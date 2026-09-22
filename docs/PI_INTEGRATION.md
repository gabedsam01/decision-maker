# Pi Agent Integration — Decisors

Decisors provides an optimized, native integration for [Pi](https://github.com/badlogic/pi-mono), serving as the agent's subconscious **System One** judgment layer.

---

## 1. Architectural Overview

```text
┌────────────────────────────────────────────────────────┐
│                   Pi Agent Session                     │
│  Slash Commands (/decision)  &  Agent Decision Tools   │
└───────────────────────────┬────────────────────────────┘
                            │ Method invocations
                            ▼
┌────────────────────────────────────────────────────────┐
│          Thin JavaScript Extension Adapter             │
│        ~/.pi/agent/extensions/decisors/index.js        │
└───────────────────────────┬────────────────────────────┘
                            │ Persistent IPC (JSONL stdio)
                            ▼
┌────────────────────────────────────────────────────────┐
│          Decisors Bridge (Python Subprocess)           │
│                  decisors bridge                       │
└───────────────┬────────────────────────┬───────────────┘
                │                        │
       Local Inference            Cloud Evaluation (Opt-in)
                ▼                        ▼
       Laya CPU / GPU / MPS      TypeSafe or OpenRouter Jev
```

### Key Engineering Tenets in Pi:
1. **Persistent Bridge**: The Python process starts once upon session initialization and remains alive. Model weights are never reloaded per tool call.
2. **Stderr Draining**: Background model-download progress or Hugging Face warning streams on `stderr` are actively drained to eliminate any risk of pipe deadlock.
3. **Thin Adapter, Single Credential Source**: Only the Python core resolves credentials (environment variables and the `auth.json` store). The JS adapter never reads secrets — it just starts the bridge, which inherits the environment.

---

## 2. Slash Commands (`/decision`)

Users can manage Decisors directly within the Pi chat interface:

| Slash Command | Description |
| :--- | :--- |
| `/decision init` | Runs hardware inspection, downloads necessary weights, and performs warm-up. |
| `/decision start` | Boots the model runtime in memory for the active session. |
| `/decision stop` | Stops the engine and unloads local weights. |
| `/decision config` | Opens the configuration modal or updates keys (`/decision config provider laya`). |
| `/decision status` | Displays current provider, loaded model, device, and readiness. |
| `/decision test` | Runs an isolated sample decision to verify connectivity. |
| `/decision doctor` | Runs diagnostics on cache paths, hardware, and credentials. |
| `/decision panel` | Opens an interactive Terminal User Interface (TUI) overlay. |

---

## 3. Agent Tools

Decisors equips the agent with 5 specialized tools:

### 1. `decision_evaluate`
Used for semantic classification, triage, scoring, and yes/no judgments.
- **Batched**: Independent questions evaluating the same context must be submitted in a single request.
- **Confidence**: Reflects distribution concentration, **never** permission.

### 2. `decision_command`
Interprets CLI outputs deterministically without wasting model passes:
- Identifies empty searches that are not failures (e.g. `rg -q` exiting with code 1).
- Flags syntax errors and Python tracebacks directly.
- Detects destructive command execution attempts (`rm -rf`, `chmod 777`) and marks them unauthorized.

### 3. `decision_subagent`
Normalizes subagent outputs and prevents useless retry loops:
- Categorizes infrastructure failures (e.g., model fallback exhaustion).
- Extracts clean results without prompting chatter.

### 4. `decision_skill`
Filters a large catalog down to a compact shortlist (maximum 19 items) matching the user's immediate request:
- Prevents bloat in agent context.
- Employs token prefix matching and handles singular/plural variants.

### 5. `decision_where`
Governs execution destination based on option volume:
- `<= 20 options`: Automatically runs locally via Laya.
- `> 20 options (with credentials)`: Requests explicit human confirmation before sending state to cloud.
- `> 20 options (cloud denied or no key)`: Runs an automated local tournament in chunks of 20.

---

## 4. Interactive TUI & Terminal Protocol

The Pi extension includes an overlay TUI built using `ctx.ui.custom`:
- **Kitty Keyboard Protocol**: Full compatibility with kitty arrow keys, escapes, and shift modifiers.
- **Non-blocking Execution**: Visual spinner and status updates during model warm-up or downloads.
