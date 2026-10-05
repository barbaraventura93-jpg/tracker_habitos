# Rotina Diária

Coach de **alimentação, suplementação e hábitos** — inspirado na experiência do Fitbod, mas para comida: o app conversa com a pessoa, indica a rotina alimentar do dia, adapta refeições quando ela quer mudar algo, controla refeições livres e mostra onde ela está escorregando para chegar na meta. Sincroniza entre dispositivos.

> **Mudança de direção (out/2026).** O app não acompanha mais treino: só indica apps de treino (Mais › Treino). Todo o código de treino foi removido do frontend e do Lambda; os dados antigos de treino continuam na conta e saem em "Exportar dados".

## Coach alimentar

- **Perfil alimentar em conversa** (cadastro e Mais › Perfil alimentar): cidade/estado, o que come num dia normal, o que ama, o que não gosta, restrições, onde sente que falha e quantas refeições livres quer por semana/quinzena/mês
- **Aba Coach**: chat com IA (`action=coach`, `mode=chat`) com todo o contexto do dia; quando a resposta muda refeições, aparece "Aplicar no meu dia"
- **Cardápio do dia** (`mode=day`), **trocar uma refeição** (`mode=swap`, 3 opções com macros parecidos) e **encaixar um extra** (`mode=flex` — "quero um sorvete sem culpa": estima o doce e reajusta as refeições que faltam)
- Os ajustes valem só para o dia (`dayData.mealOverrides`) — o plano base não muda
- **Refeições livres**: o registro "Comeu fora do plano?" tem a opção "contar como refeição livre", e o card mostra o uso no período
- **Aba Progresso** (7/14/30 dias): calorias por dia × meta, médias, refeições do plano cumpridas e "onde está escorregando" (excesso de calorias, proteína baixa, refeição pulada, escapadas à noite/no fim de semana, refeições livres acima do combinado, água, suplementos), cada ponto com atalho para pedir ajuda ao coach

