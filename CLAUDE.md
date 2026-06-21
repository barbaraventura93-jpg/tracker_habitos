# tracker_habitos — Contexto para Claude Code

## Arquitetura atual

- **Frontend:** HTML/CSS/JS puro, single file (`habit-tracker.html`), hospedado em S3 + CloudFront
- **Backend:** AWS Lambda (Python 3.12) com Function URL — single function, discriminada por `?action=`
- **DB:** DynamoDB `tracker-habitos-data` — PK `userId` (string) + SK `date` (string)
- **Auth:** AWS Cognito — Lambda extrai `userId` do `AccessToken` via `GetUser`
- **Infra como código:** `infrastructure/template.yaml` (CloudFormation)
- **CI/CD:** GitHub Actions — push em `main` → CloudFormation update → deploy S3 → invalidação CloudFront

## Multi-usuário

O app **já é multi-usuário**: cada request carrega `Bearer <token>`, o Lambda valida no Cognito e usa o `uid` retornado como PK no DynamoDB. Dados de usuários diferentes são isolados por design.

Único ponto cego: `localStorage` usa chaves sem prefixo de usuário (`ht:2026-06-18`, `ht:token`, etc.). Se dois usuários usarem o mesmo navegador, o segundo vê o cache do primeiro até a API responder. Aceitável para um app pessoal — não precisa corrigir agora.

## Convenções do Lambda

Ações especiais no Lambda usam `?action=<nome>`. Exemplos já existentes:
- `action=analyze` + POST: extrai exercícios/suplementos de PDF/imagem via Bedrock

"Datas especiais" no DynamoDB (não são datas reais, são chaves de config por usuário):
`__gymplan__`, `__workouts__`, `__csups__`, `__goals__`, `__goalsdefs__`, `__goallogs__`, `__body__`

## IAM — permissões atuais e gap

Policy `DynamoDBAccess` atual: só `GetItem` e `PutItem`.  
**Gap:** `week_summary` precisa buscar 7 dias de um usuário. Sem `dynamodb:Query`, a solução é 7 chamadas `GetItem` paralelas (suficiente para Fase 1).

Policy `BedrockAccess`: `bedrock:InvokeModel` com `"*"` — infra para Fase 3 já existe.

---

## Feature em desenvolvimento: Periodização Semanal Inteligente

**Branch:** `feature/semana` (saindo de `feature/design`)

### Decisões técnicas confirmadas

1. **Novos handlers entram como `?action=` no Lambda existente** — sem nova infra Lambda:
   - `?action=week_summary&date=2026-06-16` → retorna os 7 dias da semana que contém essa data
   - `?action=week_suggestion` → sugestão de treino via Bedrock (Fase 3)

2. **Cache de exercícios ExerciseDB → nova tabela DynamoDB** (`exercise-cache`)
   - Adicionar ao `template.yaml` com PK `exerciseName` (string) — sem `userId`, é global
   - Adicionar ao `template.yaml` apenas na Fase 2
   - **Não usar** `__cache__` como `userId` na tabela atual — gambiarra não escalável

3. **Mapa muscular → SVG estático com CSS dinâmico** — sem API externa
   - `muscle-visualizer.exercisedb.io` não tem documentação pública verificável
   - SVG com IDs nos grupos musculares + intensidade por CSS é a abordagem principal (não plano B)
   - Grupos já disponíveis nos logs: `Peito`, `Costas`, `Ombro`, `Biceps`, `Triceps`, `Perna`, `Core`, `Gluteo`, `Cardio`, `Outro`

4. **ExerciseDB free tier (100 req/dia)** — suficiente com cache, mas o cache é pré-requisito obrigatório antes de integrar

### Fases de implementação

**Fase 1 — sem API externa (esta branch `feature/semana`)**
- [ ] Tela "Semana" na nav inferior
- [ ] Busca de 7 dias via 7 `GetItem` paralelos no Lambda (`action=week_summary`)
- [ ] Cálculo de intensidade muscular baseado no campo `group` dos exercícios logados
  - Fórmula: `intensidade = Σ(séries × reps × peso)` por grupo muscular, normalizada 0–100
- [ ] SVG estático de silhueta humana com grupos musculares identificados por ID
- [ ] Colorização dinâmica do SVG por intensidade (verde → amarelo → laranja → vermelho)
- [ ] Sem mudança no `template.yaml`, sem nova tabela

**Fase 2 — nova branch após `feature/semana` entrar no main**
- [ ] Nova tabela `exercise-cache` no `template.yaml`
- [ ] `dynamodb:Query` no IAM policy
- [ ] Integração ExerciseDB: GIF + músculo preciso + instruções no momento do log
- [ ] Handler `action=identify_exercise&name=<nome>` com cache em DynamoDB

**Fase 3 — nova branch**
- [ ] `action=week_suggestion` via Bedrock com contexto semanal

### UX da tela Semana

- 7 cards de dias (Seg–Dom) mostrando: tipo de treino, grupos musculares trabalhados, duração
- Silhueta SVG com heatmap muscular da semana
- Indicador de músculo mais trabalhado e mais descansado
- Sugestão passiva: "Costas está em repouso há 5 dias"

---

## Comandos úteis

```bash
# Ver branches locais
git -C "c:\Users\barba\Local\tracker_habitos" branch

# Criar feature/semana a partir de feature/design (se ainda não existir)
git -C "c:\Users\barba\Local\tracker_habitos" checkout -b feature/semana feature/design

# Deploy (só funciona via push para main — CI/CD cuida do resto)
git push origin main
```
