import json,boto3,os,urllib.request,urllib.parse,decimal,re,base64,datetime,unicodedata,logging
from boto3.dynamodb.conditions import Key
from botocore.config import Config
from botocore.exceptions import ClientError
log=logging.getLogger()
log.setLevel(logging.INFO)
dynamo=boto3.resource('dynamodb')
table=dynamo.Table(os.environ['TABLE_NAME'])
cache_table=dynamo.Table(os.environ.get('CACHE_TABLE_NAME','exercise-cache'))
sub_table=dynamo.Table(os.environ.get('SUB_TABLE_NAME','tracker-habitos-push-subscriptions'))
# read_timeout tem que caber no Timeout da Lambda: estourar o tempo da funcao
# devolve 502 sem os headers de CORS, e o navegador reporta isso como "Failed to
# fetch", sem mensagem. Falhando dentro da funcao o erro volta como JSON.
BEDROCK_CFG=Config(connect_timeout=5,read_timeout=25,retries={'max_attempts':2,'mode':'standard'})
bedrock=boto3.client('bedrock-runtime',region_name='us-east-1',config=BEDROCK_CFG)
REGION=os.environ.get('AWS_REGION','sa-east-1')
MODEL='us.amazon.nova-lite-v1:0'
# O Amazon Nova recusa temperature=0 — o minimo aceito e 0.00001. Passar 0
# derruba a chamada inteira com ValidationException.
NOVA_MIN_TEMP=0.00001
RAPIDAPI_KEY=os.environ.get('RAPIDAPI_KEY','')
class Dec(json.JSONEncoder):
  def default(self,o):
    if isinstance(o,decimal.Decimal):
      return int(o) if o%1==0 else float(o)
    return super().default(o)
def get_uid(token):
  try:
    req=urllib.request.Request('https://cognito-idp.'+REGION+'.amazonaws.com/',data=json.dumps({'AccessToken':token}).encode(),headers={'Content-Type':'application/x-amz-json-1.1','X-Amz-Target':'AWSCognitoIdentityProviderService.GetUser'})
    with urllib.request.urlopen(req,timeout=5) as r:
      return json.loads(r.read())['Username']
  except Exception as e:
    log.warning('get_uid falhou: %s: %s',type(e).__name__,e)
    return None
def bedrock_text(content,max_tokens,temperature=None):
  """Chama o Converse e devolve o texto da resposta.

  Ponto unico de entrada do Bedrock: sem isso cada handler engolia a excecao por
  conta propria e a causa real (codigo de erro da AWS) nunca chegava ao CloudWatch.
  """
  cfg={'maxTokens':max_tokens}
  if temperature is not None: cfg['temperature']=temperature
  msgs=[{'role':'user','content':content}]
  try:
    resp=bedrock.converse(modelId=MODEL,messages=msgs,inferenceConfig=cfg)
  except ClientError as e:
    err=e.response.get('Error',{})
    code=err.get('Code','')
    log.error('bedrock converse falhou modelId=%s code=%s msg=%s',MODEL,code,err.get('Message',''))
    # Rede de seguranca: se o modelo recusar o inferenceConfig, repete so com
    # maxTokens, que e sempre aceito. Vale mais uma resposta menos deterministica
    # do que erro na tela.
    if code=='ValidationException' and 'temperature' in cfg:
      del cfg['temperature']
      log.info('repetindo converse sem temperature')
      resp=bedrock.converse(modelId=MODEL,messages=msgs,inferenceConfig=cfg)
    else:
      raise
  return resp['output']['message']['content'][0]['text']
def call_ai(file_b64,mime,ctx):
  file_bytes=base64.b64decode(file_b64)
  is_pdf=mime=='application/pdf'
  if ctx=='supplements':
    prompt='Extraia todos os suplementos, vitaminas e medicamentos. Retorne APENAS um array JSON: [{"label":"nome e dose","sub":"horario e instrucao","icon":"emoji","showOn":"always"}]. Use showOn=treino para pre/pos-treino, descanso para descanso, always para os demais. Somente o JSON, sem markdown.'
  elif ctx=='meal_plan':
    prompt=(
      'Extraia o plano alimentar com macros por refeição. Retorne APENAS um array JSON, sem markdown:\n'
      '[{"id":"cafe","hint":"descrição dos alimentos","kcal":380,"prot":35,"badge":"Semana","trigger":null}]\n'
      'Ids válidos: cafe, almoco, lanche, jantar, ceia.\n'
      'Se houver variantes (fim de semana, com carboidrato, versões do jantar), inclua com o campo trigger:\n'
      '"isFds" para final de semana | "almocoCarb" para almoço com carboidrato\n'
      '"jantarV=hamburguer" ou "jantarV=rap10" para variantes do jantar.\n'
      'Para refeições sem variante, trigger deve ser null.\n'
      'Extraia kcal e prot (proteína em gramas) de cada refeição. Somente o JSON.'
    )
  else:
    prompt='Extraia todos os exercicios deste plano de treino. Retorne APENAS um array JSON: [{"name":"exercicio","group":"Peito|Costas|Ombro|Bíceps|Tríceps|Perna|Core|Glúteo|Cardio|Outro","sets":3,"reps":"12","obs":""}]. Use os acentos exatamente como escritos. Somente o JSON, sem markdown.'
  if is_pdf:
    content=[{'document':{'format':'pdf','name':'arquivo','source':{'bytes':file_bytes}}},{'text':prompt}]
  else:
    fmt=mime.split('/')[-1].replace('jpg','jpeg')
    content=[{'image':{'format':fmt,'source':{'bytes':file_bytes}}},{'text':prompt}]
  txt=bedrock_text(content,3000)
  m=re.search(r'\[[\s\S]*\]',txt)
  if not m:
    raise Exception('Nenhum item identificado no arquivo')
  return json.loads(m.group())
