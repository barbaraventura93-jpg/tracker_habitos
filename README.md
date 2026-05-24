# 📋 Habit Tracker

App de acompanhamento de rotina diária — refeições, cardio, água, suplementos e sono — com histórico de 60 dias e sincronização entre dispositivos.

🌐 **[Acessar o app](https://d1o1gejacy6m9o.cloudfront.net)**

---

## Funcionalidades

- Cadastro e login com e-mail/senha via AWS Cognito
- Dados sincronizados na nuvem — acessíveis em qualquer dispositivo
- Marcação de refeições do dia com detalhes de macros
- Controle de água com indicador de copos, ml e litros consumidos/meta
- Cardio, suplementos e treino com checklist detalhado
- Registro de sono e horário consistente
- Score diário com anel de progresso e % no cabeçalho
- Histórico visual dos últimos 60 dias com calendário alinhado por dia da semana

### Metas pessoais inteligentes

Tela de configuração de metas com cálculo automático baseado em evidências científicas:

| Meta | Fórmula | Referência |
|---|---|---|
| **Água** | Peso atual × 35 ml/kg → converte em copos (250 ml) e exibe ml e L | EFSA & Institute of Medicine |
| **Calorias** | BMR (Mifflin-St Jeor) × fator de atividade ± ajuste de meta de peso | ISSN / ACSM (2005) |

**Perfil configurável:** sexo, idade, altura, peso atual, peso meta, dias de treino/semana e cardio mínimo.

**Fator de atividade (TDEE):**
- 0–1 dias/semana → ×1,2 (sedentário)
- 2–3 dias → ×1,375 (leve)
- 4–5 dias → ×1,55 (moderado)
- 6–7 dias → ×1,725 (intenso)

**Ajuste de meta de peso:**
- Perda de peso (meta < atual): −400 kcal/dia
- Ganho de massa (meta > atual): +300 kcal/dia
- Manutenção: sem ajuste

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

**Bucket:** `tracker-habitos`
**Região:** `sa-east-1` (São Paulo)
**URL:** `https://d1o1gejacy6m9o.cloudfront.net`

---

## Deploy automático (CI/CD)

Qualquer `push` na branch `main` dispara o workflow que:

1. Cria/atualiza a infraestrutura via CloudFormation (Cognito + Lambda + DynamoDB)
2. Injeta a URL da API e o Client ID do Cognito no HTML
3. Sincroniza os arquivos com o S3
4. Invalida o cache do CloudFront

### Permissões necessárias no IAM (`github-actions-tracker`)

- `AmazonS3FullAccess`
- `CloudFrontFullAccess`
- `AWSCloudFormationFullAccess`
- `AWSLambda_FullAccess`
- `AmazonDynamoDBFullAccess`
- `AmazonCognitoPowerUser`
- `IAMFullAccess`

### Secrets no GitHub

| Secret | Descrição |
|---|---|
| `AWS_ACCESS_KEY_ID` | Access Key do usuário IAM |
| `AWS_SECRET_ACCESS_KEY` | Secret Key do usuário IAM |

---

## Rodando localmente

Abra o arquivo `habit-tracker.html` diretamente no navegador. Sem internet ou fora do deploy, o app funciona offline usando `localStorage`.

---

## Próximos passos

- [x] CloudFront + HTTPS
- [x] Persistência em nuvem com DynamoDB + Lambda
- [x] Autenticação com AWS Cognito
- [x] Metas pessoais com cálculo científico de água e calorias
- [ ] Domínio customizado via Route 53
