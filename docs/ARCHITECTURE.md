# Arquitetura — Decisors

## Produto
Uma API única de decisões tipadas para agentes:

```text
state + questions
       │
       ▼
 DecisionEngine
       │
 ┌─────┼──────────────┐
 ▼     ▼              ▼
Laya  Jev/TypeSafe   Jev/OpenRouter
local  cloud          cloud
```

Laya é o default. Jev é opt-in.

## Contrato único

```text
DecisionRequest
├─ state: string | object | array
└─ questions
   ├─ choice(instructions, criteria)
   ├─ score(instructions, ordered criteria)
   └─ noul(instructions)

DecisionResult
├─ provider
├─ model
├─ answers + probabilities + confidence
├─ usage
├─ elapsed_ms
└─ routing?            # Laya
```

Esse contrato é compatível conceitualmente com pi-typesafe e com `laya.system_one()`.

## Providers

| Provider | Default | Execução | Credencial | Observação |
|---|---:|---|---|---|
| `laya` | sim | local | nenhuma | Router por idioma; pesos HF |
| `typesafe` | não | remoto | `TYPESAFE_API_KEY` | Jev oficial |
| `openrouter` | não | remoto | `OPENROUTER_API_KEY` | Jev via `/api/alpha/decisions` |

Não haverá fallback local→cloud implícito.

## Fluxo Pi

```text
Pi
├─ /decision ...
└─ decision_evaluate
        │
        ▼
 integration/pi (TS/JS)
        │ JSONL stdio
        ▼
 decisors bridge (Python persistente)
        │
        ▼
 provider selecionado
```

O processo persistente é obrigatório para Laya: carregar o checkpoint a cada decisão destruiria a vantagem de latência.

## Primeiro uso

`/decision init`:

1. cria config com `provider=laya`;
2. detecta CPU/CUDA/MPS e locale;
3. escolhe o checkpoint Laya adequado para o primeiro warm-up;
4. consulta tamanho dos arquivos antes do download;
5. mostra tamanho + estimativa de download calculada por probe medido de até 1 MiB (nunca hard-coded);
6. baixa usando cache Hugging Face;
7. carrega, aquece e executa um `choice + noul` local;
8. marca runtime como pronto.

`model=auto` usa o Router do Laya. `typed-decisions` permanece opt-in. Outros checkpoints podem ser baixados lazy quando necessários.

## UX de configuração

```text
/decision config
  provider:
    ● Laya (local)
    ○ Jev — TypeSafe
    ○ Jev — OpenRouter

  Laya:
    model: auto
    device: auto
    max_loaded: 1

  Jev:
    verificar chave
    testar endpoint
    mostrar política/custo antes de habilitar
```

OpenRouter não deve aparecer como "OpenAI-compatible": o Jev usa a Decisions API específica, não `/v1/chat/completions`.

## Distribuição

```text
PyPI: decisors
├─ core Python
├─ CLI `decisors`
├─ bridge persistente
└─ adapter Pi compilado como recurso estático

instalação:
  pip/uv → decisors
  decisors integrate pi
  Pi → /decision init
```

Não usar hook de instalação para modificar `~/.pi` automaticamente.

## Estrutura implementada

```text
decisors/
├─ AGENTS.md
├─ README.md
├─ pyproject.toml
├─ docs/
│  └─ ARCHITECTURE.md
├─ src/decisors/
│  ├─ domain.py        # request/result/primitives
│  ├─ engine.py        # lifecycle e seleção explícita
│  ├─ bridge.py        # JSONL persistente
│  ├─ config.py        # XDG, sem segredos
│  ├─ cli.py
│  ├─ integrate.py
│  ├─ integrations/
│  │  └─ pi-extension.js
│  └─ providers/
│     ├─ laya.py
│     ├─ typesafe.py
│     └─ openrouter.py
├─ tests/
└─ referencia/
   ├─ laya/
   └─ pi-typesafe/
```

## Decisões que já ficam fechadas

- Base conceitual/API: pi-typesafe.
- Runtime local: Laya.
- Provider padrão: Laya.
- Jev: TypeSafe ou OpenRouter, explicitamente selecionados.
- Interface pública: `/decision`.
- Pi não carrega modelo: ele controla um bridge Python persistente.
- Sem N8N-specific logic; N8N poderá consumir o core futuramente.
