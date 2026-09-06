# tracker_habitos — Contexto para Claude Code

## Estado do projeto (2026-07-28)

O roadmap de `docs/transformacao-app-diario.md` (Fases A–E) está **concluído**, assim
como as três fases da Periodização Semanal descritas abaixo. Os dois documentos de
planejamento do repositório viraram registro histórico:

- `docs/transformacao-app-diario.md` — diagnóstico e roadmap, tudo entregue
- `exercicios-refinamento.md` — resta **um item**: o redesign do formulário do Plano

Gaps técnicos ainda abertos, nenhum bloqueante: **latência do Cognito** (`get_uid()`
faz round-trip a cada request) e **`habit-tracker.html` com ~5k linhas**. A outra
metade do gap de manutenibilidade foi fechada — o Lambda da API saiu de dentro do
`template.yaml` e virou `infrastructure/api/index.py`.

O isolamento do `localStorage` por usuário e o assistente de primeiro acesso estão
entregues — ver as seções "Multi-usuário" e "Onboarding" abaixo.

## Arquitetura atual

- **Frontend:** HTML/CSS/JS puro, single file (`habit-tracker.html`), hospedado em S3 + CloudFront
- **Backend:** AWS Lambda (Python 3.12) com Function URL — single function, discriminada por `?action=`. Código em `infrastructure/api/index.py`, empacotado em zip pelo workflow e publicado em `s3://tracker-habitos/lambda-builds/api.zip`
- **DB:** DynamoDB `tracker-habitos-data` — PK `userId` (string) + SK `date` (string)
- **Auth:** AWS Cognito — Lambda extrai `userId` do `AccessToken` via `GetUser`
- **Infra como código:** `infrastructure/template.yaml` (CloudFormation)
- **CI/CD:** GitHub Actions — push em `main` → CloudFormation update → deploy S3 → invalidação CloudFront

## Multi-usuário

Cada request carrega `Bearer <token>`, o Lambda valida no Cognito e usa o `uid`
retornado como PK no DynamoDB. Do lado do servidor os dados sempre foram isolados.

O `localStorage` **também é isolado agora**. Todo cache local vive sob
`ht:u:<uid>:<chave>`; só `ht:token`, `ht:refresh` e `ht:legacy_claimed` são globais.
Antes as chaves eram planas (`ht:goals`, `ht:2026-06-18`, `ht:outbox`), e dois logins
no mesmo navegador compartilhavam tudo — o segundo usuário via o cache do primeiro
até a API responder, e as coleções que só são sobrescritas quando o servidor devolve
algo (`__csups__`, `__goalsdefs__`, `__workouts__`) nunca eram limpas. Pior: o
`ht:outbox` do primeiro era enviado com o token do segundo.

Como funciona:

- `uidFromToken()` lê o `sub` direto do JWT do AccessToken — sem round-trip. Como o
  pool usa `UsernameAttributes: email`, o `username` do Cognito é o próprio `sub`,
  o mesmo valor que o Lambda usa como PK.
- **Use `lsGet` / `lsSet` / `lsDel`, nunca `localStorage` direto** para dado de
  usuário. Sem escopo definido eles viram no-op, então nada vaza antes do login.
- `setUserScope()` + `reloadUserState()` rodam no login, no logout e no boot.
  `reloadUserState()` relê todo `let` de estado do escopo novo — se você adicionar
  um novo `let x=loadX()` no topo do arquivo, **precisa** incluí-lo lá.
- `claimLegacyKeys()` migra as chaves planas da instalação antiga para o escopo do
  usuário que já estava logado no boot. Num login novo essas chaves são
  descartadas: são de outra pessoa, e o servidor tem tudo.

Os defaults pessoais (`LEGACY_SUPS` com Oximetalona/DHEA, `DEFAULT_MEAL_PLAN` com o
cardápio da Bárbara) só valem quando `_legacyInstall` é true. Conta nova começa com
lista de suplementos vazia e sem plano alimentar — não com a rotina de outra pessoa.

## Onboarding

Assistente de 7 passos em `screen-onboarding`, disparado por `needsOnboarding()`
dentro de `enterApp()`: boas-vindas → perfil → semana de treino → alimentação →
suplementos → metas/hábitos → resumo. Só o perfil pede preenchimento; todo o resto
tem "pular", e `onbFinish()` **só grava as etapas que não foram puladas** (`d.skipped`).

