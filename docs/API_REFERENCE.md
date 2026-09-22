# API Reference — Decisors

This document outlines the programmatic Python API, the command-line interface (CLI), and the inter-process communication (IPC) protocol used by Decisors.

---

## 1. Python API

### Core Engine: `DecisionEngine`
Located in `decisors.engine`. The main interface managing configuration, provider lifecycles, and evaluation dispatching.

```python
from decisors.engine import DecisionEngine

engine = DecisionEngine()
```

#### Methods:
- `engine.init() -> dict[str, Any]`
  Prepares the configured provider, downloads required model checkpoints (if using local Laya), verifies device accessibility, and executes a warm-up pass.
- `engine.start() -> dict[str, Any]`
  Activates the engine for evaluation requests. Loads model weights into memory.
- `engine.stop() -> dict[str, Any]`
  Deactivates the engine and unloads local weights from memory.
- `engine.evaluate(state: Any, questions: dict[str, Any]) -> EvaluationResult`
  Evaluates a batch of narrow questions over a shared state dictionary.
- `engine.status() -> dict[str, Any]`
  Returns current runtime status, active state, provider details, loaded models, and device information.
- `engine.doctor() -> dict[str, Any]`
  Runs comprehensive diagnostic checks on hardware, caches, python environment, and credentials.
- `engine.config(**kwargs) -> dict[str, Any]`
  Reads or updates persistent settings in `~/.config/decisors/config.toml`.

---

### Referee: `decisors.referee`
Provides deterministic checks and tournament routing algorithms that prevent wasting model inference.

```python
from decisors.referee import (
    command_report,
    subagent_report,
    skill_shortlist,
    where_plan,
    conclude_scored,
    pick_scored,
    expand_label,
)
```

#### Functions:
- `command_report(command: str, exit_code: int, stdout: str = "", stderr: str = "") -> dict[str, Any]`
  Determines whether a command output represents a benign empty search (e.g., `rg` exit code 1), a destructive command attempt (`rm -rf`), a truncation, or an uncaught syntax error.
- `subagent_report(status: str, output: str = "", error: str = "") -> dict[str, Any]`
  Parses subagent execution results. Detects infrastructure failures (e.g. `fallbackModels exhausted`) to prevent futile retry loops.
- `skill_shortlist(task: str, catalog: list[dict[str, Any] | str], limit: int = 19) -> dict[str, Any]`
  Selects up to `limit` relevant skills from an arbitrary catalog using token and prefix matching.
- `where_plan(option_count: int, credentials: dict[str, Any], cloud_allowed: bool | None = None) -> dict[str, Any]`
  Determines execution destination based on option volume (`<= 20` local, `> 20` ask or local tournament).
- `conclude_scored(options: list[str], scorer: Callable[[list[str]], dict[str, float]]) -> dict[str, Any]`
  Executes tournament rounds over lists with more than 20 items.
- `pick_scored(scores: dict[str, float]) -> dict[str, Any]`
  Evaluates categorical probability distributions. Ensures top choice exceeds `MIN_SCORE` (0.50) and `MIN_GAP` (0.20); returns `choice: None` on ambiguity.
- `expand_label(label: str, is_portuguese: bool = True) -> str`
  Translates digits to combined numeral representations (`7` -> `7 ou sete`) to ensure robust zero-shot attention.

---

### Providers

#### `LayaDecisor` (`decisors.providers.local`)
Runs local PyTorch/transformers-based Laya checkpoints.
- Models: `english` (default for English states), `multilingual` (default for Portuguese and foreign text), `typed-decisions` (explicit opt-in only).
- Device: `cpu`, `cuda`, `mps`, or `auto`.

#### `RemoteDecisor` (`decisors.providers.remote`)
Communicates with cloud providers using zero-dependency HTTP requests:
- `typesafe`: Jev official endpoint.
- `openrouter`: Jev models routed through OpenRouter's `/api/alpha/decisions`.

---

## 2. Decision Contract

All evaluations receive a `state` and a mapping of `questions`:

```json
{
  "state": {
    "command": "git push --force origin main",
    "user": "gabedsam01"
  },
  "questions": {
    "risk": {
      "type": "choice",
      "instructions": "Qual o nível de risco desta ação?",
      "criteria": {
        "baixo": "Ação de leitura ou sem impacto destrutivo",
        "medio": "Modifica arquivos locais reversíveis",
        "alto": "Ação destrutiva ou reescrita remota irreversível"
      }
    },
    "destructive": {
      "type": "noul",
      "instructions": "O comando pode apagar histórico ou causar perda de dados?"
    }
  }
}
```

### Result Schema:
```json
{
  "decisions": {
    "risk": {
      "choice": "alto",
      "confidence": 0.9412,
      "distribution": {
        "baixo": 0.0120,
        "medio": 0.0468,
        "alto": 0.9412
      }
    },
    "destructive": {
      "choice": "sim",
      "confidence": 0.9850,
      "distribution": {
        "sim": 0.9850,
        "não": 0.0150
      }
    }
  },
  "provider": "laya",
  "model": "multilingual"
}
```

---

## 3. CLI Commands

| Command | Description |
| :--- | :--- |
| `decisors init` | Downloads models, verifies cache and device, and executes warm-up. |
| `decisors start` | Starts session runtime and loads models into memory. |
| `decisors stop` | Stops session runtime and frees allocated RAM/VRAM. |
| `decisors config [KEY [VALUE]]` | Gets or sets configuration keys (`provider`, `model`, `device`, `confidence_threshold`). |
| `decisors status` | Reports engine state, active provider, device, and cached models. |
| `decisors doctor` | Diagnoses runtime health, disk caches, and API credentials. |
| `decisors test` | Executes an isolated test decision without polluting agent context. |
| `decisors panel` | Opens an interactive terminal user interface (TUI). |
| `decisors bridge` | Spawns a persistent JSONL worker for parent agents and language extensions. |
| `decisors integrate pi` | Installs the native Pi extension and skill artifacts into `~/.pi/agent/`. |

---

## 4. IPC Bridge Protocol

The bridge mode (`decisors bridge`) communicates over standard input/output using JSON Lines (`\n` separated JSON objects).

### Request Format:
```json
{"id": "1", "method": "evaluate", "params": {"state": {...}, "questions": {...}}}
```

### Success Response:
```json
{"id": "1", "ok": true, "result": {...}}
```

### Error Response:
```json
{"id": "1", "ok": false, "error": {"type": "ValidationError", "message": "Description..."}}
```

---

## 5. Request Limits

| Constant | Value | Meaning |
|---|---|---|
| `MAX_QUESTIONS` | 32 | Questions per request (independent questions are batched). |
| `MAX_INPUT_BYTES` | 64 KB | Serialized `state + questions` payload. |
| `MAX_INSTRUCTIONS` | 4 000 chars | Per question instructions. |
| `MAX_CHOICE_OPTIONS` | 255 | Options per choice (cloud cap). Local Laya rounds cap at 20 options (tournament above that). |
| `MAX_SCORE_LEVELS` | 10 | Ordered levels per score. |
| `MAX_QUESTION_ID` | 128 chars | Question id length. |
