import json,boto3,os,urllib.request,urllib.parse,decimal,re,base64,datetime,unicodedata,logging,time
from boto3.dynamodb.conditions import Key
from botocore.config import Config
from botocore.exceptions import ClientError
log=logging.getLogger()
log.setLevel(logging.INFO)
dynamo=boto3.resource('dynamodb')
table=dynamo.Table(os.environ['TABLE_NAME'])
cache_table=dynamo.Table(os.environ.get('CACHE_TABLE_NAME','exercise-cache'))
sub_table=dynamo.Table(os.environ.get('SUB_TABLE_NAME','tracker-habitos-push-subscriptions'))
# 2 tentativas x 20s = ~45s com overhead, dentro dos 60s da funcao. A folga
# importa: estourando o Timeout da Lambda o processo e morto e nenhum except
# roda — a plataforma responde 502/"Internal Server Error", sem os headers de
# CORS e sem o campo `error` que o frontend le. Falhando aqui dentro, vira
# ReadTimeoutError com mensagem.
BEDROCK_CFG=Config(connect_timeout=5,read_timeout=20,retries={'max_attempts':2,'mode':'standard'})
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
  t0=time.time()
  try:
    resp=bedrock.converse(modelId=MODEL,messages=msgs,inferenceConfig=cfg)
    log.info('bedrock ok em %.1fs',time.time()-t0)
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
  except Exception as e:
    # timeout de leitura, DNS, TLS: nao sao ClientError e escapavam sem log
    log.error('bedrock falhou (nao-AWS) em %.1fs: %s: %s',time.time()-t0,type(e).__name__,e)
    raise
  return resp['output']['message']['content'][0]['text']
def call_ai(file_b64,mime,ctx,text=None):
  if ctx=='supplements':
    prompt='Extraia todos os suplementos, vitaminas e medicamentos. Retorne APENAS um array JSON: [{"label":"nome e dose","sub":"horario e instrucao","icon":"emoji","showOn":"always"}]. Use showOn=treino para pre/pos-treino, descanso para descanso, always para os demais. Somente o JSON, sem markdown.'
  elif ctx=='meal_plan':
    prompt=(
      'Extraia o plano alimentar com macros por refeição. Retorne APENAS um array JSON, sem markdown:\n'
      '[{"id":"cafe","hint":"descrição dos alimentos","kcal":380,"prot":35,"carb":40,"fat":10,"badge":"Semana","trigger":null}]\n'
      'Ids válidos: cafe, almoco, lanche, jantar, ceia.\n'
      'Se houver variantes (fim de semana, com carboidrato, versões do jantar), inclua com o campo trigger:\n'
      '"isFds" para final de semana | "almocoCarb" para almoço com carboidrato\n'
      '"jantarV=hamburguer" ou "jantarV=rap10" para variantes do jantar.\n'
      'Para refeições sem variante, trigger deve ser null.\n'
      'Extraia kcal, prot (proteína em g), carb (carboidrato em g) e fat (gordura em g) de cada '
      'refeição, com números inteiros. Se algum não estiver no texto, estime a partir dos alimentos. '
      'Somente o JSON.'
    )
  else:
    prompt='Extraia todos os exercicios deste plano de treino. Retorne APENAS um array JSON: [{"name":"exercicio","group":"Peito|Costas|Ombro|Bíceps|Tríceps|Perna|Core|Glúteo|Cardio|Outro","sets":3,"reps":"12","obs":""}]. Use os acentos exatamente como escritos. Somente o JSON, sem markdown.'
  if text:
    content=[{'text':prompt+'\n\nConteudo enviado pelo usuario (segmente tudo conforme as instrucoes acima):\n'+text}]
  elif (mime or '')=='application/pdf':
    file_bytes=base64.b64decode(file_b64)
    content=[{'document':{'format':'pdf','name':'arquivo','source':{'bytes':file_bytes}}},{'text':prompt}]
  else:
    file_bytes=base64.b64decode(file_b64)
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
def _clean_workouts(raw):
  """Normaliza e limita a lista de treinos vinda da IA — usada pelo gerador
  (generate_workout_plan) e pelo segmentador de texto (segment_workout_text):
  campos como string, sets inteiro, e tetos de tamanho para nao estourar o
  DynamoDB nem a tela. Devolve a lista de treinos ja saneada."""
  def _i(v,d=3):
    try: return max(1,int(round(float(v))))
    except: return d
  out=[]
  for w in (raw or [])[:7]:
    exs=[]
    for e in (w.get('exercises') or [])[:15]:
      nm=str(e.get('name','')).strip()[:80]
      if not nm: continue
      exs.append({'name':nm,'group':str(e.get('group','')).strip()[:20],
                  'sets':_i(e.get('sets')),'reps':str(e.get('reps','')).strip()[:20],
                  'obs':str(e.get('obs','')).strip()[:120]})
    if exs:
      out.append({'name':str(w.get('name','Treino')).strip()[:40],'exercises':exs})
  return out
