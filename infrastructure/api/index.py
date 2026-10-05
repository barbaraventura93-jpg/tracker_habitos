import json,boto3,os,urllib.request,decimal,re,base64,datetime,logging,time
from boto3.dynamodb.conditions import Key
from botocore.config import Config
from botocore.exceptions import ClientError
log=logging.getLogger()
log.setLevel(logging.INFO)
dynamo=boto3.resource('dynamodb')
table=dynamo.Table(os.environ['TABLE_NAME'])
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
    prompt='Extraia todos os suplementos, vitaminas e medicamentos. Retorne APENAS um array JSON: [{"label":"nome e dose","sub":"horario e instrucao","icon":"emoji","showOn":"always"}]. Use sempre showOn=always. Somente o JSON, sem markdown.'
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
    raise Exception('contexto de importacao invalido: '+str(ctx))
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
# ─── COACH ALIMENTAR ─────────────────────────────────────────────────────────
# Uma action so (`coach`), discriminada por `mode` no body: chat | swap | flex | day.
# O frontend manda o contexto inteiro (perfil alimentar, metas, plano do dia, o que
# ja foi comido, refeicoes livres) — o Lambda nao le o DynamoDB aqui, entao a
# resposta reflete exatamente o que a pessoa ve na tela.
COACH_MEALS=['cafe','almoco','lanche','jantar','ceia']
COACH_RULES=(
  'Regras: fale em portugues do Brasil, tom acolhedor e direto, sem culpa e sem '
  'terrorismo nutricional. Use alimentos comuns e acessiveis na regiao da pessoa e '
  'que ja fazem parte da rotina dela; nunca sugira algo que ela disse nao gostar ou '
  'que viole uma restricao. Nada de dietas extremas, jejum prolongado ou menos de '
  '1200 kcal/dia. Voce nao substitui nutricionista ou medico — se a pessoa citar '
  'doenca, medicamento ou sintoma, recomende acompanhamento profissional. '
  'Sobre treino: este app nao monta treinos; se perguntarem, indique procurar um '
  'educador fisico ou apps de treino (Fitbod, Hevy, Strong).\n'
)
def _cs(v,n=300):
  return str(v if v is not None else '').strip()[:n]
def _ci(v):
  try: return max(0,int(round(float(v))))
  except: return 0
def _coach_ctx(c):
  """Transforma o contexto enviado pelo app num bloco de texto para o prompt."""
  c=c if isinstance(c,dict) else {}
  pf=c.get('perfil') or {}
  fp=c.get('foodProfile') or {}
  mt=c.get('metas') or {}
  L=[]
  obj={'cutting':'perder gordura','bulking':'ganhar massa','manutencao':'manter o peso'}.get(pf.get('objetivo'),'manter o peso')
  L.append('Objetivo: '+obj+'.')
  if pf.get('pesoAtual'): L.append('Peso atual: '+_cs(pf.get('pesoAtual'),10)+' kg; meta: '+(_cs(pf.get('pesoMeta'),10) or '?')+' kg.')
  if mt: L.append('Metas diarias: %d kcal, %dg proteina, %dg carbo, %dg gordura, %d copos de agua.'%(_ci(mt.get('kcal')),_ci(mt.get('prot')),_ci(mt.get('carb')),_ci(mt.get('fat')),_ci(mt.get('agua'))))
  for k,lbl in (('cidade','Mora em'),('rotina','Alimentos que ja fazem parte da rotina'),('gosta','Gosta de'),
                ('naoGosta','NAO gosta / evita'),('restricoes','Restricoes alimentares (respeite sempre)'),
                ('falhas','Onde sente que falha'),('obs','Observacoes')):
    v=fp.get(k)
    if isinstance(v,list): v=', '.join(_cs(x,60) for x in v[:12])
    v=_cs(v,400)
    if v: L.append(lbl+': '+v+'.')
  lv=c.get('livres') or {}
  if lv.get('limite'):
    L.append('Refeicoes livres: usou %d de %d permitidas no periodo (%s).'%(_ci(lv.get('usadas')),_ci(lv.get('limite')),_cs(lv.get('periodo'),20)))
  plano=c.get('plano') or []
  if plano:
    L.append('Plano de hoje:')
    for m in plano[:6]:
      L.append('- %s (%s)%s: %s — %d kcal, %dg prot, %dg carb, %dg gord'%(
        _cs(m.get('id'),10),_cs(m.get('label'),30),' [JA COMEU]' if m.get('done') else '',
        _cs(m.get('hint'),200) or 'sem descricao',_ci(m.get('kcal')),_ci(m.get('prot')),_ci(m.get('carb')),_ci(m.get('fat'))))
  co=c.get('consumido') or {}
  if co: L.append('Ja consumido hoje: %d kcal, %dg prot, %dg carb, %dg gord.'%(_ci(co.get('kcal')),_ci(co.get('prot')),_ci(co.get('carb')),_ci(co.get('fat'))))
  fora=c.get('foraDoPlano') or []
  if fora: L.append('Comeu fora do plano hoje: '+', '.join(_cs(x,60) for x in fora[:8])+'.')
  sups=c.get('suplementos') or []
  if sups: L.append('Suplementos que usa: '+', '.join(_cs(x,60) for x in sups[:12])+'.')
  if c.get('resumo'): L.append('Acompanhamento recente: '+_cs(c.get('resumo'),900))
  if c.get('agora'): L.append('Agora: '+_cs(c.get('agora'),60)+'.')
  return '\n'.join(L)
