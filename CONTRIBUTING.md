# Contributing to Decisors

Thank you for your interest in contributing to **Decisors**! We welcome bug fixes, documentation improvements, benchmark contributions, and ecosystem integrations that adhere to our core philosophy.

---

## Core Philosophy & Design Principles

1. **System One Only**: Decisors is a narrow, fast judgment layer. It does **not** generate free text, execute code, perform arithmetic, or replace primary reasoning LLMs.
2. **Local by Default**: The default provider is local Laya without API keys. Remote cloud providers are opt-in only.
3. **No Silent Fallback**: Never send local data to a remote cloud provider without explicit user consent.
4. **Confidence != Authorization**: Model confidence represents probability distribution concentration, not safety or permission.
5. **Deterministic Referee First**: When a condition can be resolved with standard parsing (e.g., exit codes, regex on command names, subagent error codes), do so deterministically without wasting model passes.
6. **Lean Dependencies**: Prefer standard library and minimal external packages.

---

## Development Environment Setup

### Prerequisites
- Python 3.11, 3.12, or 3.13
- [`uv`](https://github.com/astral-sh/uv) (recommended package and environment manager)
- Node.js >= 20 (for Pi extension development)

### 1. Clone the Repository
```bash
git clone git@github.com:gabedsam01/decision-maker.git
cd decision-maker
```

### 2. Install Dependencies
Set up the virtual environment and install all dependencies (including development and test tools):
```bash
uv sync --extra dev
```

### 3. Run the Test Suite
Ensure all unit and integration tests pass:
```bash
uv run pytest
```

### 4. Code Quality & Formatting
We enforce strict linting and type checking across the codebase:
```bash
# Run Ruff linter and formatter checks
uv run ruff check src tests

# Run strict Mypy type checker
uv run mypy src
```

---

## Testing Pi Integration Locally

To test changes made to the Pi extension (`src/decisors/integrations/pi-extension.js`):

```bash
# Link or install the extension to ~/.pi/agent/extensions/decisors/index.js
uv run decisors integrate pi
```

Then in your Pi chat session:
```text
/reload
/decision status
/decision test
```

To run a headless bridge verification session:
```bash
python -c '
import json, subprocess
p = subprocess.Popen(["decisors", "bridge"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
p.stdin.write(json.dumps({"id": "1", "method": "status", "params": {}}) + "\n")
p.stdin.flush()
print(p.stdout.readline())
p.terminate()
'
```

---

## Pull Request Guidelines

1. **Branch Naming**: Use descriptive branch names like `feat/new-referee-rule`, `fix/conclude-tournament`, or `docs/getting-started`.
2. **Atomic Commits**: Follow Conventional Commits format (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`).
3. **Test Coverage**: Accompany any new feature or bug fix with corresponding tests in `tests/`.
4. **Preserve Integrity**: Do not commit secrets, tokens, or local cache directories.