def generate_workout_plan(payload):
  """Gera um plano de treino (varios treinos) a partir do objetivo, bioimpedancia
  e series ja feitas na semana. Retorna itens na mesma forma do import de plano
  (name/group/sets/reps/obs) para o frontend reusar o pipeline de preview."""
  grupos='Peito, Costas, Ombro, Bíceps, Tríceps, Perna, Core, Glúteo, Cardio, Outro'
  obj=payload.get('objetivo') or 'manutencao'
  n=max(1,min(7,int(payload.get('workoutsPerWeek') or 3)))
  mins=max(20,min(120,int(payload.get('minutesPerWorkout') or 60)))
  ex_alvo=max(3,min(10,round(mins/9)))
  body=payload.get('body') or {}
  goals=payload.get('goals') or {}
  week=payload.get('weekSummary') or {}
  obj_txt={'cutting':'perda de gordura (deficit calorico)',
           'bulking':'ganho de massa muscular (superavit)',
           'manutencao':'manutencao de peso e composicao'}.get(obj,'manutencao')
  ctx=[]
  if body.get('weight'): ctx.append('peso '+str(body['weight'])+'kg')
  if body.get('fat') is not None: ctx.append('gordura '+str(body['fat'])+'%')
  if body.get('lean') is not None: ctx.append('massa magra '+str(body['lean'])+'kg')
  if goals.get('idade'): ctx.append(str(goals['idade'])+' anos')
  if goals.get('sexo'): ctx.append('sexo '+('feminino' if goals.get('sexo')=='f' else 'masculino'))
  ctx_txt=', '.join(ctx) if ctx else 'nao informado'
  prompt=(
    'Voce e um profissional de educacao fisica. Monte um plano de treino de musculacao seguro, '
    'baseado em principios consolidados de treinamento de forca: volume semanal de ~10 a 20 series '
    'por grupo muscular, frequencia de ~2x por semana por grupo quando os dias permitirem, faixa de '
    'repeticoes adequada ao objetivo (hipertrofia 6-12; em deficit pode incluir algumas series de '
    'reps mais altas), e sobrecarga progressiva.\n\n'
    'Objetivo do usuario: '+obj_txt+'\n'
    'Composicao corporal / perfil: '+ctx_txt+'\n'
    'Series ja concluidas por grupo nesta semana: '+json.dumps(week,ensure_ascii=False)+'\n'
    'Treinos por semana desejados: '+str(n)+'\n'
    'Duracao por treino: '+str(mins)+' minutos (cerca de '+str(ex_alvo)+' exercicios por treino)\n\n'
    'Divida os grupos numa estrutura adequada ao numero de treinos '
    '(ex.: 2 treinos = corpo inteiro; 3 = empurrar/puxar/pernas ou A/B/C; 4 = superior/inferior). '
    'Use apenas exercicios comuns e seguros. O campo "group" deve ser EXATAMENTE um destes '
    '(com acento): '+grupos+'.\n\n'
    'Responda APENAS com um JSON valido, sem markdown, no formato:\n'
    '{"workouts":[{"name":"Treino A - Empurrar","exercises":['
    '{"name":"Supino reto","group":"Peito","sets":4,"reps":"8-12","obs":""}]}],'
    '"notes":"1 frase curta de orientacao geral"}'
  )
  txt=bedrock_text([{'text':prompt}],2000,NOVA_MIN_TEMP)
  m=re.search(r'\{[\s\S]*\}',txt)
  if not m:
    log.warning('generate_workout_plan: resposta sem JSON: %r',txt[:200])
    return {'workouts':[],'error':'Nao foi possivel gerar o treino'}
  try:
    data=json.loads(m.group())
  except Exception:
    log.warning('generate_workout_plan: JSON invalido: %r',txt[:300])
    return {'workouts':[],'error':'Resposta invalida da IA'}
  return {'workouts':_clean_workouts(data.get('workouts')),'notes':str(data.get('notes','')).strip()[:200]}
