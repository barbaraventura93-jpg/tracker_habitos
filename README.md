# 📋 Habit Tracker

App de acompanhamento de rotina diária — refeições, cardio, água, suplementos e sono — com histórico de 60 dias.

🌐 **[Acessar o app](http://tracker-habitos.s3-website-sa-east-1.amazonaws.com)**

---

## Funcionalidades

- Marcação de refeições do dia com detalhes de macros
- Controle de água, cardio e suplementos
- Registro de sono e horário consistente
- Score diário com anel de progresso
- Histórico visual dos últimos 60 dias
- Dados salvos localmente via localStorage

---

## Tecnologias

- HTML5 + CSS3 + JavaScript puro (sem frameworks)
- Hospedagem: **AWS S3 Static Website Hosting**
- Deploy automático: **GitHub Actions**

---

## Infraestrutura AWS

| Serviço | Uso | Custo |
|---|---|---|
| S3 | Hospedagem do arquivo estático | Free Tier |
| GitHub Actions | CI/CD automático no push | Gratuito |

**Bucket:** `tracker-habitos`
**Região:** `sa-east-1` (São Paulo)
**Endpoint:** `http://tracker-habitos.s3-website-sa-east-1.amazonaws.com`

---

## Deploy automático (CI/CD)

Qualquer `push` na branch `main` dispara o workflow do GitHub Actions que sincroniza os arquivos com o bucket S3 automaticamente.

### Configuração das credenciais (feita uma única vez)

1. No AWS Console, acesse **IAM → Users → Create user**
2. Nome: `github-actions-tracker`
3. Em **Permissions**, adicione a policy `AmazonS3FullAccess`
4. Crie uma **Access Key** e guarde o `Access Key ID` e `Secret Access Key`
5. No GitHub, vá em **Settings → Secrets and variables → Actions → New repository secret** e adicione:
   - `AWS_ACCESS_KEY_ID` → seu Access Key ID
   - `AWS_SECRET_ACCESS_KEY` → seu Secret Access Key

---

## Rodando localmente

Basta abrir o arquivo `habit-tracker.html` diretamente no navegador — não precisa de servidor.

---

## Próximos passos

- [ ] CloudFront + HTTPS
- [ ] Domínio customizado via Route 53
- [ ] Persistência em nuvem com DynamoDB + Lambda
