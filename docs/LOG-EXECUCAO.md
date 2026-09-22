# Log de execução — audit + cleanup + empacotamento (2026-09-22)

Transparência total: cada etapa registra **quais ferramentas/pacotes foram usados**.
Regra de evidência: nenhuma afirmação de teste/build/edição sem a saída da ferramenta no mesmo turno.

## Etapa 0 — Preflight

- `advisor` — validação de plano antes de trabalho substancial.
- `bash` (`pwd`, `git status --short`, `git branch`) — árvore limpa; branch `main`; único untracked: `docs/AUDITORIA-E-PLANO.md`.
- `bash` (credenciais, só existência) — `npm whoami` = `ENEEDAUTH`; `~/.npmrc` ausente; `~/.pypirc` ausente; env `TWINE_*`/`UV_PUBLISH_*`/`NPM_TOKEN` ausente; `gh auth` = logado (gabedsam01, gabrielsampaiosouza).
- `bash` (grep kaggle|kgat) — hits em exatamente 2 arquivos: `docs/plano-inferencia-kaggle.md`, `docs/AUDITORIA-E-PLANO.md`.
- `bash` (nomes de registro) — npm `decisors` = 404 (livre); PyPI `decisors` = 404 (livre).
- `subagent {action:"list", capabilities:true}` — lane saudável; identificada a causa do 403 anterior: agentes `researcher`/`qa`/`devops`/`docs` apontam para modelo `opencode-go/*` (sem assinatura) → dispatch com modelo pinado `openai-codex/gpt-5.6-luna`.
- Decisão aplicada do usuário: "a opção 1 é o padrão" → arquitetura recomendada (processo por sessão + warm-up em background; **sem MCP**) e empacotamento A (laya padrão). **Publicação real PyPI/npm = ADIADA** (sem token); artefatos + comandos prontos no fim.

## Etapa 1 — Purge Kaggle (em andamento)

- `memory_add` — correção durável: tema Kaggle descartado, chave revogada, não reabrir.
- `write`/`edit` (docs) + `bash rm` + `grep` de verificação — ver seções seguintes.

## Etapa 2 — Fixes da auditoria (CONCLUÍDA)

- **P0.1** `remote.status()` agora usa `get_credential` (mesma fonte do `_key()`) — corrige o "Jev não ativo". + teste `test_status_ready_follows_credential_store_not_just_env`.
- **P0.2** Juiz Laya cacheado (`_judge_provider`) em vez de um load de checkpoint (~67 s) por chamada. + teste `test_referee_local_reuses_one_loaded_judge`.
- **P2** Removidos: `conclude_local`+`Choose`+`OTHER` (+2 testes órfãos), `_loaded_for_init`, `ROWS`, `clip()`, `try/except` no-op, import duplicado de `get_credential`; `integrate.py` unificado em `importlib.resources`.
- **P1.6/P1.7** JS não lê mais `auth.json` (só o core resolve credenciais); spawn ganhou fallback `~/.local/bin/decisors`.
- **P1.8/P1.9** CI: `node --test tests/test_panel_keys.mjs`, `uv lock --check`, `uv build` + smoke do wheel.
- **P3.22** Limites do contrato documentados em `docs/API_REFERENCE.md` §5.
- **2 respins da auditoria, provados por build real:** P3.20 (classifier de licença) REVERTIDO — setuptools PEP 639 levanta `InvalidConfigError` com classifier + `license="MIT"` SPDX; P3.19 (mypy 3.11) REVERTIDO — stubs do numpy usam `type` statement 3.12+ e o mypy morre dentro do numpy; mantido 3.12 com comentário explicando.
- Ferramentas: `edit`, `pytest`, `ruff`, `mypy`, `node --test`. Evidências: `55 passed` → `53 passed` (−2 testes mortos), `All checks passed!`, `Success: no issues found in 17 source files`, `✔ test_panel_keys.mjs`.

## Etapa 3 — Limpeza total (CONCLUÍDA)

- `rm -rf`: `build/`, `src/decisors.egg-info/`, `integrations/` (duplicado do docs), `src/decisors/README.md` ("ainda não implementar" — falso), caches. Raiz limpa conferida com `ls`.

## Etapa 4 — Binário + segurança (CONCLUÍDA)

- `uv build` → `dist/decisors-0.1.0-py3-none-any.whl` + `dist/decisors-0.1.0.tar.gz`.
- `uv tool install --force <wheel>` → `Installed 1 executable: decisors` (binário gerenciado a partir do wheel).
- Smoke do binário: `--help` ok · bridge JSONL `ping`→`{"protocol":1,"ok":true}` · `shutdown`→ok · **CLI em 0,117 s** ("extremamente rápido" ✓).
- Verificação de segurança (skill `code-security`): secret scan (`rg`) **0 hits** no repo · **0 hits** no histórico git · nenhum `.env` nosso (só `.env.example` do clone de referência gitignored) · `.gitignore` cobre `.env*`/`auth.json` · `pip-audit`: **No known vulnerabilities found** · `bandit`: 7 achados → 2×B310 corrigidos de verdade (checagem de scheme `https` antes de `urlopen`) + 5 `# nosec` justificados (B110×2 degradação intencional; B404/B603/B607 subprocess com argv constante, sem shell, timeout 2 s) → resultado final **No issues identified** (1.699 linhas).

