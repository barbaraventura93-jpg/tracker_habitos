# Backlog de usabilidade e IA — avaliação de estado

> Consolidação das anotações da Bárbara (set/2026) sobre o que incluir no backlog,
> cruzada com o código atual do repositório. Para cada ponto: **estado**, **onde está
> no código** e, quando aberto, **o que falta**.
>
> Legenda: ✅ entregue · 🟡 entregue com ressalva/gap menor · ⬜ aberto

Resumo: dos 11 pontos anotados, **8 já estão entregues** (o item 8 foi entregue neste
ramo), **2 estão entregues com um gap menor** e **1 continua aberto** (item 9, sobre a
relação treino ↔ semana). Boa parte foi entregue nos PRs #41–#46 e ainda **não estava
refletida no `CLAUDE.md`** — ver "Dívida de documentação" no fim.

---

## 1. Botão para visualizar a senha na troca de senha — ✅ Entregue

Link "👁 Mostrar senhas" na tela de troca de senha (`accTogglePw`).

- `habit-tracker.html:5082` (link) · commit `2f20d49`

**Gap menor de usabilidade:** o botão existe **só** na troca de senha (Mais › Conta).
As telas de **login** (`auth-password`, `habit-tracker.html:239`) e de **redefinição
"esqueci a senha"** (`forgot-newpass`/`forgot-confirmpass`, linhas 281–283) ainda não
têm o "mostrar senha" — que é justamente onde mais se erra a digitação. Ver Sugestão A.

## 2. IA para indicação de exercícios (objetivo, bioimpedância, semana, disclaimer) — ✅ Entregue

`generate_workout_plan` monta o treino a partir de **objetivo**, **composição corporal**
(peso/gordura/massa magra) e **séries já feitas na semana**, seguindo princípios de
volume/frequência/faixa de reps. O **disclaimer** de que não substitui profissional e de
que o app não se responsabiliza aparece na tela e antes de gerar.

- `infrastructure/api/index.py:206` (`generate_workout_plan`) · commit `8dbb4b8`
- `habit-tracker.html:5570` (`WGEN_DISCLAIMER`), `5620` (tela)

**Ressalva:** o prompt usa "princípios consolidados de treinamento de força", não cita
**estudos científicos** nomeados (que a anotação pedia). É uma escolha segura — citar
papers com um LLM arrisca referências inventadas. Se quiser reforçar, dá para adicionar
uma linha de contexto ("diretrizes tipo ACSM/NSCA") sem prometer citações verificáveis.

## 3. Agente de treinos: nº de treinos/semana, tempo, limite 1x/mês, edição posterior, tela de pedido (personal OU IA) — ✅ Entregue

Tudo o que a anotação pedia está na tela `renderWorkoutGen`:

- **Nº de treinos/semana** (`wgen-n`) e **duração por treino** (`wgen-min`) — `habit-tracker.html:5629`
- **Limite de 1× por mês**: `goals.lastAiWorkoutGen` vs `wgenMonthKey()`, com aviso de
  "disponível novamente em …" — linhas `5601`, `5613`
- **Dois caminhos na mesma tela**: card "📄 Já tenho treino do meu personal" (importar) e
  "🤖 Pedir treino ao nosso agente de IA" — linha `5620`
- **Edição depois de gerar**: preview com checkboxes por exercício e `wgenApply` cria os
  treinos e os agenda na semana; a pessoa edita à vontade no plano — linhas `5575`, `5682`

**Ressalva:** o limite de 1×/mês é **client-side** (localStorage). Não é um controle de
verdade (limpar dados do navegador reabre), e também não há um "quero refazer mesmo assim".
Aceitável para o objetivo (evitar trocar treino toda semana), só registrando a limitação.

## 4. Mesma lógica de IA para a alimentação — ✅ Entregue

`generate_meal_plan` espelha o gerador de treino: aceite do aviso (`goals.aiMealOk`),
limite 1×/mês (`goals.lastAiMealGen`), preview e aplicação.

- `infrastructure/api/index.py:273` · `habit-tracker.html:5416` (`mgenAccept`), `5417` (`genMealPlan`)
- commits `de12cea`, `84bba43`

## 5. Importação de treino por texto (bloco único, app segmenta exercício/séries/reps) — ✅ Entregue (ver item 8)

