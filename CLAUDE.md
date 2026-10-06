# tracker_habitos — Contexto para Claude Code

## Estado do projeto (2026-10-05) — virada para coach alimentar

O app deixou de ser "rotina + treino" e virou um **coach de alimentação,
suplementação e hábitos** (referência: a experiência do Fitbod, aplicada à comida).
O app não acompanha mais treino — ver "Coach alimentar" abaixo. **Todo o código
de treino foi removido** (frontend e Lambda: log, plano, timer, heatmap, Semana,
periodização, gerador de treino, `identify_exercise`, `week_suggestion`,
`generate_workout_plan`, `extract_workout_plan`). Não reintroduza.

Ficou de propósito, por ser infraestrutura e não código: a tabela `exercise-cache`,
o parâmetro/secret `RapidApiKey` e o passo "Atualizar RAPIDAPI_KEY" do workflow.
Tirar a tabela do `template.yaml` faz o CloudFormation **apagá-la** — se for fazer,
faça num PR próprio e consciente. As chaves antigas de treino no DynamoDB
(`gym:<data>:<treino>`, `__gymplan__`, `__workouts__`, `__weekplan__`,
`__periodization__`) continuam nas contas, aparecem no `export` e são apagadas pelo
`delete_account`; o app só não as lê mais (`hydrateRange` pula `gym:`).

### Histórico (2026-07-28)

O roadmap de `docs/transformacao-app-diario.md` (Fases A–E) está **concluído**, assim
como as três fases da Periodização Semanal descritas abaixo. Os dois documentos de
planejamento do repositório viraram registro histórico:

- `docs/transformacao-app-diario.md` — diagnóstico e roadmap, tudo entregue
- `exercicios-refinamento.md` — arquivado: era sobre treino, que saiu do app

Gaps técnicos ainda abertos, nenhum bloqueante: **latência do Cognito** (`get_uid()`
faz round-trip a cada request) e **`habit-tracker.html` com ~5,2k linhas**. A outra
metade do gap de manutenibilidade foi fechada — o Lambda da API saiu de dentro do
`template.yaml` e virou `infrastructure/api/index.py`.

O isolamento do `localStorage` por usuário e o assistente de primeiro acesso estão
entregues — ver as seções "Multi-usuário" e "Onboarding" abaixo.

## Identidade visual — "Sálvia & Linho" (2026-10-05)