**[Acessar o app](https://d1o1gejacy6m9o.cloudfront.net)**

---

## Funcionalidades

- Cadastro e login com e-mail/senha via AWS Cognito
- Dados sincronizados na nuvem — acessíveis em qualquer dispositivo
- Layout responsivo: sidebar lateral no desktop, barra inferior no mobile

### Hoje

- Score diário com anel de progresso, barras por categoria e pendências
- Marcação de refeições com detalhes de macros
- Controle de água com indicador de copos, ml e litros
- Checklist de suplementos do dia
- Registro de sono — horas e horário consistente
- Metas personalizadas com barra de progresso e status em tempo real

### Nutrição
- Controle de macros por refeição
- Meta de calorias calculada automaticamente (BMR × TDEE)

### Suplementos
- Cadastro livre com nome, dose, horário e ícone
- Importação via PDF ou foto — IA extrai os itens

### Metas e Objetivos

Sistema completo de metas com 12 categorias, 5 frequências e acompanhamento automático.

**Categorias:** Exercício · Nutrição · Saúde · Sono · Meditação · Leitura · Finanças · Criatividade · Carreira · Social · Bem-estar · Personalizado

**Frequências:** Diária · Semanal · Mensal · Anual · Uma vez (com prazo)

**Tela Hoje — 3 seções:** Foco do Dia / Esta Semana / Longo Prazo
- Card mostra barra de progresso, status do dia e botões de log rápido (+1, +5, +10)
- Confetti ao atingir 100%
- Alerta de risco quando prazo próximo e progresso abaixo de 70%

**Registro de progresso**
- Toque no card abre painel inline (desktop) ou bottom sheet (mobile)
- Botões rápidos gerados automaticamente pela unidade da meta (livros → +1/+2/+5 · horas → +30min/+1h/+2h · R$ → +50/+100/+500)
- Campo de anotação opcional por registro
- Botão `···` abre histórico completo com data, valor e nota
- Previsão de conclusão calculada pelo ritmo atual
- Remoção de registro individual em caso de erro

**Gestão:** criar, editar, arquivar e excluir metas. Ícone e unidade livres.

### Configurações de Saúde

| Meta | Fórmula | Referência |
|---|---|---|
| **Água** | Peso × 35 ml/kg → copos de 250 ml | EFSA & Institute of Medicine |
| **Calorias** | BMR (Mifflin-St Jeor) × fator de atividade ± ajuste de peso | ISSN / ACSM (2005) |

**Fator de atividade (TDEE):** sedentário ×1,2 · leve ×1,375 · moderado ×1,55 · intenso ×1,725

**Ajuste de peso:** −400 kcal (perda) / +300 kcal (ganho) / sem ajuste (manutenção)

### Histórico
- Calendário dos últimos 60 dias com % diário
- Streak de dias acima de 80%, média geral e dias excelentes

---

## Tecnologias

- HTML5 + CSS3 + JavaScript puro (sem frameworks, single file)
- Hospedagem: **AWS S3 + CloudFront**
- Autenticação: **AWS Cognito**
- Backend: **AWS Lambda (Python 3.12) + DynamoDB**
- IA: **AWS Bedrock** (Amazon Nova Lite) — coach alimentar · análise de PDF/imagem · estimativa de macros · plano alimentar
- Infraestrutura como código: **AWS CloudFormation**
- CI/CD: **GitHub Actions**

---

## Infraestrutura AWS

| Serviço | Uso | Custo |
|---|---|---|
| S3 | Hospedagem do arquivo estático | Free Tier |
| CloudFront | CDN + HTTPS + invalidação automática | Free Tier |
| Cognito | Autenticação de usuários | Free Tier (50k MAU) |
| DynamoDB `tracker-habitos-data` | Dados diários e configurações por usuário (PK: userId, SK: date) | Free Tier |
| DynamoDB `exercise-cache` | **Sem uso** desde a remoção do treino — continua no template até ser retirada de propósito | Free Tier |
| Lambda | API REST + IA (coach, macros, plano alimentar, import) | Free Tier |
| Bedrock (Nova Lite) | Coach · extração de planos · estimativa de macros | centavos por mês |
| GitHub Actions | CI/CD automático no push | Gratuito |

**Bucket:** `tracker-habitos` · **Região:** `sa-east-1` (São Paulo) · **URL:** `https://d1o1gejacy6m9o.cloudfront.net`

---

## Lambda — actions disponíveis

| Action | Método | Descrição |
|---|---|---|
| *(sem action)* | GET | Lê dados de uma data (`?date=YYYY-MM-DD`) ou de uma chave de configuração (`__goals__` etc.) |
| *(sem action)* | PUT | Salva dados de uma data |
| `analyze` | POST | Extrai suplementos ou plano alimentar de PDF/imagem/texto via Bedrock |
| `coach` | POST | Coach alimentar — `mode` chat, swap, flex ou day |
| `estimate_food` | POST | Estima macros de uma refeição (texto ou foto) |
| `generate_meal_plan` | POST | Gera plano alimentar por IA |
| `analyze_bio` | POST | Extrai composição corporal de um exame de bioimpedância |
| `history_range` | GET | Lista os dias entre `start` e `end` (Query no DynamoDB) — hidrata o histórico em dispositivos novos |
| `delete_account` | POST | Apaga todos os dados do usuário |
| `export` | GET | Exporta todos os registros do usuário em JSON |

---

## Deploy automático (CI/CD)

Qualquer `push` na branch `main` dispara o workflow que:

1. Cria/atualiza a infraestrutura via CloudFormation (Cognito + Lambda + DynamoDB)
2. Garante permissão pública na Function URL do Lambda
3. Injeta a URL da API e o Client ID do Cognito no HTML
4. Sincroniza os arquivos com o S3
5. Invalida o cache do CloudFront

### Secrets no GitHub

| Secret | Descrição |
|---|---|
| `AWS_ACCESS_KEY_ID` | Access Key do usuário IAM |
| `AWS_SECRET_ACCESS_KEY` | Secret Key do usuário IAM |

---

## Offline & sincronização

- **PWA offline de verdade** — o service worker guarda o app em cache; o app instalado abre e funciona sem internet (estratégia network-first: com conexão, atualizações chegam na hora)
- **Fila de sincronização (outbox)** — toda gravação vai para uma fila persistente em `localStorage`; se a rede cair, a fila é reenviada automaticamente ao reconectar, ao abrir o app e a cada 60 s — nada se perde
- **Merge por timestamp** — cada dia carrega `_ts` da última edição; em conflito, vence a versão mais recente (e edições locais pendentes nunca são sobrescritas pelo servidor)
- **Indicador de sync** — o header mostra ✓ sincronizado, ↻ sincronizando ou ⚡ offline com o tamanho da fila
- **Histórico multi-dispositivo** — a tela Histórico busca os últimos 60 dias na nuvem (`action=history_range`) e preenche o cache local em dispositivos novos
- **Exportação** — Mais → Exportar dados baixa todos os registros do usuário em JSON

## Rodando localmente

Abra o arquivo `habit-tracker.html` diretamente no navegador. Sem internet, o app funciona offline usando `localStorage`. As chamadas de API (identificação de exercícios, sugestão semanal) são silenciosamente ignoradas sem conexão.

---

## Changelog

- [x] Layout responsivo — sidebar no desktop, barra inferior no mobile
- [x] Sessão de treino separada por tipo (A/B/C) — troca sem misturar dados
- [x] Musculação: séries com reps e kg, comparação com sessão anterior
- [x] Cardio: atividades com min e km, duração calculada automaticamente
- [x] Upload de plano de treino via PDF/imagem — extração por IA
- [x] Tela Semana — mapa muscular SVG com heatmap, timeline, equilíbrio e sugestão IA
- [x] Metas e objetivos — 12 categorias, 5 frequências, logs, confetti
- [x] Vínculo de meta com tipo de treino — duração ou sessões automáticas
- [x] % de sucesso do dia alimentado pelo treino concluído
- [x] Suplementos personalizados com importação por IA
- [x] Persistência em nuvem com DynamoDB + Lambda
- [x] Autenticação com AWS Cognito
- [x] Registro de progresso em metas de longo prazo — painel inline, bottom sheet, botões rápidos, histórico e previsão
- [x] Edição de exercício no plano e na sessão — nome, grupo, séries/reps, observação
- [x] Identificação automática de exercícios via Bedrock — sem dependência de API externa
- [x] Card de identificação dinâmico — loading / confirmado com emoji / grade de seleção manual
- [x] Formulário de adição simplificado — grupo preenchido automaticamente, sem select manual
- [x] Botão "Rever grupos" no Plano — reidentifica todos os exercícios em lote via Bedrock
- [x] Sessões de treino persistidas no DynamoDB — histórico seguro mesmo após limpeza de cache
- [x] Mapa muscular anatômico — silhueta com bezier + clipPath, posicionamento correto de cada grupo
- [x] Log herda séries/reps do Plano automaticamente — sem campos redundantes quando exercício já tem modelo
- [x] Periodização por Blocos — ciclos semanais com banner no Log, barra de progresso e sync em nuvem