def segment_workout_text(text):
  """Segmenta um texto livre com UM OU MAIS treinos (possivelmente de dias
  diferentes) em treinos estruturados. Diferente de generate_workout_plan, que
  cria do zero: aqui a IA apenas ORGANIZA o que a pessoa colou — nao inventa
  exercicios. Devolve o mesmo formato {workouts:[{name,exercises}]} para o
  frontend reusar o preview/apply do gerador (por isso o segmentador vive fora
  do card de um treino especifico: um unico texto pode virar varios treinos)."""
  grupos='Peito, Costas, Ombro, Bíceps, Tríceps, Perna, Core, Glúteo, Cardio, Outro'
  prompt=(
    'Voce recebe um texto com UM OU MAIS treinos de musculacao, possivelmente de '
    'dias diferentes (ex.: "Treino A - segunda", "Treino B - quarta", ou blocos '
    'separados por dia). Separe em treinos distintos conforme o texto indicar.\n\n'
    'NAO invente nada: use apenas os exercicios, series e repeticoes que estao no '
    'texto. Se as series nao aparecerem, use 3. Se as repeticoes nao aparecerem, '
    'deixe "". Nao adicione exercicios que a pessoa nao escreveu.\n\n'
    'Para cada treino: "name" (o nome/dia como no texto) e "exercises". Cada '
    'exercicio: "name", "group" (EXATAMENTE um destes, com acento: '+grupos+'), '
    '"sets" (inteiro), "reps" (texto) e "obs" (o que sobrar, ex.: tecnica/descanso).\n'
    'Se houver um unico treino no texto, devolva um unico item.\n\n'
    'Responda APENAS com um JSON valido, sem markdown:\n'
    '{"workouts":[{"name":"Treino A","exercises":[{"name":"Supino reto","group":"Peito","sets":4,"reps":"8-12","obs":""}]}]}\n\n'
    'Texto:\n'+text
  )
  txt=bedrock_text([{'text':prompt}],2500,NOVA_MIN_TEMP)
  m=re.search(r'\{[\s\S]*\}',txt)
  if not m:
    log.warning('segment_workout_text: resposta sem JSON: %r',txt[:200])
    return {'workouts':[],'error':'Nao foi possivel interpretar o texto'}
  try:
    data=json.loads(m.group())
  except Exception:
    log.warning('segment_workout_text: JSON invalido: %r',txt[:300])
    return {'workouts':[],'error':'Resposta invalida da IA'}
  return {'workouts':_clean_workouts(data.get('workouts'))}
def generate_meal_plan(payload):
  """Gera um plano alimentar diario a partir do objetivo e das metas de kcal/proteina.
  Retorna itens na mesma forma da extracao de plano (id/hint/kcal/prot/trigger) para
  o frontend reusar o pipeline de preview de refeicoes."""
  obj=payload.get('objetivo') or 'manutencao'
  kcal=int(payload.get('calorias') or 0)
  prot=int(payload.get('protein') or 0)
  valid=['cafe','almoco','lanche','jantar','ceia']
  meals=[m for m in (payload.get('meals') or valid) if m in valid] or valid
  restr=(payload.get('restricoes') or '').strip()[:200]
  regiao=(payload.get('regiao') or '').strip()[:120]
  obj_txt={'cutting':'perda de gordura (deficit calorico)',
           'bulking':'ganho de massa muscular (superavit)',
           'manutencao':'manutencao de peso e composicao'}.get(obj,'manutencao')
  prompt=(
    'Voce e um nutricionista. Monte um plano alimentar diario, saudavel e pratico, '
    'adequado ao objetivo do usuario.\n\n'
    'Objetivo: '+obj_txt+'\n'
    +('Regiao onde a pessoa mora: '+regiao+' — priorize alimentos comuns, acessiveis e '
      'facilmente encontrados nos mercados dessa regiao.\n' if regiao
      else 'Priorize alimentos comuns e acessiveis no Brasil.\n')
    +('Meta diaria aproximada: '+str(kcal)+' kcal e '+str(prot)+' g de proteina.\n' if kcal else '')
    +('Restricoes/preferencias alimentares (respeite rigorosamente): '+restr+'\n' if restr else '')
    +'Refeicoes desejadas (use exatamente estes ids): '+', '.join(meals)+'\n\n'
    'Distribua as calorias e a proteina entre as refeicoes de forma coerente e realista, '
    'com quantidades (gramas/porcoes) na descricao. Para CADA refeicao preencha os quatro '
    'macros com numeros inteiros, sempre maiores que zero: kcal, prot (proteina em g), '
    'carb (carboidrato em g) e fat (gordura em g). Nunca deixe um macro em 0 ou vazio.\n'
    'Responda APENAS com um array JSON valido, sem markdown:\n'
    '[{"id":"cafe","hint":"descricao dos alimentos com quantidades","kcal":380,"prot":35,"carb":40,"fat":10,"trigger":null}]\n'
    'Use somente os ids informados; trigger sempre null.'
  )
  txt=bedrock_text([{'text':prompt}],1500,NOVA_MIN_TEMP)
  m=re.search(r'\[[\s\S]*\]',txt)
  if not m:
    log.warning('generate_meal_plan: resposta sem JSON: %r',txt[:200])
    return {'items':[],'error':'Nao foi possivel gerar o plano'}
  try:
    data=json.loads(m.group())
  except Exception:
    log.warning('generate_meal_plan: JSON invalido: %r',txt[:300])
    return {'items':[],'error':'Resposta invalida da IA'}
  def _i(v):
    try: return max(0,int(round(float(v))))
    except: return 0
  out=[]
  for it in (data if isinstance(data,list) else []):
    mid=str(it.get('id','')).strip()
    if mid not in valid: continue
    hint=str(it.get('hint','')).strip()[:220]
    if not hint: continue
    out.append({'id':mid,'hint':hint,'kcal':_i(it.get('kcal')),'prot':_i(it.get('prot')),
                'carb':_i(it.get('carb')),'fat':_i(it.get('fat')),'trigger':None})
  return {'items':out}
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
def _bio_num(v):
  try:
    if v is None or v=='': return None
    return round(float(str(v).replace(',','.')),2)
  except: return None