Onde cada passo escreve: perfil e alimentação → `__goals__`; treino →
`__workouts__` (weekDays) + `__weekplan__`; alimentação com "criar refeições" →
`__mealplan__` (kcal/proteína distribuídos por `ONB_MEAL_SPLIT`, descrição em
branco); suplementos → `__csups__`; hábitos → `__habits__`.

As fórmulas nutricionais (`calcBMR`, `activityFactor`, `calorieAdjust`,
`calcCalories`, `calcProtein`, `calcWaterCups`) são compartilhadas com a tela de
Configurações de Saúde — as duas telas têm que chegar no mesmo número.

## Convenções do Lambda

Ações especiais no Lambda usam `?action=<nome>`. As que existem hoje:

| Action | O que faz |
|---|---|
| `analyze` (POST) | extrai exercícios/suplementos/plano alimentar de PDF/imagem/texto via Bedrock (array plano de itens) |
| `identify_exercise` | grupo + músculos + GIF + instruções de um exercício, com cache |
| `estimate_food` | estima macros de refeição livre (texto ou foto) via Bedrock |
| `week_suggestion` | sugestão de treino para os dias restantes da semana |
| `generate_workout_plan` (POST) | gera um plano de treino (vários treinos) a partir do objetivo, bioimpedância e séries da semana — formato `{workouts:[{name,exercises}]}` |
| `segment_workout_text` (POST) | segmenta um texto livre com **um ou mais** treinos (vários dias num só bloco) em treinos estruturados, sem inventar exercícios — mesmo formato do gerador, para reusar o preview/apply |
| `generate_meal_plan` (POST) | gera plano alimentar por IA a partir de objetivo, região e metas de kcal/proteína |
| `analyze_bio` (POST) | extrai a série de composição corporal (atual + histórico) de um exame de bioimpedância |
| `history_range` | Query por `userId` com `date BETWEEN` — hidrata o histórico num dispositivo novo |
| `export` | download de todos os dados do usuário |
| `delete_account` (POST) | apaga todas as linhas do `userId` nas duas tabelas — exige `{"confirm":"EXCLUIR"}` no body |
| `save_push_subscription` / `delete_push_subscription` | inscrição Web Push |

### Notificações push — por que "não deixa ativar"

O botão de ativar depende de coisas fora do nosso código, e cada uma falha de um
jeito diferente. `pushSupport()` no frontend separa os casos e o card de LEMBRETES
mostra a instrução correspondente em vez de um "não suporta" sem saída:

- **iPhone/iPad**: Web Push só existe com o app **instalado na Tela de Início**.
  No Safari em aba, `PushManager` nem aparece — não é bug, é a plataforma. O
  `manifest.json` já declara `display: standalone`
- **Permissão negada**: o navegador não pergunta de novo. Só destravando na mão
  (cadeado → Notificações → Permitir). Por isso o card detecta
  `Notification.permission==='denied'` e ensina o caminho
- **Inscrição antiga com outra chave VAPID**: reaproveitar manda o push para o
  vazio e um `subscribe()` novo estoura `InvalidStateError`. `sameServerKey()`
  compara os bytes e reinscreve quando difere
- **Android/Chrome**: o `requestPermission()` pode devolver `denied` na hora, sem
  mostrar prompt nenhum, quando o site já foi bloqueado antes (inclusive pelo
  bloqueio automático do Chrome). `unblockSteps()` dá o caminho por plataforma —
  no Android o do sistema também, que fica fora do navegador
- Safari antigo devolve `requestPermission` por callback, sem promise — daí o
  wrapper `requestNotificationPermission()`

Todo passo assíncrono da ativação passa por `withTimeout()`. Uma promise que
nunca resolve (registro do SW, `ready`, `subscribe`) deixaria o botão preso em
"Ativando…" para sempre — que é justamente a cara de "o app não deixa ativar".

O botão "Enviar notificação de teste" (`testPushNotification()`) só aparece com
os lembretes ativos e dispara `showNotification` local, sem servidor. Ele divide
o problema em dois: se a notificação aparece, permissão e service worker estão de
pé e o que falta está no envio (VAPID/push-sender); se não aparece, é do aparelho
e não adianta investigar a Lambda.

Erros de ativação vão para o `console` e para uma nota dentro do card
(`_pushNote`), não para o toast: instrução de configuração não cabe em 3 segundos.