EDB_HOST='exercisedb.p.rapidapi.com'
def edb_get(path):
  if not RAPIDAPI_KEY: return None
  try:
    req=urllib.request.Request('https://'+EDB_HOST+path,headers={'X-RapidAPI-Key':RAPIDAPI_KEY,'X-RapidAPI-Host':EDB_HOST})
    with urllib.request.urlopen(req,timeout=6) as r:
      return json.loads(r.read())
  except Exception as e:
    log.warning('ExerciseDB %s falhou: %s: %s',path,type(e).__name__,e)
    return None
def edb_lookup(english_name,target):
  # ExerciseDB indexa por nome em ingles; a busca e por substring e devolve varios matches
  q=(english_name or '').lower().strip()
  if not q: return None
  rows=edb_get('/exercises/name/'+urllib.parse.quote(q))
  if not isinstance(rows,list) or not rows:
    # 2a tentativa sem o equipamento: "barbell bench press" -> "bench press"
    words=q.split()
    if len(words)>2:
      rows=edb_get('/exercises/name/'+urllib.parse.quote(' '.join(words[-2:])))
  if not isinstance(rows,list) or not rows: return None
  tgt=(target or '').lower().strip()
  def score(r):
    n=(r.get('name') or '').lower()
    s=0
    if n==q: s+=100
    elif q in n or n in q: s+=40
    if tgt and (r.get('target') or '').lower()==tgt: s+=25
    return s
  return max(rows,key=score)
def identify_exercise(name):
  key=name.lower().strip()
  try:
    cached=cache_table.get_item(Key={'exerciseName':key}).get('Item')
    # so reaproveita cache do schema atual; entradas gravadas sem a chave da
    # RapidAPI sao refeitas quando a chave passa a existir
    if cached and cached.get('found') and cached.get('schema')=='v2':
      if not (cached.get('edb')=='nokey' and RAPIDAPI_KEY): return cached
  except Exception as e:
    log.warning('cache get falhou para %r: %s',key,e)
  prompt=(
    'Identifique o exercicio de musculacao: "'+name+'"\n\n'
    'Responda APENAS com um JSON valido, sem markdown:\n'
    '{"group":"Peito|Costas|Ombro|Bíceps|Tríceps|Perna|Glúteo|Core|Cardio|Outro",'
    '"targetMuscle":"musculo principal em ingles",'
    '"englishName":"nome do exercicio em ingles, como aparece numa base de dados de exercicios",'
    '"secondaryMuscles":["musculo2","musculo3"]}\n\n'
    'Exemplos:\n'
    '"Supino reto"->{"group":"Peito","targetMuscle":"pectorals","englishName":"barbell bench press","secondaryMuscles":["triceps","delts"]}\n'
    '"Remada curvada"->{"group":"Costas","targetMuscle":"latissimus dorsi","englishName":"barbell bent over row","secondaryMuscles":["biceps","rhomboids"]}\n'
    '"Rosca direta"->{"group":"Bíceps","targetMuscle":"biceps","englishName":"barbell curl","secondaryMuscles":["forearms"]}\n'
    '"Squat"->{"group":"Perna","targetMuscle":"quadriceps","englishName":"barbell squat","secondaryMuscles":["hamstrings","glutes"]}'
  )
  try:
    txt=bedrock_text([{'text':prompt}],200,NOVA_MIN_TEMP).strip()
    m=re.search(r'\{[\s\S]*\}',txt)
    if not m:
      log.warning('identify_exercise: resposta sem JSON para %r: %r',name,txt[:200])
      return {'exerciseName':key,'found':False}
    data=json.loads(m.group())
    result={
      'exerciseName':key,
      'found':True,
      'schema':'v2',
      'group':data.get('group','Outro'),
      'targetMuscle':data.get('targetMuscle',''),
      'secondaryMuscles':data.get('secondaryMuscles',[]),
      'englishName':data.get('englishName',''),
      'gifUrl':'',
      'instructions':[],
      'fromBedrock':True,
      'edb':'nokey' if not RAPIDAPI_KEY else 'miss',
      'cachedAt':datetime.datetime.utcnow().isoformat()+'Z',
    }
    # enriquece com GIF e instrucoes; o grupo em portugues continua vindo do Bedrock
    hit=edb_lookup(data.get('englishName') or name,data.get('targetMuscle'))
    if hit:
      result['edb']='hit'
      result['gifUrl']=hit.get('gifUrl') or ''
      result['edbName']=hit.get('name') or ''
      if hit.get('target'): result['targetMuscle']=hit['target']
      ins=hit.get('instructions')
      if isinstance(ins,list) and ins: result['instructions']=[str(i) for i in ins[:6]]
      sec=hit.get('secondaryMuscles')
      if isinstance(sec,list) and sec: result['secondaryMuscles']=[str(s) for s in sec]
    try: cache_table.put_item(Item=result)
    except Exception as e: log.warning('cache put falhou para %r: %s',key,e)
    return result
  except Exception as e:
    # a UI espera found:false para nao quebrar; o motivo vai junto para o campo
    # error e para o CloudWatch, em vez de sumir como "nao identificado"
    log.exception('identify_exercise falhou para %r',name)
    return {'exerciseName':key,'found':False,'error':'%s: %s'%(type(e).__name__,e)}
