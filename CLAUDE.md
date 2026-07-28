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

## Arquitetura atual

- **Frontend:** HTML/CSS/JS puro, single file (`habit-tracker.html`), hospedado em S3 + CloudFront
- **Backend:** AWS Lambda (Python 3.12) com Function URL — single function, discriminada por `?action=`. Código em `infrastructure/api/index.py`, empacotado em zip pelo workflow e publicado em `s3://tracker-habitos/lambda-builds/api.zip`
- **DB:** DynamoDB `tracker-habitos-data` — PK `userId` (string) + SK `date` (string)
- **Auth:** AWS Cognito — Lambda extrai `userId` do `AccessToken` via `GetUser`
- **Infra como código:** `infrastructure/template.yaml` (CloudFormation)
- **CI/CD:** GitHub Actions — push em `main` → CloudFormation update → deploy S3 → invalidação CloudFront

## Multi-usuário

O app **já é multi-usuário**: cada request carrega `Bearer <token>`, o Lambda valida no Cognito e usa o `uid` retornado como PK no DynamoDB. Dados de usuários diferentes são isolados por design.

Único ponto cego: `localStorage` usa chaves sem prefixo de usuário (`ht:2026-06-18`, `ht:token`, etc.). Se dois usuários usarem o mesmo navegador, o segundo vê o cache do primeiro até a API responder. Aceitável para um app pessoal — não precisa corrigir agora.

## Convenções do Lambda

Ações especiais no Lambda usam `?action=<nome>`. As que existem hoje:

| Action | O que faz |
|---|---|
| `analyze` (POST) | extrai exercícios/suplementos/plano alimentar de PDF/imagem via Bedrock |
| `identify_exercise` | grupo + músculos + GIF + instruções de um exercício, com cache |
| `estimate_food` | estima macros de refeição livre (texto ou foto) via Bedrock |
| `week_suggestion` | sugestão de treino para os dias restantes da semana |
| `history_range` | Query por `userId` com `date BETWEEN` — hidrata o histórico num dispositivo novo |
| `export` | download de todos os dados do usuário |
| `save_push_subscription` / `delete_push_subscription` | inscrição Web Push |

"Datas especiais" no DynamoDB (não são datas reais, são chaves de config por usuário):
`__gymplan__`, `__workouts__`, `__mealplan__`, `__csups__`, `__goals__`, `__goalsdefs__`,
`__goallogs__`, `__body__`, `__habits__`, `__weekplan__`, `__periodization__`

## IAM

Policy `DynamoDBAccess`: `GetItem`, `PutItem` e `Query`, nas duas tabelas
(`tracker-habitos-data` e `exercise-cache`). O `Query` entrou junto com o
`history_range`.

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

## Comandos úteis

```bash
# Deploy: só acontece via push para main — o CI/CD cuida do resto
git push origin main
```

O workflow `Deploy to S3` **não roda em pull requests**, só em push para `main`.
PRs não têm checks — a validação antes do merge é manual.
