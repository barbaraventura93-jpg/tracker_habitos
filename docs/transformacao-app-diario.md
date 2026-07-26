# Transformação: de tracker para companheiro diário

> Diagnóstico do sistema atual + roadmap para tornar o app uma ferramenta prática de gestão do dia a dia (hábitos, dieta, treino, planners).
> Gerado em 2026-07-25 a partir da análise do código em `main`.

---

## 1. O que o app já faz bem

- **Tracking sólido do dia:** refeições, água, sono, suplementos, treino — com score diário e streak.
- **Treino maduro:** plano A/B/C, log com herança do plano, periodização por blocos, identificação de exercícios via Bedrock com cache, tela Semana com heatmap muscular SVG e sugestão IA.
- **Metas flexíveis:** 12 categorias, 5 frequências, log rápido, previsão de conclusão.
- **Infra enxuta e barata:** S3 + CloudFront + Lambda + DynamoDB + Cognito, tudo em CloudFormation com CI/CD. Push diário via EventBridge.

O app já cobre bem o **registro** (olhar para trás). O que falta para virar gestão prática do dia a dia é o **planejamento** (olhar para frente) e uma fundação de dados confiável.

---

## 2. Gaps técnicos encontrados (com referência no código)

### G1 — Perda de dados em edição offline (crítico)
`render()` em `habit-tracker.html` (~linha 2871): carrega o dia do localStorage, busca o remoto e, **se o remoto for diferente, o remoto sempre vence** e sobrescreve o local. Como `saveDay()` (~2813) faz o PUT com `.catch(()=>{})` sem fila de retry, uma edição feita offline nunca chega ao servidor — e ao reconectar, o estado remoto (mais antigo) apaga a edição local.
**Correção:** outbox de sincronização (fila de PUTs pendentes em localStorage, reenviada no evento `online`) + merge por `updatedAt` em vez de "remoto vence".

### G2 — PWA não abre offline
`sw.js` não tem handler de `fetch` nem cache do app shell. O app instalado como PWA depende 100% da rede para carregar (o "offline via localStorage" do README só vale para o arquivo aberto localmente).
**Correção:** cache-first do shell (`index.html`, `icon.svg`, `manifest.json`) com atualização em background.

### G3 — Histórico não sincroniza entre dispositivos
`showHistory()` (~3572) monta os 60 dias só com `loadDay()` (localStorage). Num dispositivo novo, o histórico aparece vazio mesmo com tudo salvo no DynamoDB. Causa raiz: IAM só permite `GetItem`/`PutItem` — sem `dynamodb:Query` não dá para listar os dias de um usuário.
**Correção:** adicionar `dynamodb:Query` na policy + `action=history_range` no Lambda (Query por `userId` com `date BETWEEN`), hidratando o cache local.

### G4 — Falhas de sync são invisíveis
Todos os `fetch` de sincronização engolem erros silenciosamente (`catch{}`). O usuário não tem como saber se está olhando dado desatualizado ou se uma gravação falhou.
**Correção:** indicador discreto de estado de sync (sincronizado / pendente / offline) no header.

### G5 — Latência: toda chamada API faz round-trip ao Cognito
`get_uid()` no Lambda chama `GetUser` no Cognito a cada request (~100–200 ms extras). Com validação local da assinatura do JWT (JWKS cacheado), a maioria das chamadas dispensaria isso.

### G6 — Sem exportação/backup de dados
Não há como o usuário exportar seus dados (CSV/JSON). Para um app pessoal com anos de registros, é um risco e uma limitação.

### G7 — Manutenibilidade
4.043 linhas num único HTML e o Lambda inline no `template.yaml`. Funciona, mas cada feature nova fica mais cara. Não bloqueia o roadmap, mas vale ao menos separar o Lambda em arquivo próprio (como já foi feito com `push-sender/`).

### Já conhecido e aceito
- localStorage sem prefixo de usuário (documentado no CLAUDE.md — ok para app pessoal).

---

## 3. Gaps de produto para "gestão prática do dia a dia"

| # | Gap | Situação atual |
|---|---|---|
| P1 | **Sem planner** — o app registra o que aconteceu, mas não ajuda a planejar o dia/semana | Tela Hoje é checklist retroativo |
| P2 | **Hábitos genéricos de checklist diário** (meditar, ler, alongar…) não têm lugar natural | Só via Metas, cuja UX é de progresso numérico, não de check diário com streak individual |
| P3 | **Dieta rígida** — só o plano fixo de refeições com variantes | Não dá para registrar "comi X fora do plano" nem estimar macros de um prato livre |
| P4 | **Macros incompletos** | Só kcal e proteína; sem carboidrato/gordura |
| P5 | **Sem visão mensal/tendências** | Histórico é só calendário de % — não cruza peso × treino × dieta |
| P6 | **Push único diário** | Sem lembrete por item/horário (água de 2 em 2h, suplemento às 8h, treino às 18h) |

