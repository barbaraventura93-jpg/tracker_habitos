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

def has_any_activity(uid, date):
    try:
        resp = data_table.get_item(Key={'userId': uid, 'date': date})
        item = resp.get('Item')
        if not item:
            return False
        d = item.get('data') or {}
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
        return False
    except Exception:
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

def handler(event, context):
    if not VAPID_PRIVATE_KEY:
        return {'sent': 0, 'skipped': 0, 'errors': 0, 'note': 'VAPID_PRIVATE_KEY not configured'}

    now_hour = datetime.now(TZ).hour
    today = today_str()
    sent, skipped, errors = 0, 0, 0
    scan_kwargs = {}

    while True:
        resp = sub_table.scan(**scan_kwargs)
        for item in resp.get('Items', []):
            if not item.get('enabled', True):
                continue
            try:
                reminder_hour = int(item.get('reminderHour', -1))
            except (TypeError, ValueError):
                continue
            if reminder_hour != now_hour:
                continue

            uid = item['userId']
            if has_any_activity(uid, today):
                skipped += 1
                continue

            streak = calc_streak_through_yesterday(uid)
            if streak > 0:
                body = f'Voce esta com {streak} dias seguidos! Nao deixe seu streak quebrar hoje.'
            else:
                body = 'Bora registrar sua rotina de hoje?'
            payload = json.dumps({'title': 'Rotina Diaria', 'body': body})

            try:
                webpush(
                    subscription_info=item['subscription'],
                    data=payload,
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims={'sub': VAPID_SUBJECT},
                    ttl=3600,
                )
                sent += 1
            except WebPushException as ex:
                errors += 1
                status = getattr(getattr(ex, 'response', None), 'status_code', None)
                if status in (404, 410):
                    try:
                        sub_table.delete_item(Key={'userId': uid})
                    except Exception:
                        pass
            except Exception:
                errors += 1

        if 'LastEvaluatedKey' in resp:
            scan_kwargs['ExclusiveStartKey'] = resp['LastEvaluatedKey']
        else:
            break

    return {'sent': sent, 'skipped': skipped, 'errors': errors}