def _bio_date(s):
  """Normaliza a data de uma medição para ISO YYYY-MM-DD.

  A IA já recebe instrução de devolver ISO, mas laudos de bioimpedância (InBody)
  imprimem `dd.mm.yy.` — este fallback cobre esse e outros formatos dia-primeiro
  comuns no Brasil, para não descartar uma medição só por causa do formato."""
  s=str(s or '').strip().rstrip('.')
  if re.match(r'^\d{4}-\d{2}-\d{2}$',s): return s
  m=re.match(r'^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})$',s)
  if m:
    d,mo,y=int(m.group(1)),int(m.group(2)),int(m.group(3))
    if y<100: y+=2000
    if 1<=mo<=12 and 1<=d<=31:
      return '%04d-%02d-%02d'%(y,mo,d)
  return None
def analyze_bio(file_b64,mime):
  """Extrai a série de composição corporal de um exame de bioimpedância.

  Laudos como o do InBody trazem o resultado atual E uma tabela de histórico com
  medições anteriores — daí a extração devolver um array, uma entrada por data."""
  prompt=(
    'Este documento e um exame de bioimpedancia / composicao corporal (ex.: InBody). '
    'Extraia TODAS as medicoes, incluindo a TABELA DE HISTORICO com resultados de datas '
    'anteriores (as linhas de Peso, Massa Muscular Esqueletica e Percentual de Gordura ao '
    'longo das varias datas). Cada data e uma medicao separada e deve virar um item.\n\n'
    'Para cada data retorne: "date" no formato YYYY-MM-DD, "weight" (peso corporal em kg) e '
    '"fat" (percentual de gordura corporal / PBF, em %). Se um valor nao existir para uma '
    'data, use null. Nao invente datas nem valores.\n\n'
    'Responda APENAS com um array JSON valido, sem markdown, ordenado por data crescente:\n'
    '[{"date":"2026-05-23","weight":82.9,"fat":35.7}]'
  )
  file_bytes=base64.b64decode(file_b64)
  if (mime or '')=='application/pdf':
    content=[{'document':{'format':'pdf','name':'exame','source':{'bytes':file_bytes}}},{'text':prompt}]
  else:
    fmt=(mime or 'image/jpeg').split('/')[-1].replace('jpg','jpeg')
    content=[{'image':{'format':fmt,'source':{'bytes':file_bytes}}},{'text':prompt}]
  txt=bedrock_text(content,2000)
  m=re.search(r'\[[\s\S]*\]',txt)
  if not m:
    log.warning('analyze_bio: resposta sem JSON: %r',txt[:200])
    return []
  data=json.loads(m.group())
  out,seen=[],set()
  for it in (data if isinstance(data,list) else []):
    if not isinstance(it,dict): continue
    d=_bio_date(it.get('date'))
    if not d or d in seen: continue
    w=_bio_num(it.get('weight'));f=_bio_num(it.get('fat'))
    if w is not None and not(20<=w<=400): w=None
    if f is not None and not(1<=f<=75): f=None
    if w is None and f is None: continue
    lean=round(w*(1-f/100),2) if(w is not None and f is not None) else None
    seen.add(d)
    out.append({'date':d,'weight':w,'fat':f,'lean':lean})
  out.sort(key=lambda e:e['date'])
  return out
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
  """Guarda de ultimo recurso.

  Qualquer excecao que escapasse do _dispatch fazia a plataforma responder
  {"message":"Internal Server Error"} — JSON valido, mas sem o campo `error` que
  o frontend le, o que virava "falha ao estimar" sem causa nenhuma. Aqui o erro
  vira sempre JSON nosso, com nome da excecao.
  """
  params=event.get('queryStringParameters') or {}
  action=params.get('action','') or '(dia)'
  try:
    return _dispatch(event,context)
  except Exception as e:
    log.exception('handler falhou action=%s',action)
    return{'statusCode':500,'body':json.dumps({'error':'%s: %s'%(type(e).__name__,e),'action':action})}