`analyzeTextViaLambda` + `call_ai` com `text=` segmentam um texto colado em
exercícios com grupo/séries/reps. Campo "Ou cole o treino em texto…".

- `habit-tracker.html:1193`, `2516` (textarea), `2656` (`handleGymPlanText`)
- `infrastructure/api/index.py:86` (ramo `if text:` do `call_ai`)

**Mas:** hoje esse campo vive **dentro do card de um treino específico** e a IA devolve
uma **lista plana** de exercícios — não separa por dia. É exatamente o que o item 8 pede
corrigir.

## 6. Importação de alimentação por texto (segmenta café/almoço/lanche… e quantidades) — ✅ Entregue

`mpHandleText` manda o texto com `context='meal_plan'`; o prompt distribui em
`cafe/almoco/lanche/jantar/ceia` com macros por refeição.

- `habit-tracker.html:5401` · `infrastructure/api/index.py:71` (prompt `meal_plan`)

## 7. "Está constando erro de sincronização no app" — ✅ Causa provável corrigida (verificar)

O erro mais provável era o `PUT` genérico mandando `float` para o DynamoDB, que **recusa
float** e travava a fila inteira do outbox. Corrigido convertendo para `Decimal`
(commit `8857107`, `infrastructure/api/index.py:575`).

Além disso, o indicador de sincronização agora **mostra a causa real** em vez de ficar
eternamente em "sincronizando…": `flushOutbox` guarda `_syncErr` e o `sync-status`
exibe a mensagem (sessão expirada, app desatualizado, falha de rede…).

- `habit-tracker.html:4276` (`_syncErr`), `4280` (`flushOutbox`), `4330` (exibição)

**Ação:** se o erro voltar a aparecer, anotar **a mensagem exata** do indicador — ela
aponta a causa (auth / versão / rede / API), o que era impossível antes.

## 8. Importação de treino por texto FORA do bloco do treino (um texto com vários dias) — ✅ Entregue (neste ramo)

O importador por texto de **vários dias** agora vive na tela do Gerador de Treino
(`showWorkoutGen`), **fora** de qualquer card de treino específico, no cartão "📄 Já tenho
treino do meu personal". A pessoa cola um bloco único (ex.: "Treino A segunda… / Treino B
quarta…"), a IA **segmenta em treinos distintos** e o resultado passa pelo **mesmo preview
e apply** do gerador de IA — criando vários treinos de uma vez e agendando-os na semana.

- Backend: `segment_workout_text` (`infrastructure/api/index.py`) + action
  `segment_workout_text`; devolve `{"workouts":[{name,exercises}]}` reusando o saneamento
  `_clean_workouts` compartilhado com `generate_workout_plan`. O prompt **não inventa**
  exercícios — só organiza o que está no texto.
- Frontend: `wgenImportText()` + textarea global no cartão do personal (`habit-tracker.html`,
  `renderWorkoutGen`); reusa `_wgenPreview`/`wgenApply`. Importar o próprio treino **não
  gasta** a cota de 1×/mês da geração por IA (flag `_wgenIsImport`).

O importador por texto **dentro** de um treino específico (`gym-import-text`,
`habit-tracker.html:2516`) foi mantido — serve ao caso diferente de "colar exercícios num
treino que já existe". O caminho multi-dia é o novo, global.

## 9. App se perde entre treino cadastrado × planejado na semana; permitir >1 treino por dia — ⬜ Aberto

Limitação **estrutural**: cada dia guarda **um** treino só.

- Plano da semana: `weekPlan[String(dow)]` = **um** id de treino (`habit-tracker.html:1775`).
- Dia registrado: `dayData.tr` = **um** treino (`renderGym`, linha `1825`).

Não há como ter "Musculação de manhã + corrida à noite" no mesmo dia, e a diferença entre
o **planejado** (template `weekPlan`) e o **registrado** (`dd.tr`) não fica clara na tela.

**O que falta (proposta):**
1. Migrar `weekPlan[dow]` e `dayData.tr` de `string` → `array` de treinos, com fallback
   de leitura para o formato antigo (curar dado gravado, como já se faz com `canonGroup`).
   Toda leitura de `weekPlan`/`.tr` precisa passar a aceitar os dois formatos.