def week_suggestion(week_summary,untrained,remaining_days):
  if remaining_days==0: return []
  untrained_str=', '.join(untrained) if untrained else 'nenhum — semana equilibrada'
  prompt=(
    'O usuario treinou isso essa semana: '+json.dumps(week_summary,ensure_ascii=False)+'\n\n'
    'Grupos musculares NAO treinados: '+untrained_str+'\n'
    'Dias restantes na semana: '+str(remaining_days)+'\n\n'
    'Gere 1 ou 2 sugestoes curtas e motivadoras (max 2 linhas cada) sobre o que faz sentido '
    'treinar nos dias restantes para equilibrar a semana. Linguagem simples, sem jargao tecnico. '
    'Responda so com as sugestoes, sem introducao ou numeracao.'
  )
  txt=bedrock_text([{'text':prompt}],200)
  return [s.strip() for s in txt.strip().split('\n') if s.strip()]
def estimate_food(text,file_b64,mime):
  instr=(
    'Voce e um nutricionista. Estime os macros da refeicao/alimento descrito'
    +(' na imagem.' if file_b64 else ': "'+text+'".')
    +' Some tudo num unico total. Responda APENAS um JSON valido, sem markdown:\n'
    '{"name":"nome curto da refeicao","kcal":inteiro,"prot":gramas_inteiro,"carb":gramas_inteiro,"fat":gramas_inteiro}\n'
    'Se nao der para identificar comida, retorne {"name":"","kcal":0,"prot":0,"carb":0,"fat":0}.'
  )
  if file_b64:
    fb=base64.b64decode(file_b64)
    fmt=mime.split('/')[-1].replace('jpg','jpeg')
    content=[{'image':{'format':fmt,'source':{'bytes':fb}}},{'text':instr}]
  else:
    content=[{'text':instr}]
  txt=bedrock_text(content,200,NOVA_MIN_TEMP)
  m=re.search(r'\{[\s\S]*\}',txt)
  if not m:
    log.warning('estimate_food: resposta sem JSON: %r',txt[:200])
    raise Exception('Nao foi possivel estimar')
  d=json.loads(m.group())
  def _i(v):
    try: return max(0,int(round(float(v))))
    except: return 0
  return {'name':str(d.get('name','')).strip()[:60],'kcal':_i(d.get('kcal')),'prot':_i(d.get('prot')),'carb':_i(d.get('carb')),'fat':_i(d.get('fat'))}
def query_days(uid,cond_key=None):
  items=[]
  kwargs={'KeyConditionExpression':Key('userId').eq(uid)&cond_key if cond_key else Key('userId').eq(uid)}
  while True:
    resp=table.query(**kwargs)
    items+=resp.get('Items',[])
    lek=resp.get('LastEvaluatedKey')
    if not lek: break
    kwargs['ExclusiveStartKey']=lek
  return items
