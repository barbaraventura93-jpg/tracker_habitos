# Rotina Diária

App de acompanhamento de rotina diária — refeições, água, suplementos, sono, treino e metas personalizadas — com sincronização entre dispositivos e histórico de 60 dias.

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
- Suplementos com checklist configurável por tipo de dia (treino / descanso)
- Registro de sono — horas e horário consistente
- Metas personalizadas com barra de progresso e status em tempo real

### Treino

**Musculação**
- Log de exercícios com séries, reps e kg por set
- Comparação automática com a última sessão do mesmo treino
- % de sucesso do dia sobe automaticamente ao concluir séries
- Plano de treino por tipo (A/B/C) salvo como modelo, sessões isoladas por tipo
- Sessões de treino persistidas no DynamoDB — histórico seguro mesmo se o cache do browser for limpo
- **Identificação automática de exercícios via Bedrock** — ao digitar o nome (≥ 3 letras), classifica o grupo muscular (Peito · Costas · Ombro · Bíceps · Tríceps · Perna · Glúteo · Core · Cardio) com emoji de representação; resultado cacheado em DynamoDB para não repetir chamadas
- **Card de identificação dinâmico** — exibe estado de loading → card confirmado com emoji + grupo → grade de seleção rápida se não identificado; botão "Trocar" para correção manual
- **Rever grupos** — botão no Plano reidentifica todos os exercícios cadastrados via Bedrock e atualiza os grupos em lote
- **Edição no plano** — botão ✏️ nos exercícios abre painel com nome, grupo muscular, séries/reps padrão e observação; alterações salvas permanentemente no plano
- **Edição de sessão** — mesmo botão na tela de log edita só aquela sessão, com aviso visual de escopo

**Cardio / Aeróbico**
- Log de atividades com duração (min) e distância (km) por intervalo
- `gymDurMin` calculado automaticamente ao marcar atividade concluída
- Suporte a múltiplos intervalos (ex: 5 tiros de 400m)

**Geral**
- Upload de plano via PDF ou imagem — IA extrai exercícios automaticamente
- **Log herda do Plano** — ao adicionar um exercício no Log, séries e reps são herdadas automaticamente do Plano correspondente; se o exercício não estiver no Plano, mostra campos editáveis com aviso; toast confirma a herança aplicada
- **Periodização por Blocos** — organização do treino em ciclos (ex: Hipertrofia → Deload → Força) com duração em semanas, meta de séries/reps e foco (volume · intensidade · deload); banner no topo do Log mostra o bloco atual, semana do ciclo, barra de progresso e botão "Próximo" ao atingir a última semana; gerenciado em Mais → Periodização por Blocos; sincronizado via DynamoDB (`__periodization__`)

### Semana

Tela dedicada na navegação inferior com visão consolidada da semana de treino:

- **Mapa muscular SVG anatômico** — silhueta humana frente/costas com curvas bezier e `<clipPath>` para recorte preciso; músculos posicionados anatomicamente (trapézio em diamante, latíssimo em asa, peitoral em leque, abdômen segmentado); heatmap com 4 intensidades: cinza (sem treino) → roxo claro (leve) → roxo (moderado) → laranja (intenso); fórmula: 15 séries/semana = 100%
- **Timeline semanal** — 7 cards Seg–Dom com tipo de treino, grupos trabalhados, duração e marcação de concluído/falhado
- **Equilíbrio muscular** — tabela com sets e intensidade por grupo (Peito · Costas · Ombro · Bíceps · Tríceps · Perna · Core · Glúteo)
- **Sugestão IA** — após renderizar a tela, busca sugestão personalizada no Bedrock (Amazon Nova Lite) com contexto da semana; exibe 1–2 mensagens motivadoras em português sobre o que falta treinar; fallback para regra estática se a IA não responder

### Nutrição
- Controle de macros por refeição
- Meta de calorias calculada automaticamente (BMR × TDEE)

### Suplementos
- Cadastro livre com nome, dose, ícone e visibilidade (sempre / treino / descanso)
- Importação via PDF ou foto — IA extrai os itens

### Metas e Objetivos

Sistema completo de metas com 12 categorias, 5 frequências e acompanhamento automático.

**Categorias:** Treino · Nutrição · Saúde · Sono · Meditação · Leitura · Finanças · Criatividade · Carreira · Social · Bem-estar · Personalizado

**Frequências:** Diária · Semanal · Mensal · Anual · Uma vez (com prazo)

**Vínculo com tipo de treino** — progresso alimentado automaticamente:
- **Duração (min):** soma os minutos das sessões concluídas no período
- **Sessões realizadas:** conta dias com atividades marcadas como feitas

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
- IA: **AWS Bedrock** (Amazon Nova Lite) — análise de PDF/imagem · identificação de exercícios · sugestão semanal
- Infraestrutura como código: **AWS CloudFormation**
- CI/CD: **GitHub Actions**

---

## Infraestrutura AWS

| Serviço | Uso | Custo |
|---|---|---|
| S3 | Hospedagem do arquivo estático | Free Tier |
| CloudFront | CDN + HTTPS + invalidação automática | Free Tier |
| Cognito | Autenticação de usuários | Free Tier (50k MAU) |
| DynamoDB `tracker-habitos-data` | Dados diários por usuário + sessões de treino (PK: userId, SK: date) | Free Tier |
| DynamoDB `exercise-cache` | Cache global de identificação de exercícios via Bedrock (PK: exerciseName) | Free Tier |
| Lambda | API REST + IA + identificação de exercícios + sugestão semanal | Free Tier |
| Bedrock (Nova Lite) | Extração de planos · identificação de exercícios · sugestão semanal | ~$0,00002/exercício identificado |
| GitHub Actions | CI/CD automático no push | Gratuito |

**Bucket:** `tracker-habitos` · **Região:** `sa-east-1` (São Paulo) · **URL:** `https://d1o1gejacy6m9o.cloudfront.net`

---

## Lambda — actions disponíveis

| Action | Método | Descrição |
|---|---|---|
| *(sem action)* | GET | Lê dados de uma data (`?date=YYYY-MM-DD` ou `gym:YYYY-MM-DD:trId`) |
| *(sem action)* | PUT | Salva dados de uma data |
| `analyze` | POST | Extrai exercícios ou suplementos de PDF/imagem via Bedrock |
| `identify_exercise` | GET | Identifica exercício pelo nome — cache DynamoDB → Bedrock Nova Lite |
| `week_suggestion` | POST | Gera sugestão semanal personalizada via Bedrock |
| `history_range` | GET | Lista dias e sessões de treino entre `start` e `end` (Query no DynamoDB) — hidrata o histórico em dispositivos novos |
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
