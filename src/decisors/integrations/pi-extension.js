import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { createConnection } from "node:net";
import { join } from "node:path";
import { createInterface } from "node:readline";

const COMMANDS = ["init", "start", "stop", "config", "status", "panel", "test", "doctor", "help"];

export function whereNext(plan, answer) {
  if (!plan) return "local_loop";
  if (plan.mode === "ask") {
    if (answer == null) return "ask";
    return answer ? "cloud" : "local_loop";
  }
  if (plan.mode === "local" || plan.mode === "local_loop" || plan.mode === "cloud") return plan.mode;
  return "local_loop";
}

export function whereAction(plan, hasConfirm, answer) {
  if (plan && plan.mode === "ask" && !hasConfirm) return "ask";
  return whereNext(plan, hasConfirm ? answer : undefined);
}

function decisionText(result) {
  const say = result && (result.say || result.choice) || "";
  const body = say ? say + "\n" + JSON.stringify(result) : JSON.stringify(result);
  return { content: [{ type: "text", text: body }], details: result };
}
const DEFAULT_TIMEOUT_MS = 30000;
const INIT_TIMEOUT_MS = 15 * 60 * 1000;
const SOCKET_PATH = process.env.XDG_RUNTIME_DIR
  ? join(process.env.XDG_RUNTIME_DIR, "decisors", "bridge.sock")
  : join("/tmp", "decisors-" + (process.getuid?.() ?? "0"), "bridge.sock");

function bridgeCommand() {
  // Credentials are resolved by the Python core (env + auth store); the adapter stays thin.
  const localBin = join(homedir(), ".local", "bin", "decisors");
  return existsSync(localBin) ? localBin : "decisors";
}

function spawnDaemon() {
  const child = spawn(bridgeCommand(), ["bridge", "--daemon"], { detached: true, stdio: "ignore" });
  child.unref();
}

class BridgeClient {
  constructor() {
    this.socket = undefined;
    this.lines = undefined;
    this.pending = new Map();
    this.nextId = 1;
    this.connecting = undefined;
  }

  connect() {
    if (this.socket) return Promise.resolve();
    if (this.connecting) return this.connecting;
    this.connecting = new Promise((resolve, reject) => {
      const attempt = (left, spawned) => {
        const socket = createConnection(SOCKET_PATH);
        socket.once("connect", () => {
          this.socket = socket;
          this.lines = createInterface({ input: socket });
          this.lines.on("line", (line) => {
            let message;
            try {
              message = JSON.parse(line);
            } catch {
              this.failAll(new Error("Decisors bridge returned malformed JSON."));
              return;
            }
            const pending = this.pending.get(String(message.id));
            if (!pending) return;
            this.pending.delete(String(message.id));
            clearTimeout(pending.timer);
            pending.signal?.removeEventListener("abort", pending.onAbort);
            if (message.ok) pending.resolve(message.result);
            else pending.reject(new Error(message.error?.message || "Decisors bridge request failed."));
          });
          socket.on("close", () => {
            this.socket = undefined;
            this.failAll(new Error("Decisors bridge connection closed."));
          });
          this.connecting = undefined;
          resolve();
        });
        socket.once("error", () => {
          socket.destroy();
          if (left <= 0) {
            this.connecting = undefined;
            reject(new Error("Decisors bridge unavailable. Run `decisors start` and retry."));
            return;
          }
          if (!spawned) spawnDaemon();
          setTimeout(() => attempt(left - 1, true), 250);
        });
      };
      attempt(12, false);
    });
    return this.connecting;
  }

  failAll(error) {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer);
      pending.signal?.removeEventListener("abort", pending.onAbort);
      pending.reject(error);
    }
    this.pending.clear();
  }

  request(method, params = {}, options = {}) {
    const { signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options;
    return this.connect().then(() => {
      const id = String(this.nextId++);
      return new Promise((resolve, reject) => {
        const onAbort = () => {
          this.pending.delete(id);
          reject(new Error("Decisors request aborted."));
        };
        if (signal?.aborted) {
          onAbort();
          return;
        }
        signal?.addEventListener("abort", onAbort, { once: true });

        const timer = setTimeout(() => {
          this.pending.delete(id);
          reject(new Error("Decisors request timed out after " + timeoutMs + " ms."));
        }, timeoutMs);

        this.pending.set(id, { resolve, reject, timer, signal, onAbort });
        try {
          this.socket.write(JSON.stringify({ id, method, params }) + "\n");
        } catch (error) {
          clearTimeout(timer);
          signal?.removeEventListener("abort", onAbort);
          this.pending.delete(id);
          reject(error);
        }
      });
    });
  }

  detach() {
    // Keep-active: the daemon survives the session and self-stops on idle.
    this.socket?.destroy();
    this.socket = undefined;
  }
}

