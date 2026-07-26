import json, os, boto3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pywebpush import webpush, WebPushException

dynamo = boto3.resource('dynamodb')
sub_table = dynamo.Table(os.environ['SUB_TABLE_NAME'])
data_table = dynamo.Table(os.environ['TABLE_NAME'])

VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_SUBJECT = os.environ.get('VAPID_SUBJECT', 'mailto:barbaraventura93@gmail.com')
TZ = ZoneInfo('America/Sao_Paulo')

def today_str():
    return datetime.now(TZ).strftime('%Y-%m-%d')

def add_days(date_str, n):
    d = datetime.strptime(date_str, '%Y-%m-%d')
    return (d + timedelta(days=n)).strftime('%Y-%m-%d')

# dia da semana no padrao do app (JS getDay: Dom=0 .. Sab=6)
def dow_js(date_str):
    d = datetime.strptime(date_str, '%Y-%m-%d')
    return (d.weekday() + 1) % 7  # Python Mon=0..Sun=6 -> JS Dom=0..Sab=6

def get_data(uid, key):
    try:
        resp = data_table.get_item(Key={'userId': uid, 'date': key})
        return (resp.get('Item') or {}).get('data')
    except Exception:
        return None

def has_any_activity(uid, date):
    d = get_data(uid, date)
    if not isinstance(d, dict):
        return False
    if (d.get('water') or 0) > 0:
        return True
    if any((d.get('meals') or {}).values()):
        return True
    if d.get('sleep'):
        return True
    if any((d.get('sups') or {}).values()):
        return True
    if any((d.get('habits') or {}).values()):
        return True
    if d.get('foods'):
        return True
    return False

def calc_streak_through_yesterday(uid):
    streak = 0
    base = add_days(today_str(), -1)
    for i in range(365):
        date = add_days(base, -i)
        if has_any_activity(uid, date):
            streak += 1
        else:
            break
    return streak

# ── Lembretes por habito: habitos previstos para hoje, no horario atual, ainda nao feitos ──
def habits_due_now(uid, today, now_hour):
    habits = get_data(uid, '__habits__')
    if not isinstance(habits, list):
        return []
    day = get_data(uid, today)
    done = (day or {}).get('habits') or {}
    dow = dow_js(today)
    out = []
    for h in habits:
        try:
            days = h.get('days') or []
            if dow not in days:
                continue
            since = h.get('since')
            if since and today < since:
                continue
            t = h.get('time') or ''
            if not t:
                continue
            hh = int(str(t).split(':')[0])
            if hh != now_hour:
                continue
            if done.get(h.get('id')):
                continue
            out.append(h)
        except Exception:
            continue
    return out

# ── Insight matinal: resumo do plano do dia (treino previsto + habitos pendentes) ──
def plan_summary(uid, today):
    parts = []
    dow = dow_js(today)
    weekplan = get_data(uid, '__weekplan__') or {}
    workouts = get_data(uid, '__workouts__') or []
    if not isinstance(weekplan, dict):
        weekplan = {}
    if not isinstance(workouts, list):
        workouts = []
    tr = weekplan.get(str(dow))
    name = None
    if tr == 'descanso':
        name = 'descanso'
    elif tr:
        w = next((w for w in workouts if w.get('id') == tr), None)
        name = w.get('name') if w else None
    else:
        w = next((w for w in workouts if dow in (w.get('weekDays') or [])), None)
        name = w.get('name') if w else None
    if name == 'descanso':
        parts.append('descanso')
    elif name:
        parts.append('treino: ' + str(name))
    habits = get_data(uid, '__habits__')
    if isinstance(habits, list):
        day = get_data(uid, today)
        done = (day or {}).get('habits') or {}
        pend = [h for h in habits if dow in (h.get('days') or []) and not done.get(h.get('id'))]
        if pend:
            parts.append(str(len(pend)) + ' habito' + ('s' if len(pend) > 1 else ''))
    return parts

def send_push(subscription, uid, title, body):
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps({'title': title, 'body': body}),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={'sub': VAPID_SUBJECT},
            ttl=3600,
        )
        return 'sent'
    except WebPushException as ex:
        status = getattr(getattr(ex, 'response', None), 'status_code', None)
        if status in (404, 410):
            try:
                sub_table.delete_item(Key={'userId': uid})
            except Exception:
                pass
        return 'error'
    except Exception:
        return 'error'

def handler(event, context):
    if not VAPID_PRIVATE_KEY:
        return {'sent': 0, 'skipped': 0, 'errors': 0, 'note': 'VAPID_PRIVATE_KEY not configured'}

    now_hour = datetime.now(TZ).hour
    today = today_str()
    sent, skipped, errors, habit_sent = 0, 0, 0, 0
    scan_kwargs = {}

    while True:
        resp = sub_table.scan(**scan_kwargs)
        for item in resp.get('Items', []):
            if not item.get('enabled', True):
                continue
            uid = item['userId']
            sub = item.get('subscription')
            if not sub:
                continue

            # 1) Lembretes por habito (independente do reminderHour)
            due = habits_due_now(uid, today, now_hour)
            if due:
                names = ', '.join((str(h.get('icon', '')) + ' ' + str(h.get('name', ''))).strip() for h in due)
                title = 'Hora do seu habito' if len(due) == 1 else 'Habitos de agora'
                r = send_push(sub, uid, title, names)
                if r == 'sent':
                    habit_sent += 1
                else:
                    errors += 1

            # 2) Lembrete diario no horario escolhido — com resumo do plano do dia
            try:
                reminder_hour = int(item.get('reminderHour', -1))
            except (TypeError, ValueError):
                reminder_hour = -1
            if reminder_hour != now_hour:
                continue
            if has_any_activity(uid, today):
                skipped += 1
                continue

            plan = plan_summary(uid, today)
            streak = calc_streak_through_yesterday(uid)
            if plan:
                body = 'Seu dia: ' + ' · '.join(plan) + '. Bora comecar?'
            elif streak > 0:
                body = f'Voce esta com {streak} dias seguidos! Nao deixe seu streak quebrar hoje.'
            else:
                body = 'Bora registrar sua rotina de hoje?'

            r = send_push(sub, uid, 'Rotina Diaria', body)
            if r == 'sent':
                sent += 1
            else:
                errors += 1

        if 'LastEvaluatedKey' in resp:
            scan_kwargs['ExclusiveStartKey'] = resp['LastEvaluatedKey']
        else:
            break

    return {'sent': sent, 'habitReminders': habit_sent, 'skipped': skipped, 'errors': errors}
