import assert from "node:assert/strict";
import { DecisionPanel, InitWizard, footerText, keyName, whereAction, whereNext } from "../src/decisors/integrations/pi-extension.js";

assert.equal(keyName("\u001b[A"), "up");
assert.equal(keyName("\u001b[1;1A"), "up");
assert.equal(keyName("\u001b[1;1B"), "down");
assert.equal(keyName("\u001b[57419u"), "up");
assert.equal(keyName("\u001b[105u"), "i");
assert.equal(keyName("\u001b[57419;1:3u"), "ignore");
assert.equal(keyName("q"), "q");

const snapshot = {
  active: false,
  ready: true,
  config: {
    provider: "laya",
    model: "auto",
    device: "auto",
    confidence_threshold: 0.6,
    max_requests_per_session: 20,
  },
  provider_status: {
    provider: "laya",
    configured_model: "auto",
    resolved_model: "multilingual",
    loaded: ["multilingual"],
    model: "multilingual",
  },
  catalog: {
    cached: { english: true, multilingual: true, "typed-decisions": false },
    warmup_model: "multilingual",
    credentials: { openrouter: true, typesafe: false },
  },
};

const footer = footerText(snapshot);
assert.match(footer, /laya/);
assert.match(footer, /auto→multilingual/);
assert.match(footer, /jev key unused/);
assert.match(footer, /off/);

const wide = new DecisionPanel(snapshot).render(80).join("\n");
assert.match(wide, /┌/);
assert.match(wide, /Laya local/);
assert.match(wide, /Não digite a chave aqui/);
assert.match(wide, /Sessão/);
assert.match(wide, /20/);
assert.ok(new DecisionPanel(snapshot).render(40).some((line) => line.includes("┌")));

const panel = new DecisionPanel(snapshot);
panel.invalidate();
assert.equal(panel.focused, false);
let seen;
panel.onAction = async (_action, params) => {
  seen = params;
  return { snapshot, note: "ok" };
};
panel.section = 4;
panel.handleInput("\u001b[1;1B");
await new Promise((resolve) => setTimeout(resolve, 0));
assert.deepEqual(seen, { max_requests_per_session: 19 });
panel.section = 0;
panel.cursor = 1;
panel.handleInput("\r");
await new Promise((resolve) => setTimeout(resolve, 0));
assert.deepEqual(seen, { provider: "typesafe", model: "auto" });
let probed = false;
let got;
const skipped = new InitWizard(null, (value) => { got = value; }, async () => { probed = true; });
skipped.handleInput("n");
assert.equal(probed, false);
assert.deepEqual(got, { skipped: true });
assert.match(skipped.render(70).join("\n"), /y mede/);

const declined = new InitWizard(null, (value) => { got = value; });
declined.phase = "results";
declined.report = { recommended: "cuda", lay: ["Placa: respondeu em 4.0 ms."] };
declined.handleInput("n");
assert.deepEqual(got, { accept: false });

const accepted = new InitWizard(null, (value) => { got = value; });
accepted.phase = "results";
accepted.report = { recommended: "cpu", lay: ["Processador: respondeu em 2.0 ms."] };
accepted.handleInput("y");
assert.deepEqual(got, { accept: true, device: "cpu" });
assert.equal(whereNext({ mode: "ask" }, undefined), "ask");
assert.equal(whereNext({ mode: "ask" }, false), "local_loop");
assert.equal(whereNext({ mode: "ask" }, true), "cloud");
assert.equal(whereNext({ mode: "local_loop" }, true), "local_loop");
assert.equal(whereAction({ mode: "ask", say: "perguntar" }, false, false), "ask");
assert.equal(whereAction({ mode: "ask" }, true, false), "local_loop");
console.log("panel ok");