function formatBytes(bytes) {
  if (bytes == null || !Number.isFinite(bytes)) return "size unknown";
  if (bytes === 0) return "already cached";
  const units = ["B", "KiB", "MiB", "GiB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return value.toFixed(index >= 2 ? 1 : 0) + " " + units[index];
}

function formatDuration(seconds) {
  if (seconds == null || !Number.isFinite(seconds)) return "ETA unavailable";
  if (seconds <= 1) return "<1s";
  if (seconds < 60) return Math.round(seconds) + "s";
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return minutes + "m " + remainder + "s";
}

const KITTY_ARROWS = { 57419: "up", 57420: "down", 57418: "right", 57417: "left" };
const PROVIDERS = ["laya", "typesafe", "openrouter"];
const DEVICES = ["auto", "cpu", "cuda", "mps"];

export function keyName(data) {
  if (!data) return "";
  if (/:3[ABCD~u]/.test(data)) return "ignore";
  if (data === "\u001b" || data === "\u001b\u001b") return "escape";
  if (data === "\r" || data === "\n" || data === "\u001bOM" || data === "\u001b[13u") return "enter";
  if (data === "\t" || data === "\u001b[9u") return "tab";
  if (data === "\u001b[Z") return "shift-tab";
  if (data === "\u001b[A" || data === "\u001bOA") return "up";
  if (data === "\u001b[B" || data === "\u001bOB") return "down";
  if (data === "\u001b[C" || data === "\u001bOC") return "right";
  if (data === "\u001b[D" || data === "\u001bOD") return "left";
  const modArrow = /^\u001b\[(?:\d+;)?\d*(?::\d+)?([ABCD])$/.exec(data);
  if (modArrow) return { A: "up", B: "down", C: "right", D: "left" }[modArrow[1]];
  const kitty = /^\u001b\[(\d+)(?::\d*)?(?::\d+)?(?:;(\d+))?(?::(\d+))?u$/.exec(data);
  if (kitty) {
    const event = kitty[3];
    const code = Number(kitty[1]);
    if (event === "3") return "ignore";
    if (event === "2" && !KITTY_ARROWS[code]) return "ignore";
    const mod = kitty[2] ? Number(kitty[2]) - 1 : 0;
    if (mod & ~192) return "ignore";
    if (code === 27) return "escape";
    if (code === 13 || code === 9) return code === 9 ? "tab" : "enter";
    if (KITTY_ARROWS[code]) return KITTY_ARROWS[code];
    if (code >= 32 && code <= 126) return String.fromCharCode(code).toLowerCase();
    return "ignore";
  }
  if (data.length === 1) return data.toLowerCase();
  return "";
}

function cycle(list, current, dir) {
  const index = list.indexOf(current);
  const start = index < 0 ? 0 : index;
  return list[(start + dir + list.length) % list.length];
}

function modelChoices(provider, current) {
  const base =
    provider === "typesafe" ? ["auto", "jev-latest"] :
    provider === "openrouter" ? ["auto", "typesafe/jev-1.13"] :
    ["auto", "english", "multilingual", "typed-decisions"];
  return current && !base.includes(current) ? [current, ...base] : base;
}

function yn(value) {
  return value ? "sim" : "não";
}

export function footerText(status) {
  const cfg = status?.config || {};
  const ps = status?.provider_status || {};
  const catalog = status?.catalog || {};
  const provider = ps.provider || cfg.provider || status?.provider || "laya";
  const configured = ps.configured_model || cfg.model || "auto";
  const resolved = ps.resolved_model || catalog.warmup_model;
  const loaded = Array.isArray(ps.loaded) && ps.loaded.length ? ps.loaded.join("+") : "";
  const model = configured === "auto" && resolved ? configured + "→" + resolved : (ps.model || configured);
  const active = status?.active ? "on" : status?.warming ? "warming" : "off";
  const cred = catalog.credentials || {};
  const jev = provider === "laya" && cred.openrouter ? " · jev key unused" : "";
  const ram = loaded ? " · ram " + loaded : "";
  return "decision: " + provider + " · " + model + ram + " · " + active + jev;
}

function compact(value) {
  if (!value || typeof value !== "object") return String(value);
  const status = value.provider_status || value;
  const provider = status.provider || value.provider || "unknown";
  const loaded = Array.isArray(status.loaded) && status.loaded.length ? status.loaded.join("+") : null;
  const model = loaded || status.resolved_model || status.model || value.model || "auto";
  const active = value.active;
  const ready = value.ready ?? status.ready;
  return [
    "provider=" + provider,
    "model=" + model,
    ready == null ? null : "ready=" + (ready ? "yes" : "no"),
    active == null ? null : "active=" + (active ? "yes" : "no"),
  ].filter(Boolean).join(" · ");
}

function paint(theme, role, text) {
  try {
    if (theme && typeof theme.fg === "function") return theme.fg(role, text);
  } catch {
    return text;
  }
  return text;
}

const SECTIONS = ["provider", "model", "device", "threshold", "requests"];
const PROVIDER_OPTIONS = [
  { value: "laya", label: "Laya local", hint: "grátis" },
  { value: "typesafe", label: "Jev TypeSafe", hint: "chave no perfil" },
  { value: "openrouter", label: "Jev OpenRouter", hint: "chave no perfil" },
];

function stripAnsi(text) {
  return String(text).replace(/\x1b\[[0-9;]*m/g, "");
}

function padTo(text, width) {
  const gap = width - stripAnsi(text).length;
  return gap > 0 ? text + " ".repeat(gap) : text;
}

function fit(text, width) {
  const plain = stripAnsi(text);
  if (plain.length <= width) return text;
  return plain.slice(0, Math.max(0, width - 1)) + "…";
}

function paintBg(theme, text, width, selected) {
  const padded = padTo(fit(text, width), width);
  if (!theme || typeof theme.bg !== "function") return padded;
  try {
    return theme.bg(selected ? "selectedBg" : "customMessageBg", padded);
  } catch {
    return padded;
  }
}

export class InitWizard {
  constructor(theme, done, onProbe) {
    this.theme = theme;
    this.done = done || (() => {});
    this.onProbe = onProbe || (async () => ({}));
    this.tui = undefined;
    this.phase = "ask";
    this.busy = false;
    this.report = null;
    this.error = "";
  }

  invalidate() {
    this.tui?.requestRender?.();
  }

  render(width) {
    const inner = Math.max(18, width - 2);
    const accent = (text) => paint(this.theme, "accent", text);
    const lines = [];
    const push = (text) => {
      lines.push(paintBg(this.theme, "│" + padTo(fit(text, inner), inner) + "│", width, false));
    };
    lines.push(paintBg(this.theme, "┌" + "─".repeat(inner) + "┐", width, false));
    push(" " + accent("decisors") + "  init · aparelho");
    if (this.phase === "ask") {
      push(" Quer medir qual aparelho responde mais rápido?");
      push(" Não baixa o modelo. Só uma conta pequena.");
      push(" y mede   n ou enter pula");
    } else if (this.phase === "wait") {
      push(" Medindo. Não troca nada sozinho.");
    } else {
      const lay = this.report?.lay || [];
      if (this.error) push(" " + this.error);
      for (const line of lay) push(" " + line);
      if (!lay.length && !this.error) push(" Sem número. n continua.");
      push(" y aceita a sugestão   n deixa como está");
    }
    lines.push(paintBg(this.theme, "└" + "─".repeat(inner) + "┘", width, false));
    return lines;
  }

  handleInput(data) {
    if (this.busy) return;
    const key = keyName(data);
    if (!key || key === "ignore") return;
    if (this.phase === "ask") {
      if (key === "y") return this.start();
      if (key === "n" || key === "enter" || key === "escape" || key === "q") this.done({ skipped: true });
      return;
    }
    if (this.phase !== "results") return;
    const device = this.report?.recommended;
    if (key === "y" && (device === "cpu" || device === "cuda" || device === "mps")) {
      this.done({ accept: true, device });
      return;
    }
    if (key === "n" || key === "enter" || key === "escape" || key === "q") this.done({ accept: false });
  }

  start() {
    this.busy = true;
    this.phase = "wait";
    this.invalidate();
    Promise.resolve()
      .then(() => this.onProbe())
      .then((report) => {
        this.report = report || {};
        this.phase = "results";
      })
      .catch((error) => {
        this.error = error instanceof Error ? error.message : String(error);
        this.phase = "results";
      })
      .finally(() => {
        this.busy = false;
        this.invalidate();
      });
  }
}

export class DecisionPanel {
  constructor(snapshot, theme, done, onAction) {
    this.snapshot = snapshot || {};
    this.theme = theme;
    this.done = done || (() => {});
    this.onAction = onAction || (async () => {});
    this.tui = undefined;
    this.focused = false;
    this.section = 0;
    this.cursor = 0;
    this.busy = false;
    this.note = "";
    this.rev = 0;
    this.syncCursor();
  }

  cfg() {
    return this.snapshot.config || {};
  }

  sectionId() {
    return SECTIONS[this.section] || "provider";
  }

  choices(id) {
    const provider = this.cfg().provider || "laya";
    if (id === "provider") return PROVIDER_OPTIONS;
    if (id === "device") {
      return DEVICES.map((value) => ({ value, label: value, hint: "" }));
    }
    if (id === "model") {
      return modelChoices(provider, this.cfg().model).map((value) => ({
        value,
        label: value,
        hint: value === "auto" ? "router por idioma" : value === "typed-decisions" ? "opt-in" : "",
      }));
    }
    return [];
  }

  isSelect(id) {
    return id === "provider" || id === "model" || id === "device";
  }

  syncCursor() {
    const id = this.sectionId();
    if (!this.isSelect(id)) return;
    const current = this.cfg()[id] || (id === "provider" ? "laya" : "auto");
    const index = this.choices(id).findIndex((item) => item.value === current);
    this.cursor = index < 0 ? 0 : index;
  }

  nextStep(id, dir) {
    const cfg = this.cfg();
    if (id === "threshold") {
      const next = Math.min(1, Math.max(0, Number(cfg.confidence_threshold ?? 0.6) + dir * 0.05));
      return Math.round(next * 100) / 100;
    }
    return Math.min(500, Math.max(1, Number(cfg.max_requests_per_session ?? 20) + dir));
  }

  configPatch(id, value) {
    if (id === "provider") return { provider: value, model: "auto" };
    if (id === "model") return { model: value };
    if (id === "device") return { device: value };
    if (id === "threshold") return { confidence_threshold: value };
    return { max_requests_per_session: value };
  }

  applyLocal(id, value) {
    const config = { ...this.cfg() };
    if (id === "provider") {
      config.provider = value;
      config.model = "auto";
    } else if (id === "model") config.model = value;
    else if (id === "device") config.device = value;
    else if (id === "threshold") config.confidence_threshold = value;
    else config.max_requests_per_session = value;
    this.snapshot = { ...this.snapshot, config };
  }

  invalidate() {}

  render(width) {
    const inner = Math.max(18, width - 2);
    const cfg = this.cfg();
    const catalog = this.snapshot.catalog || {};
    const cred = catalog.credentials || {};
    const cached = catalog.cached || {};
    const active = this.sectionId();
    const accent = (text) => paint(this.theme, "accent", text);
    const warn = (text) => paint(this.theme, "warning", text);
    const lines = [];
    const push = (text, selected = false) => {
      const body = padTo(fit(text, inner), inner);
      lines.push(paintBg(this.theme, "│" + body + "│", width, selected));
    };
    lines.push(paintBg(this.theme, "┌" + "─".repeat(inner) + "┐", width, false));
    push(" " + accent("decisors") + "  " + footerText(this.snapshot));
    push(" cache en " + yn(cached.english) + " · ml " + yn(cached.multilingual) + " · typed " + yn(cached["typed-decisions"]));
    const keyLine = cred.openrouter
      ? " OpenRouter no perfil: sim. Jev não está ativo. Não digite a chave aqui."
      : " Chave no perfil, não neste card. OpenRouter ausente · TypeSafe " + yn(cred.typesafe);
    push(warn(keyLine));
    push("");

    for (const id of SECTIONS) {
      const here = id === active;
      if (this.isSelect(id)) {
        push((here ? "▸ " : "  ") + (id === "provider" ? "Provedor" : id === "model" ? "Modelo" : "Device"), here && false);
        const options = this.choices(id);
        options.forEach((item, index) => {
          const saved = (cfg[id] || (id === "provider" ? "laya" : "auto")) === item.value;
          const marked = here && index === this.cursor;
          const mark = saved ? "●" : "○";
          push("  " + mark + " " + item.label + (item.hint ? "  " + item.hint : ""), marked);
        });
      } else if (id === "threshold") {
        const value = Number(cfg.confidence_threshold ?? 0.6).toFixed(2);
        push((here ? "▸ " : "  ") + "Threshold  " + value + "   ↑↓ 0.05   não filtra", here);
      } else {
        const value = String(cfg.max_requests_per_session ?? 20);
        push((here ? "▸ " : "  ") + "Sessão     " + value + "   ↑↓ 1   desce até 1   só nuvem", here);
      }
    }

    push("");
    push(" ↑↓ ajusta   tab troca   enter aplica o select");
    push(" i init   s start   x stop   t test   q fecha");
    if (this.note) push(" " + this.note, false);
    lines.push(paintBg(this.theme, "└" + "─".repeat(inner) + "┘", width, false));
    return lines;
  }

  handleInput(data) {
    if (this.busy) return;
    const key = keyName(data);
    if (!key || key === "ignore") return;
    if (key === "escape" || key === "q") {
      this.done(this.snapshot);
      return;
    }
    if (key === "i") return this.run("init", {}, "init · carregando checkpoint", true);
    if (key === "s") return this.run("start", {}, "start", true);
    if (key === "x") return this.run("stop", {}, "stop", true);
    if (key === "t") return this.run("test", {}, "test", true);
    if (key === "tab" || key === "j") {
      this.section = (this.section + 1) % SECTIONS.length;
      this.syncCursor();
      return;
    }
    if (key === "shift-tab" || key === "k") {
      this.section = (this.section + SECTIONS.length - 1) % SECTIONS.length;
      this.syncCursor();
      return;
    }
    const id = this.sectionId();
    if (this.isSelect(id)) {
      const options = this.choices(id);
      if (key === "up" || key === "left" || key === "h") {
        this.cursor = (this.cursor + options.length - 1) % options.length;
        return;
      }
      if (key === "down" || key === "right" || key === "l") {
        this.cursor = (this.cursor + 1) % options.length;
        return;
      }
      if (key === "enter") {
        const value = options[this.cursor]?.value;
        if (value == null) return;
        this.applyLocal(id, value);
        this.run("config", this.configPatch(id, value), "aplicado " + id + "=" + value, false);
      }
      return;
    }
    if (key === "up" || key === "right" || key === "l" || key === "+") {
      this.step(id, 1);
      return;
    }
    if (key === "down" || key === "left" || key === "h" || key === "-") this.step(id, -1);
  }

  step(id, dir) {
    const value = this.nextStep(id, dir);
    this.applyLocal(id, value);
    this.run("config", this.configPatch(id, value), id + "=" + value, false);
  }

  run(action, params, label, lock) {
    const rev = ++this.rev;
    if (lock) this.busy = true;
    this.note = label + (lock ? "…" : "");
    this.tui?.requestRender?.();
    void this.onAction(action, params, label).then((next) => {
      if (rev !== this.rev) return;
      if (next && typeof next === "object" && next.snapshot) this.snapshot = next.snapshot;
      if (next?.note) this.note = next.note;
      this.syncCursor();
    }).catch((error) => {
      if (rev !== this.rev) return;
      this.note = error instanceof Error ? error.message : String(error);
    }).finally(() => {
      if (lock && rev === this.rev) this.busy = false;
      this.tui?.requestRender?.();
    });
  }
}

function parseConfig(tokens) {
  if (tokens.length === 0) return null;
  let key;
  let value;
  if (tokens.length === 1 && tokens[0].includes("=")) {
    [key, value] = tokens[0].split("=", 2);
  } else {
    [key, value] = tokens;
  }
  if (!key || value == null) throw new Error("Usage: /decision config <field> <value>");
  const aliases = {
    threshold: "confidence_threshold",
    timeout: "timeout_seconds",
    requests: "max_requests_per_session",
  };
  key = aliases[key] || key;
  const numeric = new Set([
    "confidence_threshold",
    "max_loaded",
    "timeout_seconds",
    "max_requests_per_session",
  ]);
  return { [key]: numeric.has(key) ? Number(value) : value };
}

export default function decisorsExtension(pi) {
  const bridge = new BridgeClient();
  let cloudConsent = false;

  async function ensureCloudConsent(ctx) {
    const status = await bridge.request("status", {}, { timeoutMs: 5000 });
    const provider = status.config?.provider || "laya";
    if (provider === "laya") return true;
    if (cloudConsent) return true;
    if (!ctx.hasUI) {
      ctx.ui.notify(
        "Cloud decision providers require explicit interactive consent for this Pi session.",
        "warning",
      );
      return false;
    }
    const destination = provider === "typesafe" ? "TypeSafe" : "OpenRouter";
    const confirmed = await ctx.ui.confirm(
      "Enable cloud decisions for this session?",
      "State and questions will be sent to " + destination +
        " and may incur charges. Do not include secrets or sensitive data unless explicitly intended. " +
        "Confidence is a model judgment, not authorization.",
    );
    cloudConsent = Boolean(confirmed);
    return cloudConsent;
  }

  pi.registerTool({
    name: "decision_evaluate",
    label: "Decision",
    description:
      "Fast typed System One judgment using the operator-selected Decisors provider. " +
      "Use only for narrow semantic classification/routing/scoring/yes-no decisions. " +
      "The local default is Laya; cloud providers are explicit opt-in. " +
      "Confidence is distribution concentration, not authorization.",
    promptSnippet: "Typed Choice/Score/Noul decisions through Decisors",
    promptGuidelines: [
      "Use decision_evaluate for narrow semantic judgments where probabilities or repeated routing are useful; do not use it for coding, free-text generation, exact lookups, arithmetic, or multi-step reasoning.",
      "Do not call decision_evaluate merely to re-decide something already deterministic in the current context.",
      "Batch independent questions over the same state into one call, keep one judgment per question, and include an other/unclear option when no choice may fit.",
      "Treat low confidence as uncertainty; never use confidence alone to authorize destructive actions.",
    ],
    parameters: {
      type: "object",
      properties: {
        state: {},
        questions: {
          type: "object",
          description: "questionId -> choice/score/noul definition",
          additionalProperties: true,
        },
      },
      required: ["state", "questions"],
      additionalProperties: false,
    },
    async execute(_toolCallId, params, signal) {
      const result = await bridge.request(
        "evaluate",
        { state: params.state, questions: params.questions },
        { signal, timeoutMs: DEFAULT_TIMEOUT_MS },
      );
      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        details: result,
      };
    },
  });

  function registerReferee(name, label, description, parameters, run) {
    pi.registerTool({
      name,
      label,
      description,
      promptSnippet: description,
      promptGuidelines: [
        "Confidence is not authorization. Do not paste the raw receipt back into the turn.",
        "Do not call a cloud provider unless decision_where asked and the user said yes.",
      ],
      parameters,
      async execute(_toolCallId, params, signal, _onUpdate, ctx) {
        return run(params || {}, signal, ctx);
      },
    });
  }

  registerReferee(
    "decision_command",
    "Comando",
    "Traduz a saída de um comando. exit=1 nem sempre é falha.",
    {
      type: "object",
      properties: {
        command: { type: "string" },
        exit_code: { type: "number" },
        stdout: { type: "string" },
        stderr: { type: "string" },
      },
      required: ["command", "exit_code"],
      additionalProperties: false,
    },
    async (params, signal) => decisionText(await bridge.request("referee", {
      tool: "command",
      command: params.command,
      exit_code: params.exit_code,
      stdout: params.stdout || "",
      stderr: params.stderr || "",
    }, { signal, timeoutMs: DEFAULT_TIMEOUT_MS })),
  );

  registerReferee(
    "decision_subagent",
    "Subagente",
    "Entrega só a resposta do subagente. Infra não pede retry.",
    {
      type: "object",
      properties: {
        status: { type: "string" },
        output: { type: "string" },
        error: { type: "string" },
      },
      required: ["status"],
      additionalProperties: false,
    },
    async (params, signal) => decisionText(await bridge.request("referee", {
      tool: "subagent",
      status: params.status,
      output: params.output || "",
      error: params.error || "",
    }, { signal, timeoutMs: DEFAULT_TIMEOUT_MS })),
  );

  registerReferee(
    "decision_skill",
    "Skill",
    "Escolhe no máximo 19 skills para o pedido. Não carrega o catálogo inteiro.",
    {
      type: "object",
      properties: {
        task: { type: "string" },
        catalog: { type: "array" },
      },
      required: ["task", "catalog"],
      additionalProperties: false,
    },
    async (params, signal) => decisionText(await bridge.request("referee", {
      tool: "skill",
      task: params.task,
      catalog: params.catalog,
    }, { signal, timeoutMs: DEFAULT_TIMEOUT_MS })),
  );

  async function localConclude(params, signal) {
    return bridge.request("referee", {
      tool: "conclude",
      options: params.options,
      instructions: params.instructions || "Qual opção segue?",
      state: params.state || "",
    }, { signal, timeoutMs: INIT_TIMEOUT_MS });
  }

  async function oneCloudChoice(provider, params, signal) {
    return bridge.request("referee", {
      tool: "cloud_once",
      provider,
      options: params.options,
      instructions: params.instructions || "Qual opção segue?",
      state: params.state || "",
    }, { signal, timeoutMs: INIT_TIMEOUT_MS });
  }

  registerReferee(
    "decision_where",
    "Onde rodar",
    "Mais de 20 opções: sem chave, loop local. Com chave, pergunta antes de usar a nuvem.",
    {
      type: "object",
      properties: {
        options: { type: "array" },
        instructions: { type: "string" },
        state: { type: "string" },
      },
      required: ["options"],
      additionalProperties: false,
    },
    async (params, signal, ctx) => {
      const plan = await bridge.request("referee", {
        tool: "where",
        options: params.options,
      }, { signal, timeoutMs: DEFAULT_TIMEOUT_MS });
      const canAsk = Boolean(ctx && ctx.hasUI && typeof ctx.ui?.confirm === "function");
      let answer;
      if (plan.mode === "ask" && canAsk) {
        answer = Boolean(await ctx.ui.confirm(
          "Usar a nuvem nesta chamada?",
          plan.say + " O estado vai para " + plan.provider +
            " e pode gerar custo. Não mande segredo. O número não autoriza nada.",
        ));
      }
      const next = whereAction(plan, canAsk, answer);
      if (next === "ask") return decisionText(plan);
      if (next === "cloud" && plan.provider) {
        return decisionText(await oneCloudChoice(plan.provider, params, signal));
      }
      return decisionText(await localConclude(params, signal));
    },
  );

  pi.registerCommand("decision", {
    description: "Decisors setup, provider config, status, test, and lifecycle",
    getArgumentCompletions(prefix) {
      const token = prefix.trim().split(/\s+/, 1)[0] || "";
      const items = COMMANDS
        .filter((command) => command.startsWith(token))
        .map((command) => ({ value: command, label: command }));
      return items.length ? items : null;
    },
    async handler(args, ctx) {
      const parts = (args || "").trim().split(/\s+/).filter(Boolean);
      const action = parts.shift() || "panel";
      if (!COMMANDS.includes(action)) {
        ctx.ui.notify("Usage: /decision " + COMMANDS.join(" | "), "warning");
        return;
      }
      if (action === "help") {
        ctx.ui.notify(
          "/decision abre o painel. init mede o aparelho e prepara; start liga.",
          "info",
        );
        return;
      }
      if (action === "panel" || action === "status" || (action === "config" && parts.length === 0)) {
        await openPanel(ctx);
        return;
      }
      try {
        if ((action === "start" || action === "test") && !(await ensureCloudConsent(ctx))) return;
        let params = {};
        if (action === "config") {
          params = parseConfig(parts);
          if (Object.hasOwn(params, "provider")) cloudConsent = false;
        }
        if (action === "init" && ctx.hasUI && typeof ctx.ui.custom === "function") {
          const choice = await openInitWizard(ctx);
          if (choice?.accept && (choice.device === "cpu" || choice.device === "cuda" || choice.device === "mps")) {
            await bridge.request("config", { device: choice.device }, { timeoutMs: DEFAULT_TIMEOUT_MS });
          }
        }
        const result = await withWorking(ctx, action, async () => {
          if (action === "init") {
            const plan = await bridge.request("plan", {}, { timeoutMs: DEFAULT_TIMEOUT_MS });
            const summary = plan.provider + " " + (plan.model || "auto") +
              (plan.provider === "laya" ? " · " + formatBytes(plan.download_bytes) : "");
            ctx.ui.setWorkingMessage?.("Decisors · init · " + summary);
            ctx.ui.setWidget?.("decisors-busy", ["Decisors · init · " + summary]);
            if (plan.planning_warning) ctx.ui.notify(plan.planning_warning, "warning");
          }
          return bridge.request(action, params, {
            timeoutMs: action === "init" || action === "start" || action === "test" ? INIT_TIMEOUT_MS : DEFAULT_TIMEOUT_MS,
          });
        });
        const status = result?.config ? result : await bridge.request("status", {}, { timeoutMs: 8000 });
        ctx.ui.setStatus?.("decisors", footerText(status));
        ctx.ui.notify("Decisors · " + action + " · " + compact(result), result?.active === false && action === "init" ? "warning" : "info");
        if (action === "init") {
          ctx.ui.notify("Init preparou o modelo. Ainda não está ativo. Rode /decision start.", "warning");
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        ctx.ui.notify("Decisors · " + action + " failed: " + message, "error");
      }
    },
  });

  function withWorking(ctx, action, fn) {
    const label = "Decisors · " + action;
    ctx.ui.setWorkingMessage?.(label);
    ctx.ui.setWidget?.("decisors-busy", [label]);
    return Promise.resolve()
      .then(fn)
      .finally(() => {
        ctx.ui.setWorkingMessage?.();
        ctx.ui.setWidget?.("decisors-busy", undefined);
      });
  }

  function openInitWizard(ctx) {
    return ctx.ui.custom((tui, theme, _keys, done) => {
      const wizard = new InitWizard(theme, done, () => bridge.request("probe", {}, { timeoutMs: INIT_TIMEOUT_MS }));
      wizard.tui = tui;
      return wizard;
    }, {
      overlay: true,
      overlayOptions: { width: "70%", minWidth: 60, maxHeight: "80%", anchor: "center" },
    });
  }

  async function openPanel(ctx) {
    let snapshot;
    try {
      snapshot = await bridge.request("status", {}, { timeoutMs: 8000 });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      ctx.ui.notify("Decisors · painel indisponível: " + message, "error");
      ctx.ui.setStatus?.("decisors", "decision: unavailable");
      return;
    }
    ctx.ui.setStatus?.("decisors", footerText(snapshot));
    if (!ctx.hasUI || typeof ctx.ui.custom !== "function") {
      ctx.ui.notify(footerText(snapshot) + " · " + compact(snapshot), "info");
      return;
    }
    await ctx.ui.custom((tui, theme, _keys, done) => {
      const panel = new DecisionPanel(snapshot, theme, done, async (action, params, label) => {
        if ((action === "start" || action === "test") && !(await ensureCloudConsent(ctx))) {
          return { snapshot, note: "nuvem cancelada" };
        }
        if (action === "config" && Object.hasOwn(params, "provider")) cloudConsent = false;
        const result = await withWorking(ctx, label || action, () => bridge.request(
          action,
          params || {},
          { timeoutMs: action === "init" || action === "start" || action === "test" ? INIT_TIMEOUT_MS : DEFAULT_TIMEOUT_MS },
        ));
        snapshot = result?.config ? result : await bridge.request("status", {}, { timeoutMs: 8000 });
        ctx.ui.setStatus?.("decisors", footerText(snapshot));
        const note = action === "init" && snapshot.active === false
          ? "init ok · ainda inativo · [s] liga"
          : compact(result);
        return { snapshot, note };
      });
      panel.tui = tui;
      return panel;
    }, {
      overlay: true,
      overlayOptions: { width: "70%", minWidth: 60, maxHeight: "80%", anchor: "center" },
    });
  }

  pi.on("session_start", async (_event, ctx) => {
    try {
      let status = await bridge.request("status", {}, { timeoutMs: 5000 });
      if (status.active) {
        // keep-active: the daemon survived with the model hot; nothing to do.
      } else if (!status.warming && status.config?.active) {
        // previous session was active: auto-restart via non-blocking warm-up.
        status = await bridge.request("warm", {}, { timeoutMs: 5000 });
      }
      ctx.ui.setStatus?.("decisors", footerText(status));
    } catch {
      ctx.ui.setStatus?.("decisors", "decision: unavailable");
    }
  });

  pi.on("session_shutdown", async () => {
    cloudConsent = false;
    bridge.detach(); // keep-active: daemon self-stops on idle; `decisors kill` forces it down.
  });
}