def _coach_json(txt,kind='{'):
  pat=r'\{[\s\S]*\}' if kind=='{' else r'\[[\s\S]*\]'
  m=re.search(pat,txt or '')
  if not m: return None
  try: return json.loads(m.group())
  except Exception: return None
def _coach_meal(it):
  mid=_cs(it.get('meal') or it.get('id'),10)
  if mid not in COACH_MEALS: return None
  hint=_cs(it.get('hint'),240)
  if not hint: return None
  return {'meal':mid,'hint':hint,'kcal':_ci(it.get('kcal')),'prot':_ci(it.get('prot')),
          'carb':_ci(it.get('carb')),'fat':_ci(it.get('fat'))}
def coach(payload):
  mode=payload.get('mode') or 'chat'
  ctx=_coach_ctx(payload.get('context'))
  head='Voce e o coach de alimentacao do app Rotina Diaria — conversa com a pessoa e adapta a alimentacao do dia a dia dela.\n'+COACH_RULES+'\nContexto da pessoa:\n'+ctx+'\n\n'
  macro='"kcal":int,"prot":int,"carb":int,"fat":int'
  if mode=='swap':
    meal=_cs(payload.get('meal'),10)
    if meal not in COACH_MEALS: raise Exception('refeicao invalida')
    pref=_cs(payload.get('pref'),200)
    prompt=(head+'Tarefa: a pessoa quer TROCAR a refeicao "'+meal+'" de hoje. Sugira 3 opcoes '
      'diferentes entre si, com quantidades, mantendo calorias e proteina proximas da refeicao atual '
      '(margem de ~10%).'+(' Pedido da pessoa: '+pref+'.' if pref else '')+'\n'
      'Responda APENAS um JSON valido, sem markdown:\n'
      '{"options":[{"hint":"alimentos com quantidades",'+macro+',"why":"frase curta"}]}')
    d=_coach_json(bedrock_text([{'text':prompt}],900,0.5)) or {}
    opts=[]
    for o in (d.get('options') or [])[:3]:
      m=_coach_meal({**o,'meal':meal})
      if m: m['why']=_cs(o.get('why'),140);opts.append(m)
    if not opts: raise Exception('Nao consegui montar opcoes agora')
    return {'options':opts}
  if mode=='flex':
    treat=_cs(payload.get('treat'),120)
    if not treat: raise Exception('diga o que quer encaixar')
    prompt=(head+'Tarefa: a pessoa quer encaixar "'+treat+'" hoje, sem culpa e sem estourar a meta do dia. '
      'Estime os macros de uma porcao realista disso e ajuste APENAS as refeicoes que ela ainda NAO comeu '
      '(reduzindo carbo/gordura, mantendo a proteina) para o total do dia continuar perto da meta. '
      'Se for razoavel, diga tambem quando encaixar.\n'
      'Responda APENAS um JSON valido, sem markdown:\n'
      '{"treat":{"name":"nome e porcao",'+macro+'},"changes":[{"meal":"id",'
      '"hint":"nova descricao com quantidades",'+macro+'}],"tip":"1-2 frases"}')
    d=_coach_json(bedrock_text([{'text':prompt}],1100,0.3)) or {}
    t=d.get('treat') or {}
    treat_o={'name':_cs(t.get('name') or treat,60),'kcal':_ci(t.get('kcal')),'prot':_ci(t.get('prot')),
             'carb':_ci(t.get('carb')),'fat':_ci(t.get('fat'))}
    ch=[m for m in (_coach_meal(x) for x in (d.get('changes') or [])[:5]) if m]
    return {'treat':treat_o,'changes':ch,'tip':_cs(d.get('tip'),400)}
  if mode=='day':
    prompt=(head+'Tarefa: monte o cardapio de HOJE para as refeicoes que ela ainda NAO comeu, variando '
      'em relacao ao plano base mas usando alimentos da rotina dela e da regiao, batendo as metas do dia '
      '(considere o que ja foi consumido). Prefira preparo simples.'
      +(' Pedido da pessoa: '+_cs(payload.get('pref'),200)+'.' if _cs(payload.get('pref'),200) else '')+'\n'
      'Responda APENAS um JSON valido, sem markdown:\n'
      '{"meals":[{"meal":"cafe|almoco|lanche|jantar|ceia","hint":"alimentos com quantidades",'+macro+'}],'
      '"tip":"1 frase sobre o foco do dia"}')
    d=_coach_json(bedrock_text([{'text':prompt}],1500,0.6)) or {}
    meals=[m for m in (_coach_meal(x) for x in (d.get('meals') or [])[:5]) if m]
    if not meals: raise Exception('Nao consegui montar o cardapio agora')
    return {'meals':meals,'tip':_cs(d.get('tip'),300)}
  # chat
  hist=payload.get('messages') or []
  conv=[]
  for m in hist[-12:]:
    who='Pessoa' if m.get('role')=='user' else 'Coach'
    t=_cs(m.get('text'),800)
    if t: conv.append(who+': '+t)
  if not conv: raise Exception('mensagem vazia')
  prompt=(head+'Conversa ate agora:\n'+'\n'.join(conv)+'\n\n'
    'Responda a ultima mensagem da Pessoa como Coach, de forma curta (ate ~120 palavras), pratica e '
    'personalizada. Se a resposta envolver mudar refeicoes de hoje, inclua as novas refeicoes em "meals" '
    '(so as que mudam; nunca as ja comidas) para ela aplicar com um toque. Sugira ate 3 respostas curtas '
    'que ela pode mandar em seguida em "chips".\n'
    'Responda APENAS um JSON valido, sem markdown:\n'
    '{"reply":"texto","meals":[{"meal":"id","hint":"...",'+macro+'}],"chips":["..."]}')
  txt=bedrock_text([{'text':prompt}],1000,0.6)
  d=_coach_json(txt)
  if not isinstance(d,dict) or not d.get('reply'):
    # modelo respondeu texto puro: melhor mostrar do que dar erro
    return {'reply':_cs(re.sub(r'```[a-z]*','',txt or ''),1500) or 'Pode repetir?','meals':[],'chips':[]}
  meals=[m for m in (_coach_meal(x) for x in (d.get('meals') or [])[:5]) if m]
  chips=[_cs(x,60) for x in (d.get('chips') or [])[:3] if _cs(x,60)]
  return {'reply':_cs(d.get('reply'),1500),'meals':meals,'chips':chips}
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
      ctx=body.get('context','')
      text=(body.get('text') or '').strip()
      if text:
        items=call_ai(None,None,ctx,text=text)
      else:
        items=call_ai(body['file'],body['mimeType'],ctx)
      return{'statusCode':200,'body':json.dumps({'items':items})}
    except Exception as e:
      return{'statusCode':500,'body':json.dumps({'error':str(e)})}
  if action=='generate_meal_plan' and method=='POST':
    try:
      body=json.loads(event.get('body') or '{}')
      res=generate_meal_plan(body)
      return{'statusCode':200,'body':json.dumps(res,cls=Dec)}
    except Exception as e:
      return{'statusCode':500,'body':json.dumps({'error':str(e)})}
  if action=='coach' and method=='POST':
    try:
      body=json.loads(event.get('body') or '{}')
      res=coach(body)
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
