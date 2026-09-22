"""Local CPU benchmark. No cloud calls. No typed-decisions download.

Times the installed `decisors bridge` from the outside: Laya evaluate does not
return elapsed_ms. Routing uses Router.route() after the bridge exits, so it
does not load a second checkpoint.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "benchmarks" / "results" / "local-cpu.json"
STATE = "Fui cobrado duas vezes no cartão. Quero o estorno hoje."
GOLD = "billing"
WIDTHS = (4, 10, 20, 40, 77)
LAT_N = 30


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("empty")
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * p / 100
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


def choice_criteria(n: int) -> dict[str, str]:
    base = {
        "billing": "cobranças, pagamentos e estornos",
        "technical": "falhas de software",
        "sales": "contratos e preços novos",
        "other": "nenhum destes",
    }
    if n < 4:
        raise ValueError("n >= 4")
    criteria = dict(list(base.items())[:n])
    while len(criteria) < n:
        key = f"opt_{len(criteria):02d}"
        criteria[key] = "não corresponde a este pedido"
    return criteria


def rss_kb(pid: int) -> int | None:
    try:
        for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except OSError:
        return None
    return None


def other_bridges(self_pid: int) -> list[dict[str, int]]:
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == self_pid:
            continue
        try:
            cmd = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if "decisors" in cmd and "bridge" in cmd:
            rss = rss_kb(pid)
            if rss is not None:
                found.append({"pid": pid, "rss_kb": rss})
    return found


class Bridge:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            ["decisors", "bridge"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.n = 0
        threading.Thread(target=self._drain, daemon=True).start()

    def _drain(self) -> None:
        assert self.proc.stderr is not None
        while self.proc.stderr.read(4096):
            pass

    def call(self, method: str, params: dict | None = None) -> dict:
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.n += 1
        payload = {"id": str(self.n), "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError(f"bridge closed during {method}")
        message = json.loads(line)
        if not message.get("ok"):
            raise RuntimeError(json.dumps(message.get("error"), ensure_ascii=False))
        result = message["result"]
        if not isinstance(result, dict):
            raise RuntimeError(f"{method} returned a non-object")
        return result

    def close(self) -> None:
        try:
            self.call("shutdown")
        except Exception:
            pass
        if self.proc.poll() is None:
            self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def timed(bridge: Bridge, method: str, params: dict | None = None) -> tuple[dict, float]:
    started = time.perf_counter()
    result = bridge.call(method, params)
    return result, (time.perf_counter() - started) * 1000


def noul_questions(count: int) -> dict:
    prompts = [
        "O cliente pede estorno?",
        "O cliente descreve cobrança duplicada?",
        "O cliente pede ajuda hoje?",
        "O cliente ameaça cancelar?",
        "O cliente fala de falha de software?",
        "O cliente pede um contrato novo?",
        "O cliente agradece e encerra?",
        "O cliente cita o cartão?",
    ]
    questions = {}
    for index in range(count):
        questions[f"q{index}"] = {
            "type": "noul",
            "instructions": prompts[index % len(prompts)] + f" ({index})",
        }
    return questions


def route_probe() -> dict:
    code = r"""
import json
import laya
router = laya.Router(auto_task_detection=False, standalone_repos=True, max_loaded=1)
cases = {
    "en": "I was charged twice",
    "pt": "Fui cobrado duas vezes",
    "hi": "मुझसे दो बार शुल्क लिया गया",
    "ko": "두 번 청구되었습니다",
}
out = {}
for key, text in cases.items():
    decision = router.route(text, {})
    out[key] = {"model": decision["model"], "reason": decision["reason"]}
print(json.dumps(out, ensure_ascii=False))
"""
    run = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if run.returncode != 0:
        return {"ok": False, "error": (run.stderr or run.stdout)[-500:]}
    return {"ok": True, "routes": json.loads(run.stdout.strip().splitlines()[-1])}


def self_check() -> None:
    assert pct([10, 20, 30], 50) == 20
    criteria = choice_criteria(10)
    assert criteria["billing"].startswith("cobranças")
    assert len(criteria) == 10
    assert "opt_09" in criteria
    assert len(choice_criteria(77)) == 77


def main() -> int:
    self_check()
    others = other_bridges(os.getpid())
    bridge = Bridge()
    report: dict = {
        "device_note": "uses ~/.config/decisors/config.toml; expected device=cpu, provider=laya",
        "other_bridges": others,
        "typed_decisions": "not loaded; not in cache; opt-in only",
        "cloud": "not called",
    }
    try:
        loaded, load_ms = timed(bridge, "init")
        report["load"] = {
            "wall_ms": round(load_ms, 1),
            "provider_elapsed_ms": loaded.get("elapsed_ms"),
            "model": loaded.get("model"),
            "warmup_ok": loaded.get("warmup_ok"),
        }
        started = bridge.call("start")
        report["rss_after_start_kb"] = rss_kb(bridge.proc.pid)
        report["loaded"] = (started.get("provider_status") or {}).get("loaded")

        # one throwaway so the 30x sample is warm
        timed(bridge, "evaluate", {"state": STATE, "questions": noul_questions(1)})
        samples = []
        for _ in range(LAT_N):
            _, ms = timed(bridge, "evaluate", {"state": STATE, "questions": noul_questions(1)})
            samples.append(ms)
        report["latency_1_noul_ms"] = {
            "n": LAT_N,
            "p50": round(pct(samples, 50), 1),
            "p95": round(pct(samples, 95), 1),
            "min": round(min(samples), 1),
            "max": round(max(samples), 1),
        }

        batch = {}
        for count in (1, 4, 8, 16):
            _, ms = timed(
                bridge,
                "evaluate",
                {"state": STATE, "questions": noul_questions(count)},
            )
            batch[str(count)] = {"wall_ms": round(ms, 1), "ms_per_question": round(ms / count, 1)}
        report["batch"] = batch

        first, _ = timed(bridge, "evaluate", {"state": STATE, "questions": noul_questions(1)})
        second, _ = timed(bridge, "evaluate", {"state": STATE, "questions": noul_questions(1)})
        report["deterministic"] = first.get("answers") == second.get("answers")

        sweep = []
        for width in WIDTHS:
            result, ms = timed(
                bridge,
                "evaluate",
                {
                    "state": STATE,
                    "questions": {
                        "team": {
                            "type": "choice",
                            "instructions": "Qual área deve tratar este pedido?",
                            "criteria": choice_criteria(width),
                        }
                    },
                },
            )
            answer = result["answers"]["team"]
            sweep.append(
                {
                    "options": width,
                    "choice": answer.get("choice"),
                    "hit": answer.get("choice") == GOLD,
                    "confidence": answer.get("confidence"),
                    "wall_ms": round(ms, 1),
                    "model": (result.get("routing") or {}).get("model"),
                }
            )
        report["option_sweep"] = sweep
        report["rss_after_eval_kb"] = rss_kb(bridge.proc.pid)
    finally:
        bridge.close()

    report["routing"] = route_probe()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        raise SystemExit(1) from exc
