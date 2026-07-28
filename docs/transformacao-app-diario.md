# Transformação: de tracker para companheiro diário

> Diagnóstico do sistema atual + roadmap para tornar o app uma ferramenta prática de gestão do dia a dia (hábitos, dieta, treino, planners).
> Gerado em 2026-07-25 a partir da análise do código em `main`.

> ## ✅ Roadmap concluído (2026-07-28)
>
> **As cinco fases (A–E) foram entregues e estão no `main`.** Este documento passou
> a ser registro histórico: serve para entender *por que* cada peça existe, não para
> saber o que fazer a seguir.
>
> Do diagnóstico original, sobraram só dois gaps técnicos, ambos não bloqueantes:
> **G5** (cada request faz round-trip ao Cognito) e **G7** (arquivo único de ~5k
> linhas + Lambda inline no template).
>
> Trabalho posterior ao roadmap, já no `main`: integração ExerciseDB com GIF e
> instruções (PR #22) e normalização de acentos dos grupos musculares (PR #23).
>
> ⚠️ As referências de linha citadas na seção 2 são de `main` em 2026-07-25 e já
> não correspondem ao código atual.

---

## 1. O que o app já faz bem

- **Tracking sólido do dia:** refeições, água, sono, suplementos, treino — com score diário e streak.
- **Treino maduro:** plano A/B/C, log com herança do plano, periodização por blocos, identificação de exercícios via Bedrock com cache, tela Semana com heatmap muscular SVG e sugestão IA.
- **Metas flexíveis:** 12 categorias, 5 frequências, log rápido, previsão de conclusão.
- **Infra enxuta e barata:** S3 + CloudFront + Lambda + DynamoDB + Cognito, tudo em CloudFormation com CI/CD. Push diário via EventBridge.

O app já cobre bem o **registro** (olhar para trás). O que falta para virar gestão prática do dia a dia é o **planejamento** (olhar para frente) e uma fundação de dados confiável.

*(Era esse o diagnóstico de 2026-07-25. As duas lacunas foram fechadas: a fundação
na Fase A, o planejamento nas Fases B e E.)*

---

## 2. Gaps técnicos encontrados (com referência no código)

> **Situação em 2026-07-28:** G1, G2, G3, G4 e G6 foram corrigidos na Fase A
> (PR #13). Continuam abertos apenas **G5** e **G7**, nenhum bloqueante. O
> diagnóstico abaixo é do estado original — as referências de linha são de
> `main` em 2026-07-25 e já não batem com o código atual.

### G1 — Perda de dados em edição offline (crítico) ✅ corrigido
`render()` em `habit-tracker.html` (~linha 2871): carrega o dia do localStorage, busca o remoto e, **se o remoto for diferente, o remoto sempre vence** e sobrescreve o local. Como `saveDay()` (~2813) faz o PUT com `.catch(()=>{})` sem fila de retry, uma edição feita offline nunca chega ao servidor — e ao reconectar, o estado remoto (mais antigo) apaga a edição local.
**Correção:** outbox de sincronização (fila de PUTs pendentes em localStorage, reenviada no evento `online`) + merge por `updatedAt` em vez de "remoto vence".

### G2 — PWA não abre offline ✅ corrigido
`sw.js` não tem handler de `fetch` nem cache do app shell. O app instalado como PWA depende 100% da rede para carregar (o "offline via localStorage" do README só vale para o arquivo aberto localmente).
**Correção:** cache-first do shell (`index.html`, `icon.svg`, `manifest.json`) com atualização em background.

### G3 — Histórico não sincroniza entre dispositivos ✅ corrigido
`showHistory()` (~3572) monta os 60 dias só com `loadDay()` (localStorage). Num dispositivo novo, o histórico aparece vazio mesmo com tudo salvo no DynamoDB. Causa raiz: IAM só permite `GetItem`/`PutItem` — sem `dynamodb:Query` não dá para listar os dias de um usuário.
**Correção:** adicionar `dynamodb:Query` na policy + `action=history_range` no Lambda (Query por `userId` com `date BETWEEN`), hidratando o cache local.

### G4 — Falhas de sync são invisíveis ✅ corrigido
Todos os `fetch` de sincronização engolem erros silenciosamente (`catch{}`). O usuário não tem como saber se está olhando dado desatualizado ou se uma gravação falhou.
**Correção:** indicador discreto de estado de sync (sincronizado / pendente / offline) no header.

### G5 — Latência: toda chamada API faz round-trip ao Cognito ⏳ em aberto
`get_uid()` no Lambda chama `GetUser` no Cognito a cada request (~100–200 ms extras). Com validação local da assinatura do JWT (JWKS cacheado), a maioria das chamadas dispensaria isso.

### G6 — Sem exportação/backup de dados ✅ corrigido
Não há como o usuário exportar seus dados (CSV/JSON). Para um app pessoal com anos de registros, é um risco e uma limitação.

### G7 — Manutenibilidade ⏳ em aberto
4.043 linhas num único HTML e o Lambda inline no `template.yaml`. Funciona, mas cada feature nova fica mais cara. Não bloqueia o roadmap, mas vale ao menos separar o Lambda em arquivo próprio (como já foi feito com `push-sender/`).

*Atualização 2026-07-28:* o gap cresceu — `habit-tracker.html` está em **4.969 linhas**
e o Lambda inline passa de 275 linhas dentro do `template.yaml`. Continua não
bloqueante, mas é o candidato mais óbvio a próximo trabalho técnico.

### Já conhecido e aceito
- localStorage sem prefixo de usuário (documentado no CLAUDE.md — ok para app pessoal).

---

## 3. Gaps de produto para "gestão prática do dia a dia"

> **Todos os seis foram fechados.** A coluna "Situação original" é o diagnóstico de
> 2026-07-25, mantido como registro do porquê de cada fase.

| # | Gap | Situação original | Fechado em |
|---|---|---|---|
| P1 | **Sem planner** — o app registra o que aconteceu, mas não ajuda a planejar o dia/semana | Tela Hoje é checklist retroativo | PR #15 (timeline "Meu Dia") + #16 (plano semanal) |
| P2 | **Hábitos genéricos de checklist diário** (meditar, ler, alongar…) não têm lugar natural | Só via Metas, cuja UX é de progresso numérico, não de check diário com streak individual | PR #14 (`__habits__`) |
| P3 | **Dieta rígida** — só o plano fixo de refeições com variantes | Não dá para registrar "comi X fora do plano" nem estimar macros de um prato livre | PR #18 (`estimate_food`) |
| P4 | **Macros incompletos** | Só kcal e proteína; sem carboidrato/gordura | PR #18 |
| P5 | **Sem visão mensal/tendências** | Histórico é só calendário de % — não cruza peso × treino × dieta | PR #20 (Relatório Mensal) |
| P6 | **Push único diário** | Sem lembrete por item/horário (água de 2 em 2h, suplemento às 8h, treino às 18h) | PR #21 (`habits_due_now`) |

---

## 4. Roadmap proposto

### Fase A — Fundação confiável ✅ (PR #13)
Os dados são o ativo do app; havia risco real de perda (G1).
- [x] Outbox de sync + merge por timestamp (G1)
- [x] Service worker com cache do shell → PWA abre offline (G2)
- [x] `dynamodb:Query` + `action=history_range` → histórico multi-dispositivo (G3)
- [x] Indicador de estado de sync no header (G4) — `updateSyncStatus()`, mostra
      "✓ sincronizado" / "↻ sincronizando N…" / "⚡ offline · N na fila"
- [x] `action=export` → download de todos os dados (G6)

> **Status (2026-07-28):** Fases A, B, C, D e E entregues e mescladas no `main`,
> incluindo os dois itens de push que estavam pendentes (PR #21). Do roadmap
> original **nada segue em aberto**. Os únicos gaps vivos são o G5 (latência do
> Cognito) e o G7 (manutenibilidade), ambos descritos abaixo e nenhum deles
> bloqueante.

### Fase B — Planner "Meu Dia" + hábitos customizados ✅ (PRs #14, #15, #16, #21)
O coração da transformação pedida.
- [x] Tela Hoje reorganizada como **timeline do dia** (manhã / tarde / noite): refeições planejadas, treino do dia, suplementos e hábitos no horário de cada um — vira um plano a executar, não só um checklist — PR #15 (`_PERIODS` + `buildDayPlanItems`, com destaque do próximo item do dia)
- [x] **Hábitos customizados** (`__habits__`): nome, ícone, frequência (dias da semana), horário sugerido; check diário com streak individual — entra no score do dia — PR #14
- [x] **Planejamento semanal** (`__weekplan__`): na tela Semana, montar a semana (qual treino em qual dia) — o planner diário lê esse plano — PR #16
- [x] Lembretes push por hábito/horário (P6) — PR #21: `habits_due_now()` no `push-sender` lê os hábitos previstos para hoje no horário atual e ainda não feitos, independente do `reminderHour`

### Fase C — Dieta 2.0 ✅ (PR #18)
- [x] Registro rápido de refeição livre: texto ("2 ovos e uma banana") ou **foto do prato** → Bedrock estima kcal/prot/carb/gordura (`action=estimate_food`)
- [x] Macros completos no dia e no resumo semanal (P4)
- [x] Aderência à dieta na tela Semana (card "Macros da Semana")

### Fase D — Relatórios & IA proativa ✅ (PR #20)
- [x] Relatório mensal: peso × treino × dieta × consistência (tela "Relatório Mensal" em Mais, com navegação por mês)
- [x] Sugestão diária no planner: card "Seu Dia" na tela Hoje — plano do dia, grupo muscular descansado, proteína da semana (regra-based, offline)
- [x] Insight no push matinal: em vez de lembrete genérico, resumo do plano do dia (treino previsto + hábitos pendentes) — PR #21

### Fase E — Agenda & Lembretes externos ✅ (PR #19, caminho leve)
Levar o planner para a agenda que a pessoa já usa, **sem OAuth e sem backend novo** — 100% no cliente, cada evento aprovado pela própria pessoa no calendário dela.
- [x] Geração de arquivos **`.ics` (iCalendar)** — eventos recorrentes por `RRULE` a partir de hábitos, refeições e do plano semanal (`__weekplan__`)
- [x] Botões **"Adicionar à agenda"** — link `calendar.google.com/render` (Google) + download `.ics` (Apple/Outlook/qualquer)
- [x] Exportar **um item** ou **a semana toda**
- [x] `VALARM` opcional para lembrete 10 min antes
- [x] Sem mudança no `template.yaml`, sem OAuth. Alternativa futura: sincronização de mão dupla via Google Calendar API (OAuth) — possível Fase E-2.

Nota histórica: os **lembretes push por hábito/horário** e o **insight no push matinal** foram os dois últimos itens a fechar, e entraram juntos na branch `feature/lembretes-push` (PR #21), como previsto aqui.

### Ordem recomendada
**A → B → C → D → E** — todas entregues. A Fase E foi independente de C/D.

---

## 5. Decisões de arquitetura para as fases

- Novos dados de config seguem o padrão de "datas especiais": `__habits__`, `__weekplan__` (planejamento semanal), `__foodlog__` fica **dentro do dia** (`data.foods[]`), não em chave separada.
- Novos endpoints seguem `?action=`: `history_range`, `export`, `estimate_food` — sem infra nova além do IAM `Query`.
- **Agenda (Fase E)** é totalmente client-side: geração de `.ics` e links de calendário em JS puro, sem endpoint novo, sem OAuth.
- Nada de framework: mantém HTML/JS puro, single file, que é a identidade do projeto.