"Datas especiais" no DynamoDB (não são datas reais, são chaves de config por usuário):
`__gymplan__`, `__workouts__`, `__mealplan__`, `__csups__`, `__goals__`, `__goalsdefs__`,
`__goallogs__`, `__body__`, `__habits__`, `__weekplan__`, `__periodization__`

## Conta do usuário

Tudo em `showAccount()`, dentro de Mais › Conta e senha:

- **Alterar senha** — `ChangePassword` do Cognito, direto do cliente, sem backend.
  `NotAuthorizedException` cobre senha errada *e* token vencido; só a `message`
  separa os dois, e o código dá `tryRefresh()` antes de desistir no segundo caso.
- **Refazer configuração inicial** — apaga `ht:onboard_done` e reabre o assistente.
- **Excluir conta** — a ordem importa: primeiro `action=delete_account` (dados no
  DynamoDB), depois `DeleteUser` no Cognito, por último `wipeUserScope()` no
  `localStorage`. Ao contrário, o token morreria antes e as linhas do DynamoDB
  ficariam órfãs, sem ninguém que consiga apagá-las. Se a API falhar, nada é
  apagado e o Cognito nem é chamado.

## IAM

Policy `DynamoDBAccess`: `GetItem`, `PutItem`, `DeleteItem`, `BatchWriteItem`,
`Scan` e `Query`, nas três tabelas (`tracker-habitos-data`, `exercise-cache` e
`tracker-habitos-push-subscriptions`). O `Query` entrou junto com o
`history_range`; o `BatchWriteItem`, junto com o `delete_account`.

Policy `BedrockAccess`: `bedrock:InvokeModel` com `"*"`.

**Gap conhecido e ainda aberto:** `get_uid()` chama `GetUser` no Cognito a cada
request (~100–200 ms extras). Validar a assinatura do JWT localmente, com JWKS
em cache, dispensaria a maioria dessas chamadas.

---

## Periodização Semanal — entregue (Fases 1, 2 e 3)

As três fases estão no `main`. O que segue descreve o que existe, não um plano.

### Tela Semana (Fase 1)

- Aba "Semana" dentro da tela de treino, com os 7 dias (Seg–Dom): tipo de treino,
  grupos musculares trabalhados e duração
- Silhueta SVG desenhada à mão no próprio HTML (`viewBox 0 0 400 466`, paths
  espelhados por `transform="scale(-1,1)"`), colorida por intensidade via `svgFill`
- **A intensidade é contagem de séries concluídas, não volume de carga.**
  `muscleSets[grupo] += nº de séries com done=true`, e
  `pct = min(100, round(muscleSets[grupo] / 15 × 100))` — ou seja, 15 séries na
  semana saturam o grupo em 100%. A ideia original de `Σ(séries × reps × peso)`
  não foi adiante: peso é opcional no log e deixava o mapa vazio para quem não
  anota carga
- `Cardio` e `Outro` ficam fora do heatmap de propósito
- Os 7 dias são lidos do cache local (`loadDay`), hidratado por `history_range` —
  **não existe handler `week_summary`**, ele foi descartado quando o `Query`
  entrou no IAM e tornou o `history_range` suficiente

### Identificação de exercício (Fase 2)

- Tabela `exercise-cache` (PK `exerciseName`, global — sem `userId`)
- `identify_exercise` roda em dois passos: o Bedrock resolve o grupo em português
  (necessário para o heatmap, e que a ExerciseDB não fornece) e traduz o nome para
  inglês; essa tradução busca GIF, instruções e músculo-alvo na ExerciseDB
- A ordem importa: buscar a ExerciseDB primeiro erraria quase sempre, porque os
  nomes são digitados em português. Assim fica 1 requisição por exercício novo,
  dentro do free tier de 100/dia
- Sem a chave da RapidAPI o handler continua funcionando, só não enriquece — essas
  entradas são marcadas com `edb:'nokey'` e refeitas quando a chave passa a existir.
  O marcador `schema:'v2'` invalida entradas antigas gravadas com `gifUrl` vazio

### Sugestão semanal (Fase 3)

- `action=week_suggestion` via Bedrock, com os grupos não treinados e os dias
  restantes da semana no contexto

### Timer de treino

Um único widget com dois modos, em `_tmr`: `rest` (regressivo, descanso entre
séries) e `work` (progressivo, exercícios medidos em tempo).