---

## 4. Roadmap proposto

### Fase A — Fundação confiável (fazer primeiro)
Os dados são o ativo do app; hoje há risco real de perda (G1).
- [ ] Outbox de sync + merge por timestamp (G1)
- [ ] Service worker com cache do shell → PWA abre offline (G2)
- [ ] `dynamodb:Query` + `action=history_range` → histórico multi-dispositivo (G3)
- [ ] Indicador de estado de sync no header (G4)
- [ ] `action=export` → download JSON/CSV de todos os dados (G6)
- Sem tela nova; risco baixo; destrava tudo que vem depois.

> **Status (2026-07-26):** Fases A, B, C, D, E entregues e mescladas no `main`. Pendente apenas o item opcional de **lembretes push por hábito/horário**. Detalhes de cada PR na memória do projeto.

### Fase B — Planner "Meu Dia" + hábitos customizados
O coração da transformação pedida.
- [ ] Tela Hoje reorganizada como **timeline do dia** (manhã / tarde / noite): refeições planejadas, treino do dia, suplementos e hábitos no horário de cada um — vira um plano a executar, não só um checklist *(parcial: card "Seu Dia" com sugestão proativa entregue na Fase D; timeline por período ainda não)*
- [x] **Hábitos customizados** (`__habits__`): nome, ícone, frequência (dias da semana), horário sugerido; check diário com streak individual — entra no score do dia — PR #14
- [x] **Planejamento semanal** (`__weekplan__`): na tela Semana, montar a semana (qual treino em qual dia) — o planner diário lê esse plano — PR #16
- [ ] Lembretes push por hábito/horário (P6) — o `push-sender` já roda de hora em hora; basta ler os horários dos hábitos do usuário *(opcional, ainda pendente)*

### Fase C — Dieta 2.0 ✅ (PR #18)
- [x] Registro rápido de refeição livre: texto ("2 ovos e uma banana") ou **foto do prato** → Bedrock estima kcal/prot/carb/gordura (`action=estimate_food`)
- [x] Macros completos no dia e no resumo semanal (P4)
- [x] Aderência à dieta na tela Semana (card "Macros da Semana")

### Fase D — Relatórios & IA proativa ✅ (PR desta branch)
- [x] Relatório mensal: peso × treino × dieta × consistência (tela "Relatório Mensal" em Mais, com navegação por mês)
- [x] Sugestão diária no planner: card "Seu Dia" na tela Hoje — plano do dia, grupo muscular descansado, proteína da semana (regra-based, offline)
- [ ] Insight no push matinal: em vez de lembrete genérico, resumo do plano do dia *(pendente — depende de editar o push-sender)*

### Fase E — Agenda & Lembretes externos ✅ (PR #19, caminho leve)
Levar o planner para a agenda que a pessoa já usa, **sem OAuth e sem backend novo** — 100% no cliente, cada evento aprovado pela própria pessoa no calendário dela.
- [x] Geração de arquivos **`.ics` (iCalendar)** — eventos recorrentes por `RRULE` a partir de hábitos, refeições e do plano semanal (`__weekplan__`)
- [x] Botões **"Adicionar à agenda"** — link `calendar.google.com/render` (Google) + download `.ics` (Apple/Outlook/qualquer)
- [x] Exportar **um item** ou **a semana toda**
- [x] `VALARM` opcional para lembrete 10 min antes
- [x] Sem mudança no `template.yaml`, sem OAuth. Alternativa futura: sincronização de mão dupla via Google Calendar API (OAuth) — possível Fase E-2.

Nota: os **lembretes push por hábito/horário** e o **insight no push matinal** são os dois itens que restam — ambos mexem no `push-sender` e podem entrar juntos numa branch "lembretes".

### Ordem recomendada
**A → B → C → D → E** — todas entregues. A Fase E foi independente de C/D.

---

## 5. Decisões de arquitetura para as fases

- Novos dados de config seguem o padrão de "datas especiais": `__habits__`, `__weekplan__` (planejamento semanal), `__foodlog__` fica **dentro do dia** (`data.foods[]`), não em chave separada.
- Novos endpoints seguem `?action=`: `history_range`, `export`, `estimate_food` — sem infra nova além do IAM `Query`.
- **Agenda (Fase E)** é totalmente client-side: geração de `.ics` e links de calendário em JS puro, sem endpoint novo, sem OAuth.
- Nada de framework: mantém HTML/JS puro, single file, que é a identidade do projeto.
