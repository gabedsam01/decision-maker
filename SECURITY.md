# Security Policy

## Reporting Security Vulnerabilities

If you discover a security vulnerability or potential risk within **Decisors**, please do not open a public issue. Instead, report it privately to the maintainers:

- **Maintainer**: Gabriel Sampaio
- **GitHub**: [@gabedsam01](https://github.com/gabedsam01)
- **Security Contact**: Contact via GitHub Security Advisories or direct secure communication.

Please include:
1. A description of the vulnerability and its potential impact.
2. Steps or a minimal reproducer script showing how the vulnerability can be triggered.
3. Relevant environment details (OS, Python version, provider configuration).

We appreciate responsible disclosure and will acknowledge receipt and work promptly on a remediation.

---

## Security Architecture & Principles

Decisors is designed as a **System One decision engine** for AI agents. Because it directly influences agent routing and tool execution, security and privacy are core architectural tenets:

### 1. Local-First Sovereignty
- **Default Provider**: Local Laya (`laya`) running completely on-device.
- **Zero Outbound Traffic**: When running with Laya, no external network requests are dispatched. Model weights are downloaded and verified once via the standard Hugging Face hub cache (`~/.cache/huggingface/hub`) and loaded directly into local memory.
- **No Telemetry**: Decisors does not collect usage analytics, telemetry, or user prompts.

### 2. Explicit Cloud Consent & No Silent Fallback
- **No Silent Fallback**: Decisors will **never** automatically or silently fall back from local execution to a remote cloud provider upon an error or threshold breach.
- **Session-Level Explicit Opt-In**: Cloud providers (`typesafe` or `openrouter`) require explicit user confirmation during `/decision start` or before running cloud-routed options via `decision_where`.
- **Sensitive State Warning**: The agent interface warns users before sending any context to cloud endpoints.

### 3. Protection of Secrets and Credentials
- **Credential Storage**: API keys (`TYPESAFE_API_KEY`, `OPENROUTER_API_KEY`, `HF_TOKEN`) and Pi credentials (`~/.pi/agent/auth.json`) are accessed in-memory only.
- **Log and Error Sanitization**: Bridge error handlers and exception formatters strip raw tokens, authorization headers, and credential blobs before transmitting results to Pi or printing to terminal stdout/stderr.
- **Local Config**: Configuration stored in `~/.config/decisors/config.toml` holds non-sensitive settings only.

### 4. Confidence Is Not Authorization
- **Distribution Concentration**: The `confidence` score returned by Choice, Score, or Noul models reflects the concentration of the model's categorical distribution. It is **not** a mathematical proof of factual correctness, an authorization token, or a safety guarantee.
- **Destructive Command Barrier**: The deterministic Referee (`decision_command`) inspects bash commands for dangerous patterns (`rm -rf`, `mkfs`, `dd if=`, `git reset --hard`, `chmod 777`, `git push --force`) and immediately marks them as unauthorized (`authorized: false`, `verdict: "risco"`).
- **Destructive Actions**: Under no circumstances should downstream agents or tools interpret high model confidence as sufficient permission to execute irreversible or destructive system actions without human approval.

---

## Supported Versions

| Version | Supported          |
| :------ | :----------------- |
| 0.1.x   | :white_check_mark: |
| < 0.1.0 | :x:                |