- O widget é criado em `document.body`, **não** dentro do HTML da tela. `renderGym()`
  reconstrói a tela inteira a cada série marcada — dentro dela o timer morreria a
  cada toque
- O tempo sai sempre de `Date.now()` (`_tmrValue()`), nunca de um contador
  decrementado: com a tela apagada o navegador estrangula o `setInterval` e um
  contador dessincronizaria
- `AudioContext` é criado no **início** do timer, que é sempre um gesto do usuário.
  Criar no fim da contagem seria bloqueado pelo mobile, que exige gesto
- Preferências em `localStorage` `ht:tmr` (`{rest, auto, sound}`). Os botões ±15s
  gravam o novo padrão — o timer aprende o descanso real, sem tela de configuração
- `timerLogWork()` grava na primeira série pendente: `"45s"` na musculação,
  minutos decimais no aeróbico (onde o campo alimenta `dayData.gymDurMin`).
  Guarda `date`/`tr` do início para não gravar no lugar errado se a pessoa
  trocar de dia no meio
- A classe `body.tmr-on` aumenta o `padding-bottom` do `.screens-wrap` para a
  barra não cobrir o fim da lista

### Grupos musculares — atenção ao acento

`GYM_GROUPS` usa **`Bíceps`, `Tríceps`, `Glúteo` com acento**. O heatmap indexa
`muscleSets` por essa string, então qualquer valor sem acento simplesmente some do
mapa, sem erro visível. Os prompts do Bedrock pedem os grupos acentuados, e
`canonGroup()` no frontend normaliza qualquer variante recebida — use essa função
em vez de comparar strings de grupo na mão. `loadGymPlan`, `loadGymSession` e
`syncGymPlan` também normalizam na leitura, para curar dado gravado antes do fix.

---

## Onde mexer no backend

O código das duas Lambdas está em arquivo próprio — **não edite Python dentro do
`template.yaml`**, ele só declara infraestrutura:

| Lambda | Fonte | Zip no S3 |
|---|---|---|
| `tracker-habitos-api` | `infrastructure/api/index.py` | `lambda-builds/api.zip` |
| `tracker-habitos-push-sender` | `infrastructure/push-sender/index.py` | `lambda-builds/push-sender.zip` |

O `S3Key` é fixo, então o CloudFormation **não** percebe mudança de código. Quem
republica é o passo `update-function-code` do workflow, depois do deploy da stack.
Se você mudar o caminho do zip, mude nos dois lugares (template e workflow).

A API não tem `requirements.txt`: usa só stdlib + `boto3`, que já vem no runtime.
Se um dia precisar de dependência de terceiros, copie o padrão do `push-sender`
(`pip install -t` antes do zip).

⚠️ O passo "Atualizar RAPIDAPI_KEY" usa `update-function-configuration
--environment`, que **substitui o mapa inteiro de variáveis**, não faz merge. Toda
variável declarada no template precisa estar repetida lá, senão some a cada deploy.

### Chamadas ao Bedrock

Toda chamada passa por `bedrock_text(content, max_tokens, temperature=None)` —
não chame `bedrock.converse` direto. O helper registra o código de erro real da
AWS no CloudWatch antes de propagar; sem ele os erros sumiam nos `except` mudos.

⚠️ **`temperature=0` é inválido no Amazon Nova** — o mínimo aceito é `0.00001`
(a constante `NOVA_MIN_TEMP`). Passar `0` derruba a chamada inteira com
`ValidationException`. Foi o que quebrou `estimate_food` e `identify_exercise`
enquanto `analyze` e `week_suggestion`, que não mandavam `temperature`,
continuavam funcionando. O helper ainda repete a chamada sem `temperature` se o
modelo recusar o `inferenceConfig`, então uma mudança futura de validação
degrada em vez de quebrar.

O `read_timeout` do cliente (25 s × 2 tentativas) tem que caber no `Timeout` da
Lambda, hoje 60 s. Se a função estoura o tempo, o Function URL responde 502 **sem
os headers de CORS** e o navegador mostra só "Failed to fetch", sem a causa.

## Comandos úteis

```bash
# Deploy: só acontece via push para main — o CI/CD cuida do resto
git push origin main
```

O workflow `Deploy to S3` **não roda em pull requests**, só em push para `main`.
PRs não têm checks — a validação antes do merge é manual.