Visual de coach de rotina, alimentação e bem-estar: verde-sálvia claro, fundo linho,
toque de rosé. Tokens no `:root` do `habit-tracker.html` (`--accent` #6E9C7E,
`--accent-deep` #4F7F60, `--accent-light`, `--rose`, `--bg` #F6F8F2…).

- **Fontes:** títulos em Cormorant Garamond (`var(--serif)`), texto e números em Jost
  (`font-variant-numeric:tabular-nums` no lugar da antiga fonte mono).
- **Ícones de interface:** traço fino via sprite SVG logo após o `<body>`. Em JS use
  `ic('nome')` (ex.: `ic('drop')`, `ic('leaf')`); em HTML estático,
  `<svg class="i"><use href="#i-nome"/></svg>`. Emoji só onde é conteúdo do usuário
  (ícone de refeição, suplemento, hábito).
- **Não volte ao roxo (#6C63FF) nem a cinzas frios.** Cores novas: puxe do token ou da
  mesma família (pêssego p/ refeições, névoa azul p/ água, lilás p/ sono, dourado p/
  suplementos, rosé p/ alertas).
- Componentes: `.coach-hero` (abertura do dia em Hoje), `.btn-primary`, `.btn-soft`,
  `.btn-link`. Login/onboarding escondem a navegação via `body.auth-on`.

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
  `reloadUserState()` relê todo `let` de estado do escopo novo (inclusive `foodProfile` e `coachMsgs`) — se você adicionar
  um novo `let x=loadX()` no topo do arquivo, **precisa** incluí-lo lá.
- `claimLegacyKeys()` migra as chaves planas da instalação antiga para o escopo do
  usuário que já estava logado no boot. Num login novo essas chaves são
  descartadas: são de outra pessoa, e o servidor tem tudo.

Os defaults pessoais (`LEGACY_SUPS` com Oximetalona/DHEA, `DEFAULT_MEAL_PLAN` com o
cardápio da Bárbara) só valem quando `_legacyInstall` é true. Conta nova começa com
lista de suplementos vazia e sem plano alimentar — não com a rotina de outra pessoa.

## Onboarding

Assistente de 7 passos em `screen-onboarding`, disparado por `needsOnboarding()`
dentro de `enterApp()`: boas-vindas → perfil (inclui nível de atividade) → rotina
alimentar (entrevista em chat) → alimentação → suplementos → metas/hábitos → resumo. O perfil é **obrigatório**
(idade, altura e peso atual — base de todos os cálculos) e não tem "pular"; todo o resto
tem, e `onbFinish()` **só grava as etapas que não foram puladas** (`d.skipped`). As Configurações de Saúde
(`saveGoalsForm`) exigem os mesmos três campos antes de salvar.

Onde cada passo escreve: perfil e alimentação → `__goals__` (o nível de atividade
vira `treinosSemana`, que só alimenta o fator de gasto calórico); rotina →
`__foodprofile__`; alimentação com "criar refeições" →
`__mealplan__` (kcal/proteína distribuídos por `ONB_MEAL_SPLIT`, descrição em
branco); suplementos → `__csups__`; hábitos → `__habits__`.

As fórmulas nutricionais (`calcBMR`, `activityFactor`, `objFromWeights`,
`calorieAdjust`, `calcCalories`, `calcProtein`, `calcWaterCups`,
`weightProjection`/`projLine`) são compartilhadas com a tela de Configurações de
Saúde — as duas telas têm que chegar no mesmo número.

O **objetivo é derivado**, não escolhido por um seletor cutting/bulking/manutenção.
A meta de peso manda quando há diferença clara (`objFromWeights`: meta < peso →
`cutting`, meta > peso → `bulking`); com o peso **estável** (diferença ≤1 kg ou sem
meta — `isStableWeight`) o app pergunta o **foco de recomposição** (`goals.recomp` /
`d.recomp`: `perder_gordura` | `ganhar_massa` | `manter`), porque dá para trocar
gordura por músculo sem mexer na balança. `resolveObjetivo(peso,meta,recomp)` junta os
dois e devolve o objetivo efetivo, que pode ser `cutting`, `bulking`, `manutencao`,
`recomp_fat` ou `recomp_lean`. A pergunta (`recompQuestionHtml`) aparece no preview do
onboarding e no card de OBJETIVO das Configurações, só quando o peso está estável;
`saveGoalsForm`/`onbFinish` gravam `objetivo` (efetivo) e `recomp`.

O ajuste calórico segue o objetivo efetivo: `calorieAdjust(objetivo,tdee)` devolve
déficit de 20% do TDEE no cutting (300–750 kcal), superávit de 12% no bulking (200–450
kcal), déficit leve de 10% no `recomp_fat` (150–400), superávit leve de 8% no
`recomp_lean` (150–350) e 0 na manutenção. Proteína (`PROT_FACTORS`): 2,2 cutting, 1,8
bulking, 2,0 nos dois recomp, 1,6 manutenção. A meta de peso (`pesoMeta`) alimenta a
direção e a **projeção** de quando a meta é atingida (`weightProjection`, ~7700
kcal/kg), exibida no preview do onboarding e no card de PESO das Configurações
(`#g-peso-proj`).

## Coach alimentar

Navegação: **Hoje · Progresso · Mais**. Hoje, Plano e Coach viraram **uma tela
só** (`renderHoje`): coach (`dailyInsightCard`) → jejum (`fastCard`) → score →
refeições (`mealsCardHtml`) → fora do plano → refeições livres → suplementos
(`supsCardHtml`) → hábitos (checklist em `renderHabitsToday`) → água → sono →
resumo nutricional → metas → observações. O planner "Meu dia" saiu. A conversa
(`screen-coach`) abre por cima de Hoje, com botão de voltar; `showBnav('nutricao')`
e `'coach'` continuam aceitos e caem em Hoje. Treino é só indicação de apps
(`showTreinoApps()`, Mais › Treino).

- **Perfil alimentar** — `foodProfile`, chave `ht:foodprofile` / `__foodprofile__`:
  `cidade`, `rotina`, `gosta`, `naoGosta`, `restricoes[]`+`restricoesTxt`,
  `falhas[]`+`falhaTxt`, `livresQtd`+`livresPeriodo` (`semana|quinzena|mes`).
  Coletado pela entrevista em formato de chat (`PF_QS`, `pfRender`/`pfMount`), que é
  o passo `rotina` do onboarding e também a tela Mais › Perfil alimentar.
  `saveFoodProfile()` espelha cidade/restrições em `goals.regiao`/`goals.restricoes`
  (que o `generate_meal_plan` lê).
- **Ajuste do dia** — `dayData.mealOverrides[refeição] = {hint,kcal,prot,carb,fat,badge}`.
  `getMealSlot()` olha o override antes do plano base, então tudo que lê o plano
  (resumo, progresso, contexto do coach) já enxerga o ajuste. Só vale para a data
  em que foi gravado. Override nunca é aplicado em refeição já marcada como feita.
- **Refeições livres** — item de `dayData.foods` com `free:true`.
  `freeMealStatus()` conta no período do perfil. Itens com `src:'flex'` são o extra
  planejado pelo "Encaixar um extra" e não contam como livre nem como "fora do plano".
- **Consumo e metas** — use `dayIntake(dd)` e `nutriTargets()`; não recalcule na mão.
- **Progresso** — `progressStats(n)` olha os N dias **antes de hoje** e ignora dia sem
  registro nenhum. `progressInsights()` são regras locais (sem IA); cada uma pode
  levar uma pergunta pronta para o coach (`coachAsk`). O topo da tela tem o card
  **Peso e projeção** (`prgWeightCard`): peso atual/meta/faltam, a curva de peso
  (reaproveita `renderBodyChart` com os `bodyEntries`) e a projeção da meta **pelo que
  vem sendo cumprido** — `planProjection(p,peso)` compara a média real de calorias
  registradas (`p.kcal`) com o gasto (TDEE recalculado do perfil) e estima o ritmo;
  `weighingRate()` dá o ritmo real medido nas pesagens como complemento. O card aparece
  mesmo sem registro de refeições (a projeção então pede dados). Objetivo de
  recomposição não projeta peso (mostra nota sobre composição).
- **Conversa** — `coachMsgs` em `ht:coach_chat` (local, não sincroniza, últimas 60).
- **Jejum intermitente** — `foodProfile.jejum = {proto, inicio}`; `proto` é
  `12:12|14:10|16:8|18:6` (janela diária), `flex` (às vezes pula o café) ou `nenhum`;
  `inicio` abre a janela de alimentação. No dia, `dayData.fast` true/false sobrepõe o
  perfil (`flex`/`nenhum` jejuam com 16:8 quando a pessoa toca em "Vou pular (jejum)"
  no café). Use `isFastDay`, `fastWindow`, `mealFasted` e `activeMeals` — refeição fora
  da janela **não é pulada**: sai de `calcScore`, das estatísticas do Progresso e do
  modo `day` do coach (vai no contexto com `jejum:true`). A tela Mais › Jejum
  (`renderJejum`) tem as fontes científicas e as contraindicações.
- **Variantes do plano** — só `isFds` (fim de semana) existe. `cleanMealPlan()` tira
  na leitura as variantes antigas `jantarV=*` (Rap10/Hambúrguer) e `almocoCarb`, e
  regrava o `__mealplan__` limpo quando vem do servidor. Atenção ao resolver conflito
  com ramos antigos: um merge já trouxe o seletor de jantar de volta uma vez.
- `getSups()` não filtra por dia: todo suplemento aparece todo dia (o campo
  `showOn` de dado antigo é ignorado).
- O score do dia (`calcScore`) não conta treino. `dayData` não tem mais
  `tr`/`trs`/`gymDurMin` (dia antigo que ainda os tenha só carrega campos mortos).
- Metas (`goalsDefs`) não têm mais vínculo com treino (`linkedWorkout`); meta
  antiga com o campo vira meta de registro manual.

Backend: **uma action só, `coach` (POST)**, com `mode` = `chat | swap | flex | day`.
O frontend manda o contexto inteiro em `context` (`coachContext()`) — o Lambda não
lê o DynamoDB nessa action. Todas as respostas passam por `_coach_meal()`, que
descarta refeição com id inválido ou sem descrição.

## Convenções do Lambda

Ações especiais no Lambda usam `?action=<nome>`. As que existem hoje:

| Action | O que faz |
|---|---|
| `analyze` (POST) | extrai suplementos (`context=supplements`) ou plano alimentar (`context=meal_plan`) de PDF/imagem/texto via Bedrock |
| `coach` (POST) | coach alimentar: `mode` chat (conversa), swap (3 opções para trocar uma refeição), flex (encaixar um extra e reajustar o dia), day (cardápio do dia) |
| `estimate_food` | estima macros de refeição livre (texto ou foto) via Bedrock |
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
`__mealplan__`, `__csups__`, `__goals__`, `__goalsdefs__`, `__goallogs__`, `__body__`,
`__habits__`, `__foodprofile__`. Legado de treino, sem leitura no app: `__gymplan__`,
`__workouts__`, `__weekplan__`, `__periodization__` e as sessões `gym:<data>:<treino>`.

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
`Scan` e `Query`, nas três tabelas (`tracker-habitos-data`, `exercise-cache` — sem
uso desde a remoção do treino — e `tracker-habitos-push-subscriptions`). O `Query` entrou junto com o
`history_range`; o `BatchWriteItem`, junto com o `delete_account`.

Policy `BedrockAccess`: `bedrock:InvokeModel` com `"*"`.

**Gap conhecido e ainda aberto:** `get_uid()` chama `GetUser` no Cognito a cada
request (~100–200 ms extras). Validar a assinatura do JWT localmente, com JWKS
em cache, dispensaria a maioria dessas chamadas.

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

⚠️ O passo "Atualizar RAPIDAPI_KEY" (resto da época do treino — a chave não é mais
lida pelo código) usa `update-function-configuration
--environment`, que **substitui o mapa inteiro de variáveis**, não faz merge. Toda
variável declarada no template precisa estar repetida lá, senão some a cada deploy.

### Chamadas ao Bedrock

Toda chamada passa por `bedrock_text(content, max_tokens, temperature=None)` —
não chame `bedrock.converse` direto. O helper registra o código de erro real da
AWS no CloudWatch antes de propagar; sem ele os erros sumiam nos `except` mudos.

⚠️ **`temperature=0` é inválido no Amazon Nova** — o mínimo aceito é `0.00001`
(a constante `NOVA_MIN_TEMP`). Passar `0` derruba a chamada inteira com
`ValidationException`. Foi o que já quebrou `estimate_food` em produção, enquanto as
chamadas que não mandavam `temperature` continuavam funcionando. O helper ainda repete a chamada sem `temperature` se o
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
