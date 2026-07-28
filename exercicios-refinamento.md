# Refinamento técnico — Exercícios & Identificação Muscular
## branch: feature/semana → feature/exercicios-v2

---

## Contexto e estado atual

O módulo de exercícios tem identificação via Bedrock já funcionando no Lambda, mas com um bug ativo e um problema de UX que tornam a experiência confusa.

| Capacidade | Estado | Observação |
|---|---|---|
| Identificação via Bedrock (`identify_exercise`) | ✅ Existe | Bug de acentuação impede auto-fill |
| Cache no DynamoDB (`exercise-cache`) | ✅ Existe | Tabela criada, caching funciona |
| Auto-preenchimento do grupo no formulário | ❌ Bug ativo | Mismatch de acentos — veja abaixo |
| Formulário limpo (sem campos manuais) | ❌ Pendente | `gpa-group` sempre visível |
| ExerciseDB (GIF + músculo preciso) | ✅ Existe | GIF + instruções + músculo-alvo, com cache |
| Identificação no log diário (não só no plano) | ❌ Pendente | Só funciona na tela de Plano |

---

## Bug: Grupo muscular não é preenchido pela API

### Causa raiz — mismatch de acentuação

O Lambda envia o prompt ao Bedrock pedindo um valor sem acento:

```python
# infrastructure/template.yaml — linha ~171
'"group":"Peito|Costas|Ombro|Biceps|Triceps|Perna|Gluteo|Core|Cardio|Outro"'
#                                      ^^^^^^  ^^^^^^^       ^^^^^^
#                                      sem acento            sem acento
```

O Bedrock retorna exatamente o que o prompt pede: `"Biceps"`, `"Triceps"`, `"Gluteo"`.

Mas o frontend compara contra `GYM_GROUPS` que tem acentos:

```javascript
// habit-tracker.html — linha 394
const GYM_GROUPS = ['Peito','Costas','Ombro','Bíceps','Tríceps','Perna','Core','Glúteo','Cardio','Outro'];
//                                            ^^^^^^   ^^^^^^^                  ^^^^^^
//                                            com acento                       com acento
```

A comparação falha silenciosamente:

```javascript
// linha 757-759 — normalize('NFC') não remove acentos, apenas normaliza representação Unicode
const normalized = d.group.normalize('NFC');   // "Biceps" continua "Biceps"
const opt = [...groupEl.options].find(o => o.value.normalize('NFC') === normalized);
// "Bíceps" !== "Biceps" → opt === undefined → select NÃO é preenchido
if(opt) groupEl.value = opt.value;             // nunca executa
```

**Resultado:** para qualquer exercício de Bíceps, Tríceps ou Glúteo, a API identifica corretamente mas o select permanece em "Peito" (primeiro item). O usuário vê a card de identificação correta *e* um select errado, sem entender o que está acontecendo.

### Fix

**Opção A — Corrigir o prompt do Lambda** (mais simples, recomendada):

```python
# Alterar em infrastructure/template.yaml
'"group":"Peito|Costas|Ombro|Bíceps|Tríceps|Perna|Glúteo|Core|Cardio|Outro",'
```

Prós: a fonte da verdade fica correta. Contras: Bedrock pode ou não reproduzir acentos fielmente (modelo de linguagem, não é garantido).

**Opção B — Normalizar a comparação no frontend** (mais robusta):

```javascript
// Adicionar função de normalização insensível a acento
function stripAccents(s) {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

// Substituir a comparação na linha 758
const opt = [...groupEl.options].find(o => stripAccents(o.value) === stripAccents(d.group));
```

**Recomendação: fazer as duas.** Corrigir o prompt (Opção A) para evitar divergência de dados no cache do DynamoDB, e adicionar `stripAccents` (Opção B) como defesa — o Bedrock pode variar.

---

## Problema de UX: o formulário pede campos que a IA já sabe

### Situação atual

Quando o usuário abre "Adicionar exercício ao plano", vê isso:

```
[ Nome do exercício  ______________ ]

  Identificando...   ← status da API

[ Peito ▾ ]           ← select de grupo SEMPRE visível

[ Séries: 3 ]  [ Reps: 12 ]
[ Observação (opcional) ]
[ Adicionar ao Plano ]
```

Quando a API identifica com sucesso, aparece a card de identificação **e** o select continua visível. O usuário não sabe se deve confirmar o select ou se a card já resolveu. O grupo também só é auto-preenchido nos casos sem bug (Peito, Costas, Ombro, Perna, Core, Cardio).

Além disso, `targetMuscle` e `secondaryMuscles` ficam invisíveis — são salvos via `_gymIdInfo` automaticamente, mas o usuário nunca sabe que foram capturados.

