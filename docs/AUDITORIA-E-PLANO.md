# Decisors — Auditoria completa e plano consolidado

Data: 2026-09-22. Escopo: varredura de ponta a ponta (cabeça, corpo e rabo) do repositório,
mais os 4 pontos pedidos: auditoria de código, startup/warm-up do LLM, pré-requisitos de
instalação e validação do fluxo na documentação oficial do MCP.

## 0. Método e evidências

Método: leitura integral de `src/`, `tests/`, `docs/`, `pyproject.toml`, CI e configurações;
execução de testes e lint; pesquisa web nas fontes oficiais para o ponto 4; tentativa de
subagentes (researcher + code-reviewer) — **falharam por infraestrutura** (researcher:
`403 "An active OpenCode Go subscription is required to use Go models."`; code-reviewer:
modelo indisponível após 706 s). A validação do ponto 4 foi feita por pesquisa web direta.

Evidências coladas (executadas em 2026-09-22 nesta máquina):

```text
$ uv run pytest
53 passed in 2.41s

$ uv run ruff check src tests
All checks passed!

$ uv run mypy src
Success: no issues found in 17 source files

$ uv run python -c "...versions..."
py 3.13.14
laya 0.3.5
torch 2.14.0

$ uv tool list | grep -i decisors
decisors v0.1.0
```

Nenhum carregamento de modelo foi executado nesta auditoria. Números de tempo de carga citados
adiante vêm da sessão de 2026-09-22 (medida anterior: `prepare` ≈ 67 s) e são **estimativas**,
não medições novas.

---

## 1. Ponto 1 — Auditoria completa do código

### 1.1 Resumo executivo

O núcleo está sólido para o tamanho (validação de entrada rigorosa, erros sem segredo, contrato
único `choice`/`score`/`noul`, config atômica com permissão 600, adapter fino, 53 testes em
2,4 s, CI com lint+tipos+testes). Os problemas concentram-se em: **1 bug que explica a queixa
antiga do "Jev não mostra ativo"**, custos escondidos de carregamento de modelo, duplicação de
resolução de credencial entre JS e Python, artefatos órfãos e uma nota interna com telemetria
pessoal em repo público.

### 1.2 P0 — bugs e correções (fazer primeiro)

| # | Problema | Onde | Plano de ação |
|---|---|---|---|
| 1 | **`status()` mente sobre credencial.** `RemoteJevProvider.status()` monta `ready` com `os.environ.get(self.key_env)`, mas `_key()` usa `config.get_credential` (env **ou** `~/.pi/agent/auth.json`). Com a chave só no `auth.json`, o status diz "não pronto" mesmo funcionando. **É a causa provável da queixa anterior "O Jev do OpenRouter não mostra que está ativo"** | `src/decisors/providers/remote.py:148` (`status`) vs `:66` (`_key`) | Trocar `os.environ.get(...)` por `bool(get_credential(self.name))`; teste unitário com chave só em arquivo |
| 2 | **Carga de modelo escondida por chamada.** `engine._conclude_local` cria um `LayaProvider` **temporário** (load completo do checkpoint, `prepare` ≈ 67 s) a cada `decision_where`/conclusões quando o provider ativo não é o Laya — e ainda exige `active` quando é. Custo invisível e incoerente com a escolha de provider do usuário | `src/decisors/engine.py:114-141` | Singleton de Laya para o juiz com cache entre chamadas (ou exigir `provider=laya` para o referee local e dizer isso no erro); nunca `load` por chamada |
| 3 | **CLI `start`/`stop` são desperdício/no-op.** `decisors start` carrega o modelo inteiro e **encerra o processo** (o load é jogado fora). `decisors stop` opera um engine recém-criado, ou seja, não para nada. Da memória da sessão anterior: "`decisors status/doctor` abre processo novo e mente sobre ready/active" | `src/decisors/cli.py:52-53, 87-90` | Remover `start`/`stop` do CLI standalone (o bridge persistente é o único dono do ciclo de vida); em `status`/`doctor`, imprimir que o processo é efêmero e que só o bridge da sessão fala a verdade |

### 1.3 P1 — qualidade, segurança e privacidade

