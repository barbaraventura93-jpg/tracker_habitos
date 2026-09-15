# Backlog de usabilidade e IA — avaliação de estado

> Consolidação das anotações da Bárbara (set/2026) sobre o que incluir no backlog,
> cruzada com o código. Para cada ponto: **estado** e **onde está no código**.
>
> Legenda: ✅ entregue · 🟡 entregue com ressalva · ⬜ aberto

**Resumo.** Todos os 11 pontos anotados estão entregues. Os itens 8 e 9 (import de
treino por texto multi-dia e vários treinos por dia) foram entregues no **PR #48**; os
demais e as melhorias A–E deste documento estão no **PR #47** (este ramo), que
**complementa** o #48 sem reimplementar o que já está no `main`.

---

## 1. Botão para visualizar a senha na troca de senha — ✅ Entregue

Link "👁 Mostrar senhas" na troca de senha (`accTogglePw`). Estendido ao **login**
(`auth-password`) e à **redefinição "esqueci a senha"** via o helper genérico
`togglePwFields()` (Sugestão A, neste ramo).

## 2. IA para indicação de exercícios (objetivo, bioimpedância, semana, disclaimer) — ✅ Entregue

`generate_workout_plan` (backend) monta o treino a partir de objetivo, composição
corporal e séries da semana, com disclaimer de que não substitui profissional.

## 3. Agente de treinos (nº/semana, tempo, limite 1×/mês, editar depois, tela personal×IA) — ✅ Entregue

Tela `renderWorkoutGen`: inputs de treinos/semana e duração, limite 1×/mês
(`lastAiWorkoutGen`), dois caminhos (importar do personal × pedir à IA), preview
editável. **Ressalva fechada neste ramo:** o limite 1×/mês ganhou escape "Preciso
refazer agora" (Sugestão C).

## 4. Mesma lógica de IA para a alimentação — ✅ Entregue

`generate_meal_plan` + aceite (`aiMealOk`) + limite 1×/mês (`lastAiMealGen`).

## 5. Importação de treino por texto (segmentar exercício/séries/reps) — ✅ Entregue (PR #48)

`analyze`/`extract_workout_plan` segmentam texto colado em exercícios/treinos.

## 6. Importação de alimentação por texto (café/almoço/lanche…) — ✅ Entregue

`mpHandleText` com `context='meal_plan'`.

## 7. "Erro de sincronização no app" — ✅ Corrigida a causa provável

Conversão float→Decimal no `PUT` genérico (destravou o outbox); o indicador de sync
passou a mostrar a causa real (`_syncErr`).

## 8. Import de treino por texto FORA do bloco do treino (vários dias num texto) — ✅ Entregue (PR #48)

Backend `extract_workout_plan` segmenta um texto livre com vários treinos/dias; o
import saiu do bloco por-treino e foi para o Gerador de Treino (`importWorkoutText`),
reusando o preview multi-treino e a aplicação (`wgenApply`); não consome a cota mensal.

## 9. Vários treinos por dia + separar planejado × registrado — ✅ Entregue (PR #48)

`dayData.trs` (lista de treinos do dia); `dayData.tr` é o treino **em foco** no log, com
normalização retrocompatível. `plannedTrsForDow` retorna todos os treinos previstos e
`weekPlan[dow]` aceita string **ou lista**. O seletor da tela marca/desmarca treinos do
dia (`gymPickDay`/`gymRemoveDay`); heatmap e timeline agregam todas as sessões do dia.

**Complemento deste ramo (a limitação conhecida do #48).** O #48 anotou que
"score/insight/relatório consideram o treino em foco". Aqui isso foi **fechado**: um
helper `dayTrs(dd)` e as agregações passaram a somar **todos** os treinos do dia em
`calcScore` (score diário), `buildMonthReport` (relatório mensal), a varredura de grupo
descansado do `dailyInsightCard` e `getLastGymSession`.

## 10. IA alimentar considerar região + indicar macros — ✅ Entregue

Campo `regiao` enviado ao `generate_meal_plan` (prioriza alimentos acessíveis da região);
macros `kcal/prot/carb/fat` obrigatórios. **Ressalva fechada neste ramo:** se `regiao`
estiver vazio, o `genMealPlan` **pergunta** a cidade/estado e grava no perfil (Sugestão B;
só na dieta — o gerador de treino não usa região).

## 11. Composição corporal por data (retroativo) + import de bioimpedância — ✅ Entregue

Seletor de data no registro; `analyze_bio` extrai atual + histórico do laudo, com dedupe.

---

## Melhorias adicionais (surgiram na leitura do código)

- **A. "Mostrar senha" no login e no reset** — ✅ entregue neste ramo (`togglePwFields`).
- **B. Pedir a região quando faltar** — ✅ entregue neste ramo (`genMealPlan`).
- **C. Escape do limite de 1×/mês da IA** — ✅ entregue neste ramo: "Preciso refazer agora"
  nas telas de treino e dieta (`wgenForceRegen`/`mgenForceRegen`), sob confirmação.
- **D. Helper único de import por IA** — ✅ entregue neste ramo: `runAiImport()` concentra o
  fluxo comum; os importadores por `analyze` (treino/arquivo, dieta/arquivo e texto) passaram
  a usá-lo.
- **E. Dívida de documentação** — ✅ entregue neste ramo: a tabela de actions do `CLAUDE.md`
  foi completada com as ações de IA (`generate_workout_plan`, `extract_workout_plan`,
  `generate_meal_plan`, `analyze_bio`). Gaps de manutenibilidade ainda abertos, fora deste
  backlog: latência do `get_uid` no Cognito e o `habit-tracker.html` com ~6,5k linhas.

## O que resta

Nada dos 11 pontos. Aberto só um item de conforto do #48: `gymDurMin` (cardio) segue
escalar por dia — dois aeróbicos no mesmo dia compartilham a duração. Fora de escopo aqui.