### Visão proposta

O formulário deve ter **uma única responsabilidade do usuário**: digitar o nome.
O resto é responsabilidade da IA.

```
ADICIONAR AO PLANO — Peito B

  [ Supino inclinado com halteres  ✕ ]
    ↑ foco aqui, sem outros campos

  ─── Identificando... ───────────────

  quando encontrado:

  ┌─────────────────────────────────────┐
  │ 🫁  Peito · Peitoral maior          │
  │     Secundários: Tríceps, Ombros    │
  └─────────────────────────────────────┘
  [Mudar grupo ▾]  ← só aparece se usuário quiser corrigir

  Séries [ 3 ]   Reps [ 12 ]
  Obs (opcional) [________________________]

  [Adicionar ao Plano]
```

**Regras do novo UX:**

| Estado da identificação | O que mostrar |
|---|---|
| Digitando (< 3 chars ou < 450ms) | Apenas o campo de nome |
| Carregando | `Identificando...` abaixo do nome |
| Encontrado | Card com grupo + músculo principal + secundários. Select de grupo OCULTO |
| Não encontrado | Seletor simples de grupo (só grupo, sem músculo primário/secundário) |
| Sem API / offline | Seletor simples de grupo direto |

---

## Redesign do formulário — implementação

```javascript
function gymRenderAddForm(wId) {
  const state = _gymAddIdState; // 'idle' | 'loading' | 'found' | 'not_found'
  const info  = _gymIdInfo;

  // Bloco de identificação
  let idBlock = '';
  if (state === 'loading') {
    idBlock = `<div style="font-size:11px;color:#A8A29E;padding:4px 0">Identificando...</div>`;
  } else if (state === 'found' && info?.found) {
    const icon = GROUP_ICONS[info.group] || '🏋️';
    const secs = (info.secondaryMuscles || []).join(', ');
    idBlock = `
      <div style="display:flex;align-items:center;gap:10px;padding:10px 12px;
                  background:#EDE9FF;border:1px solid #C4BFFF;border-radius:10px;margin-bottom:6px">
        <div style="width:36px;height:36px;border-radius:8px;background:#C4BFFF;
                    display:flex;align-items:center;justify-content:center;font-size:20px">
          ${icon}
        </div>
        <div style="flex:1;min-width:0">
          <div style="font-size:13px;font-weight:700;color:#1C1917">${info.group}</div>
          <div style="font-size:11px;color:#6C63FF">${info.targetMuscle || ''}</div>
          ${secs ? `<div style="font-size:10px;color:#78716C;margin-top:2px">+ ${secs}</div>` : ''}
        </div>
        <button onclick="gymOverrideGroup()" style="font-size:10px;color:#A8A29E;
                background:none;border:none;cursor:pointer;padding:4px">
          Corrigir
        </button>
      </div>`;
  } else if (state === 'not_found' || (state === 'idle' && !USE_API)) {
    // Select simples — só grupo, sem targetMuscle/secondaryMuscles
    idBlock = `
      <div style="font-size:11px;color:#78716C;margin-bottom:4px">
        ${state === 'not_found' ? 'Não identificado — selecione o grupo:' : 'Grupo muscular:'}
      </div>
      <select id="gpa-group" style="width:100%;...">
        ${GYM_GROUPS.map(g => `<option value="${g}">${g}</option>`).join('')}
      </select>`;
  }

  return `
    <div style="background:#FAFAF9;border:1px solid #D4D0CE;border-radius:10px;padding:12px;margin-top:8px">
      <input type="text" id="gpa-name"
        oninput="gymTriggerIdentify(this.value)"
        placeholder="Nome do exercício"
        style="...;margin-bottom:6px">
      <div id="gym-id-status">${idBlock}</div>
      ${/* gpa-group SÓ aparece no not_found/idle acima — nunca junto com a card found */ ''}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
        <div>Séries <input type="number" id="gpa-sets" value="3"></div>
        <div>Reps   <input type="text"   id="gpa-reps" placeholder="12"></div>
      </div>
      <input type="text" id="gpa-obs" placeholder="Observação (opcional)" style="...">
      <div style="display:flex;gap:8px;margin-top:10px">
        <button onclick="gymPlanManualConfirm('${wId}')">Adicionar ao Plano</button>
        <button onclick="gymPlanManualCancel()">Cancelar</button>
      </div>
    </div>`;
}
```

Ao salvar (`gymPlanManualConfirm`):