## Etapa 5 — Implementação (CONCLUÍDA)

- **Bridge daemon** (`bridge.py`): socket UNIX `$XDG_RUNTIME_DIR/decisors/bridge.sock` (fallback `/tmp/decisors-$UID/`), singleton por bind (stale socket detectado via ping), `chmod 700/600`, pidfile, idle-timeout (900s, `DECISORS_IDLE_TIMEOUT`) que descarrega e encerra → nada 24h, nada no boot. Ctrl+C 1º = graceful, 2º = `os._exit(130)` forçado. Métodos novos: `warm` (start_async) e o ciclo `call_daemon`/`spawn_daemon`/`wait_for_socket`/`force_kill_daemon`.
- **Engine** (`engine.py`): `start_async()` (warm-up em thread, nunca dentro de tool call), estado `warming`/`warmup_error`, evaluate fail-fast durante warm-up, intenção persistida em `Settings.active` (auto-restart respeita stop explícito; kill forçado preserva active=true → a próxima sessão auto-restarta).
- **CLI** (`cli.py`): `start` não-bloqueante via daemon, `stop` via daemon, `kill [--force]`, `status` honesto (daemon vivo = verdade; daemon morto = config-only com nota — mata o antigo "CLI mente sobre ready/active"). `bridge --daemon` para o modo socket.
- **Adapter Pi** (`pi-extension.js`): BridgeClient via socket UNIX (connect-or-spawn, retry 12×250ms), `session_start` = keep-active se quente / auto-restart (`warm`) se a sessão anterior estava ativa, `session_shutdown` = detach (daemon sobrevive; self-stop no idle), abort/timeout isolados por request (não matam o daemon), footer mostra `warming`.
- **Empacotamento**: `package.json` (nome `decisors`, bin `decisors-pi`, postinstall) + `install.mjs` (instala os 3 assets no `~/.pi/agent` + checa o binário). Validação: `npm pack --dry-run` → `decisors-0.1.0.tgz` 16,9 kB / 7 arquivos; smoke do `install.mjs` com HOME=tmp instalou os 3 assets e achou o binário.
- **Testes novos**: `tests/test_daemon.py` (round-trip no socket + warm não-bloqueante + persistência de intenção) e dispatch `warm` em test_bridge. Evidência final: **56 passed** · ruff · mypy · node.
- **Smoke end-to-end do ciclo de vida** (binário regenerado do wheel — a 1ª rodada pegou o wheel antigo e foi descartada por comportamento divergente): `decisors start` = **0,232s** com `warming:true` · warm-up real em background pronto em **~45s** · keep-active entre processos (`active/ready: true`) · `kill` gracioso `{"forced": false, "shutdown": true}`.
- **Code-review subagente** (lane `code-reviewer`, modelo luna após grok degradar): CHANGES REQUESTED → P0 do `engine.status()` sem instanciação corrigido (com regressão em test_engine), P1 da doc `PI_INTEGRATION.md` corrigida, P2 do `MAX_QUESTION_ID` corrigido (constante real em domain.py). Artefatos: `subagent-artifacts/outputs/715f54eb-.../review.md`.
- **2 respins da auditoria provados por build real**: classifier de licença inválido com PEP 639 (setuptools erro); mypy 3.11 quebra nos stubs do numpy (mantido 3.12 com comentário).
- **Subagentes**: 1º run `6d3eb131-4f11-401f-b135-8befe2172c6d` = failed ("Service temporarily unavailable... degraded", artefato com 1 linha); retentativa `35e45e0f-d106-4c63-bacb-5ec70e1992d5` = **completed** com review real.

## Adiados (reportados ao usuário)

1. **Publicação real PyPI/npm** — sem `~/.pypirc`/`~/.npmrc`/tokens no env (comprovado no preflight). Comandos prontos: `uv publish dist/*` e `npm publish --access public`.
2. **MCP** — fora de escopo por decisão do usuário.
3. `docs/tools-complemento.md` — nota interna ainda no repo público.
4. Política de timeout P3.21 (timeout de evaluate no Laya).
5. Refresh do README/GETTING_STARTED com o novo ciclo de vida (fluxo funciona; docs ainda descrevem o comportamento antigo em pontos pontuais).

## Etapa 6 — Commit, PR e CI

- Guard local (guard-git) bloqueou commit direto no `main` → fluxo padrão: branch `feat/session-lifecycle` + commit `feat: session lifecycle daemon, audit fixes, and npm/PyPI packaging` + push.
- `gh` tinha a conta ativa errada (`gabrielsampaiosouza`, sem acesso ao repo) → `gh auth switch --user gabedsam01` e **PR #1**: https://github.com/gabedsam01/decision-maker/pull/1 (CI disparado por `pull_request`: pytest 3.11/3.12/3.13 · ruff · mypy · node · `uv lock --check` · smoke do wheel).
- `workflow_dispatch` adicionado ao ci.yml para trigger manual; README: `engine.init()` inexistente corrigido para `initialize()` + comandos `start`/`status`/`kill` (itens 5 e parcialmente 1 da lista de adiados resolvidos aqui).