def _dispatch(event,context):
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
      ctx=body.get('context','gym_plan')
      text=(body.get('text') or '').strip()
      if text:
        items=call_ai(None,None,ctx,text=text)
      else:
        items=call_ai(body['file'],body['mimeType'],ctx)
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
  if action=='generate_workout_plan' and method=='POST':
    try:
      body=json.loads(event.get('body') or '{}')
      res=generate_workout_plan(body)
      return{'statusCode':200,'body':json.dumps(res,cls=Dec)}
    except Exception as e:
      return{'statusCode':500,'body':json.dumps({'error':str(e)})}
  if action=='segment_workout_text' and method=='POST':
    try:
      body=json.loads(event.get('body') or '{}')
      text=(body.get('text') or '').strip()
      if not text:
        return{'statusCode':400,'body':json.dumps({'error':'missing text'})}
      res=segment_workout_text(text)
      return{'statusCode':200,'body':json.dumps(res,cls=Dec)}
    except Exception as e:
      return{'statusCode':500,'body':json.dumps({'error':str(e)})}
  if action=='generate_meal_plan' and method=='POST':
    try:
      body=json.loads(event.get('body') or '{}')
      res=generate_meal_plan(body)
      return{'statusCode':200,'body':json.dumps(res,cls=Dec)}
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
  if action=='analyze_bio' and method=='POST':
    try:
      body=json.loads(event.get('body') or '{}')
      file_b64=body.get('file')
      if not file_b64:
        return{'statusCode':400,'body':json.dumps({'error':'missing file'})}
      items=analyze_bio(file_b64,body.get('mimeType','application/pdf'))
      return{'statusCode':200,'body':json.dumps({'items':items},cls=Dec)}
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
  if action=='delete_account' and method=='POST':
    # Apaga tudo que existe deste uid nas tabelas. O usuario do Cognito quem
    # remove e o proprio cliente, com o AccessToken, depois desta chamada dar
    # certo — se fosse ao contrario o token morreria antes e as linhas do
    # DynamoDB ficariam orfas, sem ninguem que consiga apaga-las.
    try:
      body=json.loads(event.get('body') or '{}')
      if body.get('confirm')!='EXCLUIR':
        return{'statusCode':400,'body':json.dumps({'error':'confirmation required'})}
      items=query_days(uid)
      with table.batch_writer() as batch:
        for it in items:
          batch.delete_item(Key={'userId':uid,'date':it['date']})
      try:
        sub_table.delete_item(Key={'userId':uid})
      except Exception:
        pass  # sem inscricao de push nao ha o que apagar
      return{'statusCode':200,'body':json.dumps({'ok':True,'deleted':len(items)})}
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
    # parse_float=Decimal: o DynamoDB recusa float ("Float types are not
    # supported"); qualquer numero decimal do cliente (peso, %, macros) tem que
    # virar Decimal antes do put_item, senao a fila do outbox trava inteira.
    body=json.loads(event.get('body') or '{}',parse_float=decimal.Decimal)
    table.put_item(Item={'userId':uid,'date':date,'data':body})
    return{'statusCode':200,'body':json.dumps({'ok':True})}
  return{'statusCode':405,'body':json.dumps({'error':'not allowed'})}
