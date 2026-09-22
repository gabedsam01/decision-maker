#!/usr/bin/env node
// Installs the Pi adapter artifacts into ~/.pi/agent and checks the decisors binary.
// The Python core resolves credentials; this installer never reads or writes secrets.
import { spawnSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const base = join(homedir(), ".pi", "agent");

const assets = [
  ["src/decisors/integrations/pi-extension.js", join(base, "extensions", "decisors", "index.js")],
  [
    "src/decisors/integrations/skills/decisores-decisoes/SKILL.md",
    join(base, "skills", "decisores-decisoes", "SKILL.md"),
  ],
  ["src/decisors/integrations/prompts/juiz.md", join(base, "prompts", "juiz.md")],
];

for (const [source, target] of assets) {
  const from = join(here, source);
  if (!existsSync(from)) {
    console.log("missing in package:", source);
    continue;
  }
  mkdirSync(dirname(target), { recursive: true });
  copyFileSync(from, target);
  console.log("installed:", target);
}

// The Python binary is the engine; make sure it is reachable (warn-only on postinstall).
const probe = spawnSync("sh", ["-c", "command -v decisors"], { encoding: "utf-8" });
if (probe.status === 0) {
  console.log("decisors binary:", probe.stdout.trim());
} else {
  console.log("decisors binary not found in PATH. Install it with: uv tool install decisors");
}