| # | Problema | Onde | Plano de ação |
|---|---|---|---|
| 4 | **Nota interna de produto no repo público.** `docs/tools-complemento.md` é nota interna (não é doc do usuário final) | `docs/tools-complemento.md` | Separar `docs/` público de `notas/` interna (gitignored) |
| 6 | **Credencial resolvida em dois lugares e acoplada ao Pi.** O `BridgeClient` (JS) lê `~/.pi/agent/auth.json` e injeta no env; o Python (`config.get_credential`) lê o mesmo arquivo. Além da duplicação, o **core** depende de caminho do Pi — Claude Code/Codex/OpenCode não têm `auth.json` | `src/decisors/integrations/pi-extension.js:44-58`, `src/decisors/config.py:19-38` | Resolução de credencial só no Python (env → XDG → gaveta por cliente); o JS só faz `spawn`. É pré-requisito do ponto 2 (multi-cliente) |
| 7 | **`spawn("decisors")` depende do PATH do processo do Pi.** Sem o console script no PATH do host, o erro é `ENOENT` genérico na primeira chamada | `src/decisors/integrations/pi-extension.js:59` | Mensagem de erro já existe; acrescentar detecção documentada (`uv tool install decisors`) e, se possível, tentar `~/.local/bin/decisors` como fallback |
| 8 | **Teste JS nunca roda no CI.** `tests/test_panel_keys.mjs` (92 linhas) é executável com `node --test`, mas o CI roda só `pytest` | `.github/workflows/ci.yml`, `tests/test_panel_keys.mjs` | Adicionar step `node --test tests/` no CI |
| 9 | **CI sem smoke de empacotamento.** Não há build de sdist/wheel nem `uv sync --locked` — regressão de packaging passa despercebida | `.github/workflows/ci.yml` | Steps: `uv lock --check` (ou `uv sync --locked`), `uv build`, instalar o wheel num venv limpo e `decisors --help` |

### 1.4 P2 — código morto, redundante e simplificação

| # | Problema | Onde | Plano de ação |
|---|---|---|---|
| 10 | `referee.conclude_local` + tipo `Choose` só são usados pelos testes; o engine usa `conclude_scored` | `src/decisors/referee.py:268-313` | Decidir: deletar (e os testes junto) ou promover a API pública documentada. Hoje é flexibilidade morta |
| 11 | `LayaProvider._loaded_for_init` é atribuído e nunca lido | `src/decisors/providers/laya.py:62,168,258` | Remover o campo |
| 12 | `ROWS` duplica `SECTIONS` sem uso; `clip()` é sombra de `fit()` | `src/decisors/integrations/pi-extension.js:188, 282` | Deletar os dois |
| 13 | `try: ... except Exception: raise` sem efeito | `src/decisors/providers/remote.py:113-116` | Remover o `try` |
| 14 | `get_credential` importado no topo e re-importado dentro de `_catalog()` | `src/decisors/engine.py:11, 226` | Ficar só com o import do topo |
| 15 | `install_pi_assets` usa `Path(__file__).parent`; `install_pi_extension` usa `importlib.resources` | `src/decisors/integrate.py:12, 33` | Unificar em `importlib.resources` |
| 16 | `src/decisors/README.md` diz "Ainda não implementar código" — falso hoje | `src/decisors/README.md` | Apagar (o README raiz já cobre) |
| 17 | `integrations/pi/README.md` duplica `docs/PI_INTEGRATION.md` | `integrations/pi/README.md` | Apagar o duplicado, manter `docs/` |
| 18 | `build/lib/` guarda cópias **obsoletas** do pacote (`pi-extension.js` com 709 linhas vs 983 atuais); `src/decisors.egg-info/` é lixo de build | `build/`, `src/decisors.egg-info/` | `rm -rf` (já estão no `.gitignore`, mas confundem varredura e handoff) |

### 1.5 P3 — polish de config, CI e docs

| # | Problema | Plano de ação |
|---|---|---|
| 19 | `mypy python_version = "3.12"` diverge de `requires-python >=3.11` e `ruff target py311` | Alinhar tudo em 3.11 |
| 20 | `pyproject.toml` sem classifier `License :: OSI Approved :: MIT` | Acrescentar |
| 21 | `Settings.timeout_seconds` (15 s) não é aplicado a `LayaProvider.prepare/evaluate` (só probe remoto e HTTP) | Definir política explícita: init sem timeout (com progresso), evaluate com timeout; alinhar `INIT_TIMEOUT_MS` do JS |
| 22 | `MAX_QUESTIONS = 32` no `domain.py` não aparece na documentação pública | Documentar no `API_REFERENCE.md` |