```javascript
function gymPlanManualConfirm(wId) {
  const name = (document.getElementById('gpa-name')?.value || '').trim();
  if (!name) return;

  // Grupo: preferir o identificado pela IA; fallback para select (estado not_found)
  const group =
    (_gymIdInfo?.found && _gymIdInfo.group) ||
    document.getElementById('gpa-group')?.value ||
    'Outro';

  // Extra: só preenche se a IA identificou
  const extra = _gymIdInfo?.found ? {
    targetMuscle:     _gymIdInfo.targetMuscle,
    targetMuscles:    _gymIdInfo.targetMuscle ? [_gymIdInfo.targetMuscle] : [],
    secondaryMuscles: _gymIdInfo.secondaryMuscles || [],
    gifUrl:           _gymIdInfo.gifUrl || '',
    instructions:     _gymIdInfo.instructions || '',
  } : {};

  // ... resto igual
}
```

---

## Identificação no log diário (não só no plano)

Hoje a identificação só funciona em `gymPlanManualAdd` (tela de Plano). Quando o usuário adiciona um exercício ad-hoc durante o treino (log do dia), o `_gymAddIdState` e `_gymIdInfo` são resetados, mas não há chamada a `gymTriggerIdentify`.

**Gap:** exercícios adicionados no log diário sem plano ficam sem `group`, `targetMuscle` e `secondaryMuscles` — isso quebra o heatmap muscular da tela Semana.

**Fix:** o campo de input de nome no log diário também deve chamar `gymTriggerIdentify` e ler `_gymIdInfo` ao salvar.

---

## Ordem de implementação

```
1. [URGENTE / BAIXO ESFORÇO] Fix do bug de acentuação
   → Corrigir o prompt do Lambda (Biceps → Bíceps, etc.)
   → Adicionar stripAccents() na comparação do frontend
   → 5 linhas de mudança — pode entrar em qualquer branch

2. [MÉDIO] Redesign do formulário de adição
   → Ocultar gpa-group quando API identifica
   → Mostrar card de identificação como confirmação visual
   → Botão "Corrigir" para override manual
   → ~50 linhas

3. [MÉDIO] Estender identificação ao log diário
   → Chamar gymTriggerIdentify no input do log
   → Ler _gymIdInfo ao salvar exercício ad-hoc
   → Garantir que group sempre seja preenchido para o heatmap

4. [FEITO — Fase 2] Integração ExerciseDB
   → GIF animado + instruções + músculo-alvo da base de dados
   → Card de identificação mostra o GIF no lugar do ícone do grupo
   → Ordem invertida em relação ao plano original: Bedrock primeiro, ExerciseDB
     depois. A busca da ExerciseDB é por nome em inglês, então com nomes em
     português ("Rosca direta") ela erraria quase sempre. O Bedrock resolve o
     grupo em português — que a ExerciseDB não tem — e traduz o nome; a busca
     usa essa tradução. Fica 1 requisição por exercício novo, dentro do free tier.
```

---

## Modelo de dados do exercício após o fix

```javascript
// Exercício no gymPlan[workoutId]:
{
  name:             "Supino inclinado com halteres",
  group:            "Peito",             // preenchido pela IA (corrigido)
  sets:             3,
  reps:             "12",
  obs:              "",
  // campos opcionais — presentes quando IA identificou
  targetMuscle:     "pectorals",
  targetMuscles:    ["pectorals"],
  secondaryMuscles: ["triceps", "delts"],
  gifUrl:           "",                  // será preenchido na Fase 2
  instructions:     "",                  // será preenchido na Fase 2
}
```

---

## Git

```bash
# Fix urgente — pode ir em qualquer branch ativa
git commit -m "fix(gym): corrigir mismatch de acentos entre Lambda e GYM_GROUPS"

# Redesign do formulário
git commit -m "feat(gym): ocultar select de grupo quando API identifica exercicio"
git commit -m "feat(gym): mostrar card de confirmacao muscular no formulario de adicao"
git commit -m "fix(gym): estender identificacao de exercicio ao log diario"
```

---

## Critérios de aceite

### Bug fix
- [ ] Adicionar "Rosca direta" → grupo preenchido como "Bíceps" automaticamente
- [ ] Adicionar "Tríceps testa" → grupo preenchido como "Tríceps" automaticamente
- [ ] Adicionar "Glúteo 4 apoios" → grupo preenchido como "Glúteo" automaticamente
- [ ] Cache do DynamoDB armazena o valor com acento correto

### UX do formulário
- [ ] Após identificação bem-sucedida, select de grupo não aparece
- [ ] Card de identificação mostra: grupo + ícone + músculo principal + secundários
- [ ] Botão "Corrigir" exibe o select de grupo para override manual
- [ ] Quando não identificado, mostra apenas select de grupo (sem campos de músculo)

### Log diário
- [ ] Exercício adicionado no log (fora do plano) tem `group` preenchido
- [ ] Heatmap da tela Semana contabiliza esses exercícios corretamente
