# Getting Started with Decisors

Decisors brings fast, provider-agnostic **System One** judgment to AI agents. It handles semantic routing, narrow classification, risk evaluation, and yes/no scoring without invoking heavy reasoning models for everyday micro-decisions.

---

## 1. Quick Installation

### Option A: Via `uv` (Recommended)
```bash
# Install as a global CLI tool
uv tool install decisors

# Or install from local repository
git clone git@github.com:gabedsam01/decision-maker.git
cd decision-maker
uv tool install .
```

### Option B: Via `pip`
```bash
pip install decisors
```

---

## 2. Setting Up in Pi

Decisors includes a first-class extension for [Pi](https://github.com/badlogic/pi-mono):

1. **Register the Extension:**
   ```bash
   decisors integrate pi
   ```
   This automatically installs:
   - Extension entry point: `~/.pi/agent/extensions/decisors/index.js`
   - Prompt guidelines: `~/.pi/agent/prompts/juiz.md`
   - Skill documentation: `~/.pi/agent/skills/decisores-decisoes/SKILL.md`

2. **Reload and Initialize Pi:**
   In your active Pi session, run:
   ```text
   /reload
   /decision init
   /decision start
   ```

3. **Verify Health:**
   ```text
   /decision doctor
   /decision test
   ```

---

## 3. First-Time Setup (`/decision init`)

When you run `/decision init`:
1. **Hardware & Cache Inspection:** Decisors checks local CPU/GPU/MPS availability, available RAM, and Hugging Face cache status (`~/.cache/huggingface/hub`).
2. **Download & Warm-up (Laya Local):**
   - For `model = "auto"`, it inspects model checkpoints.
   - Downloads required weights once.
   - Loads the model into memory and executes a warm-up inference to verify readiness.
3. **Persisted Configuration:** Saves clean configurations in `~/.config/decisors/config.toml`.

---

## 4. Basic CLI Usage

Decisors provides an interactive CLI for testing and managing providers outside of agent sessions:

```bash
# View current status, provider, and loaded weights
decisors status

# Run system doctor diagnostic
decisors doctor

# Execute an interactive TUI control panel
decisors panel

# Test sample decision
decisors test

# Evaluate direct JSON payloads from stdin or file
cat request.json | decisors evaluate
```

---

## 5. Switching Providers

Decisors supports three provider backends:

### A. Local Laya (Default)
Runs 100% locally on CPU, CUDA, or MPS with zero API keys or external fees:
```bash
decisors config provider laya
```
Or in Pi:
```text
/decision config provider laya
```

### B. TypeSafe (Jev Official)
Direct high-speed decisions via TypeSafe API:
```bash
export TYPESAFE_API_KEY="your-typesafe-key"
decisors config provider typesafe
```
Or in Pi:
```text
/decision config provider typesafe
```

### C. OpenRouter (Jev via Decisions API)
Runs Jev models via OpenRouter's specialized `/api/alpha/decisions` endpoint:
```bash
export OPENROUTER_API_KEY="your-openrouter-key"
decisors config provider openrouter
```
Or in Pi:
```text
/decision config provider openrouter
```
*(Note: If configured in `~/.pi/agent/auth.json`, Decisors automatically detects and uses the key with session consent).*

---

## 6. What Next?
- Read the [Architecture Guide](ARCHITECTURE.md) to understand System One design principles.
- Check the [API Reference](API_REFERENCE.md) to integrate Decisors into Python applications.
- Explore [Pi Integration](PI_INTEGRATION.md) to customize tools and referee behaviors.
