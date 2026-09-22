<div align="center">

# Decisors (`decision-maker`)

**Fast, provider-agnostic System One decisions for AI agents.**

[![CI](https://github.com/gabedsam01/decision-maker/actions/workflows/ci.yml/badge.svg)](https://github.com/gabedsam01/decision-maker/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-blue)](https://mypy-lang.org/)

[Features](#-key-features) • [Installation](#-installation) • [Pi Integration](#-pi-agent-integration) • [Quickstart](#-quickstart) • [Contract](#-decision-contract) • [Architecture](#-architecture) • [Documentation](#-documentation)

</div>

---

## 💡 What is Decisors?

Modern AI agents often waste slow and expensive reasoning LLM calls (System Two) on basic semantic classification: deciding if a search command had results, choosing which 2 skills out of 50 to activate, categorizing user sentiment, or answering yes/no confidence checks.

**Decisors** provides an agentic **System One subconscious**:
- It evaluates narrow semantic judgments in milliseconds with calibrated probabilities.
- It **does not generate free-form text** and **does not replace the agent's main model**.
- It receives `state + questions` and returns typed decisions (`choice`, `score`, `noul`) alongside distribution confidence.

---

## ✨ Key Features

- 🏠 **Local by Default (Laya)**: Runs 100% locally on CPU, CUDA, or Apple Silicon MPS using [Laya](https://github.com/leondz/laya). Zero API keys, zero fees, zero telemetry.
- ☁️ **Optional Cloud Providers**: Seamlessly plug in **TypeSafe (Jev)** or **OpenRouter (Jev via Decisions API)**.
- 🛡️ **Zero Silent Fallback**: Data sovereignty by design. The system will **never** silently forward prompts to external cloud endpoints. Cloud routing requires explicit, session-scoped consent.
- ⚖️ **Deterministic Referee**: Built-in deterministic parsing for CLI outputs (`rg` exit codes, syntax errors, dangerous commands like `rm -rf`), subagent status triage, and skill shortlisting.
- 🥧 **First-Class Pi Integration**: Native extension for [Pi](https://github.com/badlogic/pi-mono) featuring a persistent Python IPC bridge, slash commands (`/decision`), agent tools (`decision_evaluate`), and interactive TUI panel with Kitty keyboard protocol support.
- 📐 **Calibrated Confidence**: Low confidence signals ambiguity rather than making blind guesses. When options cannot be separated, Decisors reports uncertainty rather than picking the first option.

---

## 📦 Installation

### Option 1: Using `uv` (Recommended)
```bash
# Install CLI globally
uv tool install git+https://github.com/gabedsam01/decision-maker.git

# Integrate with Pi agent
decisors integrate pi
```

### Option 2: From Source
```bash
git clone git@github.com:gabedsam01/decision-maker.git
cd decision-maker
uv sync --extra dev
uv tool install .
decisors integrate pi
```

---

## 🥧 Pi Agent Integration

Decisors integrates directly with **Pi**:

```text
/reload             # Reload Pi extensions
/decision init      # Inspect hardware, download weights (one-time), run warm-up
/decision start     # Activate the persistent bridge and load runtime
```

### Available Slash Commands:
- `/decision init`: First-time setup, model download, hardware benchmark, warm-up.
- `/decision start`: Start decision runtime in background memory.
- `/decision stop`: Stop runtime and free memory/VRAM.
- `/decision config`: Select provider (`laya`, `typesafe`, `openrouter`), model, device, or thresholds.
- `/decision status`: Real-time status of provider, loaded weights, cache, and device.
- `/decision test`: Run an isolated sample decision without polluting agent context.
- `/decision doctor`: Comprehensive diagnostic for models, caches, and credentials.
- `/decision panel`: Interactive TUI modal.

### Tools Exposed to the Agent:
1. `decision_evaluate`: Core System One evaluation for semantic routing and scoring.
2. `decision_command`: Interprets CLI outputs (differentiates empty search from fatal failures, flags dangerous commands).
3. `decision_subagent`: Evaluates subagent responses and catches infrastructure issues before retry loops.
4. `decision_skill`: Narrows large skill catalogs down to the most relevant items (<= 19).
5. `decision_where`: Evaluates option volume (runs locally for <= 20 options, asks consent or tournaments for > 20).

---

## 🚀 Quickstart

### 1. Python API
```python
from decisors.engine import DecisionEngine

engine = DecisionEngine()
engine.init()
engine.start()

# Evaluate narrow questions over state
result = engine.evaluate(
    state={
        "command": "python app.py",
        "stderr": "Traceback (most recent call last):\n  File 'app.py', line 4\n    print('Hello'\n          ^\nSyntaxError: '(' was never closed",
    },
    questions={
        "failure_type": {
            "type": "choice",
            "instructions": "What kind of failure occurred?",
            "criteria": {
                "syntax": "Syntax or parsing error in code",
                "network": "Connection or timeout issue",
                "permission": "Access denied or authentication failure",
                "other": "Unrelated error",
            },
        },
        "is_fatal": {
            "type": "noul",
            "instructions": "Does this require code modification before re-running?",
        },
    },
)

print(result)
```

### 2. CLI Interface
```bash
# Check status and health
decisors status
decisors doctor

# Run sample test decision
decisors test

# Open interactive control panel
decisors panel
```

---

## 📋 Decision Contract

Decisors accepts a shared `state` and a dictionary of narrow `questions`:

```json
{
  "state": {
    "message": "Cobrança duplicada no meu cartão de crédito, solicito estorno imediato."
  },
  "questions": {
    "department": {
      "type": "choice",
      "instructions": "Para qual departamento este chamado deve ir?",
      "criteria": {
        "financeiro": "Cobranças, faturas, pagamentos e estornos",
        "suporte": "Falhas no software, bugs e problemas de acesso",
        "comercial": "Vendas, planos e novas contratações",
        "outro": "Nenhuma das opções acima"
      }
    },
    "urgente": {
      "type": "noul",
      "instructions": "O usuário demonstra insatisfação crítica ou urgência?"
    },
    "gravidade": {
      "type": "score",
      "instructions": "Qual a gravidade do problema?",
      "criteria": ["baixa", "media", "alta"]
    }
  }
}
```

### Response:
```json
{
  "decisions": {
    "department": {
      "choice": "financeiro",
      "confidence": 0.8924,
      "distribution": {
        "financeiro": 0.8924,
        "suporte": 0.0410,
        "comercial": 0.0152,
        "outro": 0.0514
      }
    },
    "urgente": {
      "choice": "sim",
      "confidence": 0.9310,
      "distribution": {
        "sim": 0.9310,
        "não": 0.0690
      }
    }
  },
  "provider": "laya",
  "model": "multilingual"
}
```

---

## 🏗 Architecture

```text
┌────────────────────────────────────────────────────────┐
│                      Agent (Pi)                        │
│             /decision   •   decision_* tools           │
└───────────────────────────┬────────────────────────────┘
                            │ Method invocations
                            ▼
┌────────────────────────────────────────────────────────┐
│                JavaScript Extension Adapter            │
│         ~/.pi/agent/extensions/decisors/index.js       │
└───────────────────────────┬────────────────────────────┘
                            │ Persistent IPC (JSONL stdio)
                            ▼
┌────────────────────────────────────────────────────────┐
│            Python Subprocess Bridge (decisors)         │
│                      DecisionEngine                    │
└───────────────┬────────────────────────┬───────────────┘
                │                        │
       Local Inference            Cloud Evaluation (Opt-in)
                ▼                        ▼
       Laya CPU / GPU / MPS      TypeSafe or OpenRouter Jev
     (No API Key Required)       (/api/alpha/decisions)
```

---

## 🔒 Security & Safety Principles

1. **Confidence is NOT Authorization**: Probability concentration indicates certainty in category distribution. It is never a proof of truth or permission for destructive actions.
2. **Deterministic Command Shield**: Destructive operations (`rm -rf`, `git push --force`, `mkfs`, `dd`, `chmod 777`) are intercepted deterministically and marked unauthorized (`authorized: false`).
3. **Zero Secret Leakage**: API credentials (`auth.json`, environment variables) are stripped before sending results across the IPC bridge or outputting logs.

Read our full [Security Policy](SECURITY.md) for details.

---

## 📚 Documentation

- 🚀 [Getting Started Guide](docs/GETTING_STARTED.md)
- 🏛 [Architecture & Design Rationale](docs/ARCHITECTURE.md)
- 📖 [API Reference & IPC Specification](docs/API_REFERENCE.md)
- 🥧 [Pi Agent Deep Dive](docs/PI_INTEGRATION.md)
- 🛡 [Security Policy](SECURITY.md)
- 🤝 [Contributing Guidelines](CONTRIBUTING.md)
- ⚖️ [License (MIT)](LICENSE)

---

## 👤 Author

**Gabriel Sampaio** ([@gabedsam01](https://github.com/gabedsam01))  
Founder, OrkestraIA