def handler(event,context):
  method=event.get('requestContext',{}).get('http',{}).get('method','')
  auth=(event.get('headers') or {}).get('authorization','')
  uid=get_uid(auth[7:]) if auth.startswith('Bearer ') else None
  if not uid:
    return{'statusCode':401,'body':json.dumps({'error':'unauthorized'})}
  params=event.get('queryStringParameters') or {}
  action=params.get('action','')
  date=params.get('date','')
  if action=='analyze' and method=='POST':
    try:
      body=json.loads(event.get('body') or '{}')
      items=call_ai(body['file'],body['mimeType'],body.get('context','gym_plan'))
      return{'statusCode':200,'body':json.dumps({'items':items})}
    except Exception as e:
      return{'statusCode':500,'body':json.dumps({'error':str(e)})}
  if action=='identify_exercise' and method=='GET':
    name=params.get('name','').strip()
    if not name:
      return{'statusCode':400,'body':json.dumps({'error':'missing name'})}
    try:
      result=identify_exercise(name)
      return{'statusCode':200,'body':json.dumps(result,cls=Dec)}
    except Exception as e:
      return{'statusCode':500,'body':json.dumps({'error':str(e)})}
  if action=='week_suggestion' and method=='POST':
    try:
      body=json.loads(event.get('body') or '{}')
      suggestions=week_suggestion(body.get('weekSummary',{}),body.get('untrainedGroups',[]),body.get('remainingDays',0))
      return{'statusCode':200,'body':json.dumps({'suggestions':suggestions})}
    except Exception as e:
      return{'statusCode':500,'body':json.dumps({'error':str(e)})}
  if action=='estimate_food' and method=='POST':
    try:
      body=json.loads(event.get('body') or '{}')
      text=(body.get('text') or '').strip()
      file_b64=body.get('file')
      if not text and not file_b64:
        return{'statusCode':400,'body':json.dumps({'error':'missing text or file'})}
      res=estimate_food(text,file_b64,body.get('mimeType','image/jpeg'))
      return{'statusCode':200,'body':json.dumps(res,cls=Dec)}
    except Exception as e:
      return{'statusCode':500,'body':json.dumps({'error':str(e)})}
  if action=='save_push_subscription' and method=='POST':
    try:
      body=json.loads(event.get('body') or '{}')
      sub=body.get('subscription')
      hour=int(body.get('reminderHour'))
      if not sub or not(0<=hour<=23):
        return{'statusCode':400,'body':json.dumps({'error':'missing subscription or invalid reminderHour'})}
      sub_table.put_item(Item={'userId':uid,'subscription':sub,'reminderHour':hour,'enabled':True})
      return{'statusCode':200,'body':json.dumps({'ok':True})}
    except Exception as e:
      return{'statusCode':500,'body':json.dumps({'error':str(e)})}
  if action=='delete_push_subscription' and method=='POST':
    try:
      sub_table.delete_item(Key={'userId':uid})
      return{'statusCode':200,'body':json.dumps({'ok':True})}
    except Exception as e:
      return{'statusCode':500,'body':json.dumps({'error':str(e)})}
  if action=='history_range' and method=='GET':
    start=params.get('start','');end=params.get('end','')
    if not re.match(r'^\d{4}-\d{2}-\d{2}$',start) or not re.match(r'^\d{4}-\d{2}-\d{2}$',end):
      return{'statusCode':400,'body':json.dumps({'error':'invalid start/end'})}
    try:
      items=query_days(uid,Key('date').between(start,end))
      items+=query_days(uid,Key('date').between('gym:'+start,'gym:'+end+';'))
      out=[{'date':i['date'],'data':i.get('data')} for i in items]
      return{'statusCode':200,'body':json.dumps({'items':out},cls=Dec)}
    except Exception as e:
      return{'statusCode':500,'body':json.dumps({'error':str(e)})}
  if action=='export' and method=='GET':
    try:
      items=query_days(uid)
      out={'exportedAt':datetime.datetime.utcnow().isoformat()+'Z','records':[{'date':i['date'],'data':i.get('data')} for i in items]}
      return{'statusCode':200,'body':json.dumps(out,cls=Dec)}
    except Exception as e:
      return{'statusCode':500,'body':json.dumps({'error':str(e)})}
  if not date:
    return{'statusCode':400,'body':json.dumps({'error':'missing date'})}
  if method=='GET':
    resp=table.get_item(Key={'userId':uid,'date':date})
    data=resp.get('Item',{}).get('data')
    return{'statusCode':200,'body':json.dumps(data,cls=Dec)}
  if method=='PUT':
    body=json.loads(event.get('body') or '{}')
    table.put_item(Item={'userId':uid,'date':date,'data':body})
    return{'statusCode':200,'body':json.dumps({'ok':True})}
  return{'statusCode':405,'body':json.dumps({'error':'not allowed'})}