2. Na tela do dia, separar visualmente "**Planejado para hoje**" (vem da semana) de
   "**Treinos de hoje**" (registrados), com botão de "adicionar outro treino ao dia".
3. Heatmap e `weekMuscleSets` (`habit-tracker.html:5560`) já somam por sessão — só precisam
   iterar sobre a lista de treinos do dia em vez de um único `tr`.

É o item de maior esforço da lista (mexe no modelo de dados e em várias telas). Sugiro
tratá-lo como uma fase própria, com migração de dados cuidadosa.

## 10. IA alimentar considerar região + sempre indicar macros — ✅ Entregue

- **Região:** campo `regiao` no perfil, nas metas e no onboarding; enviado ao
  `generate_meal_plan`, que prioriza alimentos acessíveis na região (senão, "no Brasil").
  - `infrastructure/api/index.py:283`/`291` · `habit-tracker.html:3101`, `3886`, `5429`
- **Macros:** o prompt exige `kcal/prot/carb/fat` inteiros e **> 0** por refeição
  ("Nunca deixe um macro em 0 ou vazio", `index.py:300`).

**Gap menor:** se `regiao` estiver vazio, o gerador **não pergunta** — apenas assume Brasil.
A anotação pedia "se não tiver no cadastro, deve ser pedido". Ver Sugestão B.

## 11. Composição corporal: dados retroativos por data + import de exame de bioimpedância (atual e histórico) — ✅ Entregue

- **Registro por data (retroativo):** seletor de data `bc-date` (limitado a hoje) no
  formulário de novo/atualizar registro; `pesoAtual` só é reescrito se a data for a mais
  recente. — `habit-tracker.html:2881`, `2907` (`bcIsLatestDate`)
- **Import do exame + leitura de histórico:** `analyze_bio` extrai **todas** as medições,
  inclusive a tabela de datas anteriores do laudo (InBody etc.), com dedupe por data e
  checkbox por medição (marcadas só as datas novas). — `infrastructure/api/index.py:371`,
  `habit-tracker.html:2870`, `2947` · commit `4fc97fa`

---

## Sugestões adicionais de usabilidade

Coisas que apareceram na leitura do código e valem entrar no backlog:

- **A. "Mostrar senha" no login e no reset** — replicar o toggle do item 1 em
  `auth-password` e nos campos de "esqueci a senha". Baixo esforço, alto retorno (é onde
  a digitação errada mais trava a pessoa).
- **B. Pedir a região quando faltar** — no `genMealPlan`/`genWorkoutPlan`, se `goals.regiao`
  estiver vazio, abrir um mini-prompt antes de chamar a IA, gravando em `goals.regiao`.
  Fecha o intento do item 10.
- **C. "Refazer treino/dieta mesmo assim"** — o limite 1×/mês não tem escape legítimo.
  Um link discreto "preciso refazer agora" (com confirmação) evita frustração sem abrir mão
  do objetivo de estabilidade.
- **D. Unificar os dois importadores por texto** — treino (item 8) e dieta já compartilham
  o `analyze`; vale um componente único de "colar texto" reutilizado nas duas telas.
- **E. Dívida de documentação (manutenibilidade)** — o `CLAUDE.md` **não menciona**
  `generate_workout_plan`, `generate_meal_plan` nem `analyze_bio`, e a tabela de actions está
  desatualizada. Como o próprio `CLAUDE.md` é o contexto de quem for mexer aqui depois,
  atualizá-lo é barato e evita retrabalho. (Gaps já conhecidos e ainda abertos: latência do
  `get_uid` no Cognito e o `habit-tracker.html` com ~6,5k linhas.)

## Priorização sugerida

1. **Item 9** — o único ainda aberto e o que a pessoa mais sente no uso ("o app se perde").
   É o de maior esforço (mexe no modelo de dados: `weekPlan[dow]`/`dayData.tr` de único → lista).
2. **Sugestões A e B** — rápidas, fecham gaps menores dos itens 1 e 10.
3. **Sugestão C** — melhoria de conforto, quando sobrar espaço.

> Item 8 e a Sugestão E (documentar as actions de IA no `CLAUDE.md`) foram entregues
> neste ramo.
