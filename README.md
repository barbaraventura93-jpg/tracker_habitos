# 📋 Rotina Diária

App de acompanhamento de rotina diária — refeições, água, suplementos, sono, treino e metas personalizadas — com sincronização entre dispositivos e histórico de 60 dias.

🌐 **[Acessar o app](https://d1o1gejacy6m9o.cloudfront.net)**

---

## Funcionalidades

- Cadastro e login com e-mail/senha via AWS Cognito
- Dados sincronizados na nuvem — acessíveis em qualquer dispositivo
- Layout responsivo: sidebar lateral no desktop, barra inferior no mobile

### Hoje
- Marcação de refeições do dia com detalhes de macros
- Controle de água com indicador de copos, ml e litros consumidos/meta
- Suplementos com checklist configurável por tipo de dia (treino/descanso)
- Registro de sono (horas + horário consistente)
- Metas personalizadas com progresso em tempo real
- Score diário com anel de progresso, barras por categoria e pendências

### Treino
- Log de exercícios com séries, reps e kg
- Comparação automática com a última sessão do mesmo treino
- Campo de duração (⏱️ min) que alimenta as metas automaticamente
- Plano de treino por tipo (A/B/C) — separado por sessão, sem misturar dados
- Upload de plano via PDF ou imagem (interpretado via IA)
- % de sucesso do dia sobe automaticamente ao concluir séries

### Nutrição
- Controle de macros por refeição
- Metas de calorias calculadas automaticamente

### Suplementos
- Cadastro livre de suplementos com nome, dose, ícone e visibilidade (sempre / dia de treino / descanso)

### Metas Pessoais

Tela de configuração com cálculo automático baseado em evidências científicas:

| Meta | Fórmula | Referência |
|---|---|---|
| **Água** | Peso atual × 35 ml/kg → copos de 250 ml | EFSA & Institute of Medicine |
| **Calorias** | BMR (Mifflin-St Jeor) × fator de atividade ± ajuste de peso | ISSN / ACSM (2005) |

**Fator de atividade (TDEE):**
- 0–1 dias/semana → ×1,2 (sedentário)
- 2–3 dias → ×1,375 (leve)
- 4–5 dias → ×1,55 (moderado)
- 6–7 dias → ×1,725 (intenso)

**Ajuste de meta de peso:** −400 kcal (perda) / +300 kcal (ganho) / sem ajuste (manutenção).

#### Metas Personalizadas

Crie metas livres com frequência e acompanhamento automático:

- **Nome + ícone** configuráveis (ex: 🚴 Bike)
- **Unidade** livre (min, km, h, sessões…)
- **Frequência:** Diária / Semanal / Mensal
- **Vínculo com treino:** ao vincular a um tipo de treino, o progresso é lido automaticamente da duração registrada na sessão — sem entrada manual
- Barra de progresso e % de completude exibidos na tela Hoje

### Histórico
- Calendário dos últimos 60 dias com % diário
- Streak de dias acima de 80%, média geral e dias excelentes

---

## Tecnologias

- HTML5 + CSS3 + JavaScript puro (sem frameworks)
- Hospedagem: **AWS S3 + CloudFront**
- Autenticação: **AWS Cognito**
- Backend: **AWS Lambda + DynamoDB**
- Infraestrutura como código: **AWS CloudFormation**
- CI/CD: **GitHub Actions**

---

## Infraestrutura AWS

| Serviço | Uso | Custo |
|---|---|---|
| S3 | Hospedagem do arquivo estático | Free Tier |
| CloudFront | CDN + HTTPS + invalidação automática | Free Tier |
| Cognito | Autenticação de usuários | Free Tier (50k MAU) |
| DynamoDB | Persistência dos dados por usuário | Free Tier |
| Lambda | API de leitura/escrita dos dados | Free Tier |
| GitHub Actions | CI/CD automático no push | Gratuito |

**Bucket:** `tracker-habitos` · **Região:** `sa-east-1` (São Paulo) · **URL:** `https://d1o1gejacy6m9o.cloudfront.net`

---

## Deploy automático (CI/CD)

Qualquer `push` na branch `main` dispara o workflow que:

1. Cria/atualiza a infraestrutura via CloudFormation (Cognito + Lambda + DynamoDB)
2. Injeta a URL da API e o Client ID do Cognito no HTML
3. Sincroniza os arquivos com o S3
4. Invalida o cache do CloudFront

### Secrets no GitHub

| Secret | Descrição |
|---|---|
| `AWS_ACCESS_KEY_ID` | Access Key do usuário IAM |
| `AWS_SECRET_ACCESS_KEY` | Secret Key do usuário IAM |

---

## Rodando localmente

Abra o arquivo `habit-tracker.html` diretamente no navegador. Sem internet, o app funciona offline usando `localStorage`.

---

## Changelog recente

- [x] Layout responsivo com sidebar no desktop
- [x] Metas personalizadas (frequência diária/semanal/mensal)
- [x] Vínculo entre meta e tipo de treino — duração lida automaticamente
- [x] Duração do treino contabilizada no % de sucesso do dia
- [x] Sessão de treino separada por tipo (A/B/C) — troca sem perder dados
- [x] Plano de treino por tipo com upload de PDF/imagem via IA
- [x] Suplementos personalizados
- [x] Persistência em nuvem com DynamoDB + Lambda
- [x] Autenticação com AWS Cognito
- [ ] Domínio customizado via Route 53