### 1.6 O que está bom (manter como está)

- `domain.py`: validação de entrada completa (JSON-safe, limites de tamanho, tipos por questão).
- `errors.py`: mensagens seguras, sem vazar estado/segredo.
- `config.py`: escrita atômica (`mkstemp` + `fsync` + `chmod 600` + `os.replace`), sem segredo persistido.
- `bridge.py`: protocolo JSONL minimalista e à prova de erro; adapter Pi sem lógica de provider (regra do `AGENTS.md` cumprida).
- Consentimento de nuvem explícito por sessão no adapter; limite de requests remotos por sessão.
- `.gitignore` completo (venv, caches, `build/`, `egg-info`, `referencia/`, `auth.json`).
- Testes rápidos (2,4 s) e CI com lint + tipos estritos + matriz Python 3.11–3.13.

---

## 2. Ponto 2 — Startup lento e warm-up em segundo plano

### 2.1 Diagnóstico do comportamento real de hoje

Primeiro, a precisão sobre o que o código faz (importante porque a pergunta assume "residente
desde o início"):

1. No `session_start` do Pi, o adapter sobe o `decisors bridge` (subprocesso Python persistente) só para responder `status` — **sem modelo em RAM**.
2. O modelo só entra em RAM quando o usuário roda `/decision init` ou `/decision start`: `LayaProvider.prepare()` faz `router.load(target)` + um `predict` de aquecimento, **de forma síncrona dentro do tool call** (timeout de 15 min no JS). Medição da sessão anterior: `prepare` ≈ 67 s bloqueando.
3. Depois disso o modelo fica residente **dentro do bridge** até `/decision stop` ou o fim da sessão.
4. Ctrl+C×2 no cliente mata o bridge junto (por design — processo filho). Ao reabrir, tudo recarrega do zero.

Ou seja: o modelo **não** fica residente desde o início; ele fica residente **depois** do
init/start. Os defeitos reais são: (a) o carregamento é síncrono e trava o cliente; (b) não há
aquecimento em segundo plano enquanto o usuário faz outra coisa; (c) cada sessão paga o load
inteiro de novo. O requisito "nada 24h / nada no boot" **já é atendido hoje** (não existe
systemd, docker nem serviço) e deve continuar sendo.

### 2.2 Requisitos → desenho alvo

| Requisito | Desenho |
|---|---|
| Nada rodando 24h, nada no boot, nenhum container permanente | Processo servidor **por sessão de cliente**, nascido e morto com ela (transporte MCP `stdio`) |
| LLM carregado em segundo plano enquanto o usuário gerencia o agente | Thread de warm-up disparada **depois** do handshake MCP; o handshake nunca bloqueia em carga |
| Disponível imediatamente ao terminar, sem travar o cliente | Tool de status (`warming`/`ready`/`error` + modelo + device); `decision_evaluate` atende na hora quando `ready` |
| Tool call durante o warm-up não pode passar de timeout de cliente | Falha rápida com resposta estruturada `{status:"not_ready", eta…}` — **carga de modelo nunca dentro de `tools/call`** (validado: §4.5 — Codex corta tool call em 60 s por padrão) |
| Vale para Claude Code, Codex, OpenCode e outros | Fronteira única: servidor MCP (`decisors mcp`); cada cliente registra o mesmo comando |
| Init explícito com progresso | **`decision_init` dispara o trabalho e retorna na hora** (job em background); progresso via polling do status + `notifications/message` (logging). `notifications/progress` só serve dentro de request ativo com `progressToken` (validado: §4.4) |

### 2.3 Opções consideradas (escolher A/B/C/D)

- **A — MCP stdio por sessão + warm-up em thread pós-handshake (RECOMENDADO).** Atende todos os requisitos literalmente. Custo: cada sessão paga o warm-up (~1 min) — porém em segundo plano, sem travar ninguém. É o que a seção 4 valida na spec.
- **B — Daemon local com idle-timeout.** Sobe sob demanda na primeira chamada e se auto-apaga após N minutos ocioso (estilo qwen-modal). Disponibilidade instantânea entre sessões, mas é serviço residente temporário (porta, lock, versionamento, "quem mata?") e toca na borda do "nada 24h". Só como opt-in futuro, default desligado.
- **C — Manter o bridge JSONL do Pi e só paralelizar o load.** Resolve o travamento no Pi, mas **não** atende "qualquer agente cliente". Insuficiente.
- **D — Inferência remota em serviço externo.** Fora: sem serviço de serving síncrono adequado no horizonte estudado.

Recomendação: **A**. O bridge JSONL atual vira o transporte interno do Pi (não construir os dois
na mesma etapa).

---

## 3. Ponto 3 — Pré-requisitos de instalação

### 3.1 O que é usado hoje (confirmado, não especulado)

- **Motor/gerenciador: é o `uv` mesmo** (Astral, escrito em Rust). Confirmado por: `uv.lock` (266 KB) na raiz; CI usa `astral-sh/setup-uv@v3`; `which uv` → `~/.local/bin/uv`; `decisors v0.1.0` instalado como **uv tool** (`~/.local/bin/decisors`). O build backend do pacote é `setuptools>=75` — o uv orquestra o ambiente, não substitui o backend.
- **O usuário precisa de Python, não só de Node.** Hoje "parece depender só de Node" porque o plugin do Pi é JS, mas o `pi-extension.js` faz `spawn("decisors", ["bridge"])` — um **console script Python**. Na prática a instalação atual exige: Python ≥3.11 + pacote `decisors` no PATH. Isso está implícito hoje e é a origem da confusão — precisa ficar explícito.
- **Cadeia de dependências pesada (medida):** `decisors` → `laya 0.3.5` → `torch 2.14.0` + `transformers` + `huggingface_hub` + `safetensors`. O `torch` no Linux puxa `cuda-toolkit`/`cuda-bindings` mesmo em máquina sem GPU → **venv medido neste host: 5,5 GB**. Pesos dos modelos (memória da sessão anterior): ≈644 MB multilingual / ≈843 MB english no cache Hugging Face. Downloads de peso no primeiro init são irreduzíveis (produto local-first).
- **Node:** só é necessário porque o Pi é Node. Para Claude Code/Codex/OpenCode via MCP, o pré-requisito passa a ser só Python (resolvido pelo uv).

### 3.2 Pré-requisitos mínimos propostos

| Item | Hoje | Proposto | Por quê |
|---|---|---|---|
| Python ≥3.11 | obrigatório (implícito) | obrigatório — **resolvido automaticamente pelo uv** | `laya`/`torch` são Python |
| `uv` | recomendado | **único gerenciador exigido** (alternativa aceita: `pip` num Python existente) | Rust, rápido, baixa o Python sozinho |
| Node | exigido na prática para o Pi | **opcional** (só para o adapter do Pi) | cliente é quem define |
| torch + CUDA (GBs) | baixado sem pedido | **CPU-only por padrão** (índice extra do torch) | 5,5 GB → centenas de MB |
| Pacotes Git / build tools | — | nunca exigir | wheels prontos no PyPI |
| Pesos HF (~650–850 MB) | baixados no init | igual, com progresso visível | irreduzível |
| Rede | só no init | só no init | depois roda offline |

Rota de instalação alvo para o usuário final (um comando):

```fish
uv tool install decisors          # uv resolve o Python se não houver
decisors doctor                   # confere runtime, pesos e credenciais
```

E a variante fina (decisão aberta abaixo): `decisors[local]` com laya+torch-cpu como extra, e
`decisors[remote]` (Jev/nuvem) sem torch nenhum, para quem só usa a nuvem.

### 3.3 Decisão aberta (precisa do seu A/B/C/D)

- **A — `decisors` com `laya` como dependência padrão** (local-first, como o `AGENTS.md` manda), mas com torch **CPU-only** por constraint/índice extra. Instalação maior, zero surpresa.
- **B — extras explícitos**: `pip install "decisors[local]"` puxa laya+torch-cpu; `decisors[remote]` não puxa torch. Instalação mínima para usuário só-nuvem; mas o default do produto deixa de ser local.

Recomendação: **A** para o produto (regra 1 do `AGENTS.md`), com B documentado para quem só quer Jev.

---

## 4. Ponto 4 — Validação na documentação oficial do MCP

Fontes: spec oficial MCP **2025-11-25** (modelcontextprotocol.io), docs do Claude Code, docs do
Codex e docs do OpenCode. Pesquisa feita em 2026-09-22. Cada item traz URL + trecho.

### 4.1 Transporte e ciclo de vida: processo por sessão, morre com o cliente — **SUPORTADO**

> "In the **stdio** transport: The client launches the MCP server as a subprocess. The server reads
> JSON-RPC messages from its standard input (`stdin`) and sends messages to its standard output
> (`stdout`)." — [Transports, spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)

> "During the shutdown phase, one side (usually the client) cleanly terminates the protocol
> connection... For the stdio transport, the client **SHOULD** initiate shutdown by: 1. First,
> closing the input stream to the child process (the server) 2. Waiting for the server to exit, or
> sending `SIGTERM`... 3. Sending `SIGKILL`... The server **MAY** initiate shutdown by closing its
> output stream to the client and exiting." — [Lifecycle, spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)

Implicação: o servidor stdio nasce com a sessão do cliente e morre com ela — **nada sobe no boot,
nada fica 24h, nada entre sessões**. O shutdown gracioso (descarregar o modelo antes de sair) cabe
no "server MAY initiate shutdown by... exiting" e no fechamento de stdin. O transporte alternativo
(Streamable HTTP) é explicitamente "an independent process that can handle multiple client
connections" — ou seja, um serviço residente, o que contradiz o requisito; fica fora do escopo
(opção B do §2.3, só como opt-in futuro).

### 4.2 Handshake rápido e warm-up depois do `initialized` — **SUPORTADO**

> "After successful initialization, the client **MUST** send an `initialized` notification to
> indicate it is ready to begin normal operations... The server **SHOULD NOT** send requests other
> than pings and logging before receiving the `initialized` notification." — [Lifecycle, spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)

Implicação: o handshake é negociação de capacidades — **a spec não exige que nada esteja
"pronto" além de responder**. Depois do `initialized`, o servidor pode disparar o warm-up em
thread de fundo sem bloquear ninguém. O `initialize` **MUST NOT** ser cancelado pelo cliente
([Cancellation](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/cancellation)),
logo ele precisa ser barato e rápido.

### 4.3 `tools/list` durante o warm-up — **SUPORTADO (mas tem janela de 5 s em um cliente)**

> To discover available tools, clients send a `tools/list` request... `listChanged` indicates
> whether the server will emit notifications when the list of available tools changes." — [Tools, spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)

> `timeout` — "Timeout in ms for fetching tools from the MCP server. Defaults to **5000 (5 seconds)**." — [OpenCode: MCP servers](https://opencode.ai/docs/mcp-servers/)

Implicação: as tools devem ser listáveis **instantaneamente**, com o modelo ainda frio (a
ferramenta `decision_status` já descreve `warming`). Opcional: declarar `listChanged` e emitir a
notificação quando o estado muda. Limite duro: responder `tools/list` em <5 s sempre.

### 4.4 Progresso do warm-up — **SUPORTADO com nuance (progress só dentro de request ativo)**

> "When a party wants to receive progress updates for a request, it includes a `progressToken` in
> the request metadata... The receiver **MAY** then send progress notifications containing: The
> original progress token, the current progress value so far, an optional 'total' value, and an
> optional 'message' value." — [Progress, spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/progress)

> "Progress notifications **MUST** only reference tokens that: Were provided in an active request;
> Are associated with an in-progress operation." — mesma página

Implicação: `notifications/progress` só existe **ancorada a um request em voo** (ex.: uma tool call
de init que o cliente fez com `progressToken`). O warm-up disparado sozinho em background **não**
tem request dono, logo não pode usar `progress`; para ele, o caminho validado é: tool
`decision_status` (polling com %/ETA) e, como gosto, `notifications/message` do capability
`logging` — a spec permite logging do servidor antes mesmo do `initialized` (§4.2).

### 4.5 Tempo de `tools/call`: por que a carga NÃO pode morar dentro de tool call — **VALIDADO (restrição de projeto)**

Spec:

> "Implementations **SHOULD** establish timeouts for all sent requests... Implementations **MAY**
> choose to reset the timeout clock when receiving a progress notification corresponding to the
> request... However, implementations **SHOULD** always enforce a maximum timeout, regardless of
> progress notifications." — [Lifecycle → Timeouts, spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)

Codex (o mais rígido):

> "`tool_timeout_sec` (optional): Timeout (seconds) for the server to run a tool. **Default: 60**."
> "`startup_timeout_sec` (optional): Timeout (seconds) for the server to start. **Default: 10**." — [Codex: Model Context Protocol](https://developers.openai.com/codex/mcp)

Claude Code:

> "The per-server `timeout` is a **hard wall-clock limit per tool call, and progress notifications
> from the server don't extend it**... falls through to `MCP_TOOL_TIMEOUT`, or to its default of
> about 28 hours when that variable is unset... A tool call to an MCP server that sends no response
> and no progress notification for the idle window aborts with an error... The idle window
> defaults to five minutes for HTTP, SSE, WebSocket... and to **30 minutes for stdio servers**." — [Claude Code Docs: MCP](https://code.claude.com/docs/en/mcp)

Implicação dura para o projeto: `prepare()` do Laya já foi medido em **≈67 s** — acima do
timeout padrão do Codex (60 s) e perto de qualquer limite razoável. Portanto, **toda carga de
modelo acontece em thread de fundo, fora de `tools/call`**; as tools são sempre rápidas:
`decision_init`/`decision_start` **disparam o job e retornam imediatamente**, `decision_status`
informa o progresso, `decision_evaluate` devolve `{status:"not_ready"}` estruturado enquanto
não estiver pronto. Risco residual conhecido (comportamento de cliente varia entre versões —
ver [issue anthropics/claude-code#58687](https://github.com/anthropics/claude-code/issues/58687):
cliente derrubou tool call longa apesar de progress): com tools sempre <1 s, esse risco some.

### 4.6 Cancelamento e ping — **SUPORTADO**

> "When a party wants to cancel an in-progress request, it sends a `notifications/cancelled`
> notification containing: The ID of the request to cancel; An optional reason string." — [Cancellation, spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/cancellation)

Implicação: um `decision_init` em andamento pode ser cancelado; o receptor **SHOULD** "Stop
processing the cancelled request / Free associated resources" — a thread de warm-up deve checar
cancelamento e descarregar o modelo se cancelada. Ping (`basic/utilities/ping`) existe nas duas
direções para keep-alive de conexão (relevante só para HTTP).

### 4.7 Consentimento de nuvem via Elicitation — **PARCIAL (spec define; suporte por cliente varia)**

> "The Model Context Protocol (MCP) provides a standardized way for servers to request additional
> information from users through the client... Elicitation supports two modes: **Form mode**:
> Servers can request structured data from users... **URL mode**: Servers can direct users to
> external URLs for sensitive interactions... Clients that support elicitation **MUST** declare the
> `elicitation` capability during initialization." — [Elicitation, spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation)

Implicação: o consentimento "usar a nuvem nesta chamada?" pode ser um `elicitation/create`
(modo `form`, pergunta sim/não) **quando o cliente declarar a capability**. Como nem todo
cliente declara, o fallback validado é o mesmo do Pi hoje: a tool devolve `{mode:"ask", ...}` e o
agente pergunta ao usuário na conversa; só uma resposta explícita do usuário libera a chamada
remota. Nunca fallback silencioso para a nuvem (regra 3 do `AGENTS.md`).

*Suporte por cliente desta capability: a validar na implementação (a spec define; as docs lidas
de Codex/OpenCode não detalham elicitation).*

### 4.8 O servidor fica quente ENTRE sessões? — **NÃO (confirmado)**

Nada na spec mantém um servidor stdio vivo entre sessões de cliente: o processo é filho do
cliente (§4.1) e o shutdown fecha stdin + SIGTERM/SIGKILL. Streamable HTTP é que é "independent
process" com `MCP-Session-Id` e `DELETE` para encerrar sessão — modelo de serviço residente.
Conclusão: para o requisito "nada 24h", stdio por sessão é o único transporte que satisfaz
literalmente; o custo é cada sessão pagar o warm-up (~1 min, em segundo plano).

### 4.9 Matriz de configuração por cliente — **SUPORTADO nos quatro**

| Cliente | Como registra o `decisors mcp` (stdio) | Fonte |
|---|---|---|
| Claude Code | `claude mcp add decisors -- decisors mcp` ("Option 3: Add a local stdio server") ou `.mcp.json` | [Claude Code Docs: MCP](https://code.claude.com/docs/en/mcp) |
| OpenAI Codex | `~/.codex/config.toml`: `[mcp_servers.decisors]` com `command = "decisors"`, `args = ["mcp"]` ("STDIO servers: Servers that run as a local process (started by a command)") | [Codex: MCP](https://developers.openai.com/codex/mcp) |
| OpenCode | `opencode.json` → `mcp.decisors = { "type": "local", "command": ["decisors", "mcp"] }` | [OpenCode: MCP servers](https://opencode.ai/docs/mcp-servers/) |
| Pi | hoje: extensão + bridge JSONL (`decisors integrate pi`); depois pode adotar o mesmo servidor MCP | `docs/PI_INTEGRATION.md` |

### 4.10 Veredito de arquitetura

Dá para fazer "certinho" com MCP hoje, sem gambiarra:

1. **`decisors mcp`** (stdio, Python) — processo por sessão, morre com o cliente. ✅ spec §4.1
2. Handshake <1 s; `tools/list` imediato com as tools todas já descritas. ✅ §4.2/§4.3
3. Warm-up em **thread de fundo** disparada após `initialized`; nunca dentro de `tools/call`. ✅ §4.2/§4.5 (restrição dura do Codex 60 s)
4. Tools sempre rápidas: `decision_init/start` = trigger + retorno imediato; `decision_status` = estado/progresso; `decision_evaluate` = julga ou devolve `not_ready` estruturado. ✅ §4.5
5. Progresso: polling de status + `notifications/message`; `notifications/progress` só em ops rápidas com `progressToken`. ✅ §4.4
6. Cancelamento de job via `notifications/cancelled`; shutdown gracioso com descarga do modelo no fim da sessão. ✅ §4.6/§4.1
7. Consentimento de nuvem: `elicitation/create` quando disponível; senão, resposta `{mode:"ask"}`. ⚠️ §4.7 parcial

Única lacuna real: suporte de **elicitation** por cliente (§4.7) — com fallback pronto, não bloqueia nada.

---

## 5. Plano de ação consolidado (ordem de execução)

1. **P0.1** — fix da credencial em `remote.py::status` + teste (corrige a queixa "Jev não mostra ativo").
2. **P0.2/P0.3** — eliminar load temporário por chamada no `_conclude_local`; sanear CLI `start`/`stop`.
3. **Empacotamento/pré-requisitos** — torch CPU-only, extras, docs de instalação explícitos, fallback de PATH no spawn.
4. **Ponto 4** — validação MCP com citações (§4) → **aguardar aprovação antes das features** (pedido explícito).
5. **Feature do ponto 2** — `decisors mcp` (stdio) com warm-up em thread pós-`initialized`, `decision_init/start` como trigger imediato, `decision_status` para polling, `evaluate` com `not_ready` estruturado durante o warm-up, cancelamento e shutdown gracioso (conforme §4); adaptar clientes.
6. **Limpeza P1/P2** — código morto, READMEs obsoletos, `build/` + `egg-info`, step de teste JS e smoke de build no CI.
7. **P3** — alinhamento de versões no toolchain, classifiers, política de timeout.

## 6. Riscos e o que não foi testado

- Nenhum modelo foi carregado nesta auditoria; o tempo `prepare ≈ 67 s` é da sessão de 2026-09-22 (estimativa, sem JSON novo colado).
- A lane de subagentes falhou duas vezes por infraestrutura nesta sessão (403 de assinatura de modelo / modelo indisponível); se quiser, refaço a auditoria com subagente quando a lane estiver saudável — os achados acima vieram de leitura direta completa.
- Codex e OpenCode não estão instalados nesta máquina: a configuração deles será validada por documentação oficial (§4), não por execução.
- O bug P0.1 tem reprodução lógica clara (chave só em `auth.json`), mas a reprodução ponta a ponta num cliente real fica para a etapa de correção.
