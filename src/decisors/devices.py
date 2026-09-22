"""Pick a compute device by a small latency probe.

Does not download or load a Laya checkpoint, and does not write config.
"""

from __future__ import annotations

import statistics
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

REPS = 7
SIZE = 256
NOISE_RATIO = 0.05
NOISE_FLOOR_MS = 1.0

Bench = Callable[[str], dict[str, Any]]


def choose(measured: list[dict[str, Any]]) -> tuple[str, str]:
    """Return (device, why). Never picks a device that did not return a time."""
    ok = [
        row
        for row in measured
        if row.get("ok")
        and isinstance(row.get("median_ms"), (int, float))
        and row.get("id") in {"cpu", "cuda", "mps"}
    ]
    if not ok:
        return (
            "cpu",
            "Recomendo o processador. A medição não deu número. Não troco para uma placa que não respondeu.",
        )
    best = min(ok, key=lambda row: (float(row["median_ms"]), 0 if row["id"] == "cpu" else 1))
    cpu = next((row for row in ok if row["id"] == "cpu"), None)
    if best["id"] != "cpu" and cpu is not None:
        margin = float(cpu["median_ms"]) - float(best["median_ms"])
        noise = max(NOISE_FLOOR_MS, float(cpu["median_ms"]) * NOISE_RATIO)
        if margin <= noise:
            return (
                "cpu",
                "Recomendo o processador. A placa foi só um pouco mais rápida, dentro do ruído.",
            )
        device = "cuda" if best["id"] == "cuda" else "mps"
        return device, "Recomendo a placa. Foi mais rápida que o processador, fora da margem."
    if len(ok) == 1 and ok[0]["id"] == "cpu":
        return "cpu", "Recomendo o processador. Foi o único que respondeu."
    return "cpu", "Recomendo o processador. Foi o mais rápido."


def lay_lines(
    measured: list[dict[str, Any]],
    seen: list[str],
    recommended: str,
    why: str,
    mode: str,
) -> list[str]:
    lines: list[str] = []
    timed = {row["id"] for row in measured if row.get("ok")}
    for row in measured:
        label = row.get("label") or row.get("id")
        if row.get("ok"):
            lines.append(
                f"{label}: respondeu em {float(row['median_ms']):.1f} ms. "
                f"A mais lenta das {row.get('reps', REPS)} foi {float(row['p95_ms']):.1f} ms."
            )
        else:
            lines.append(f"{label}: a medição falhou ({row.get('error') or 'erro'}).")
    if seen and "cuda" not in timed and "mps" not in timed:
        lines.append("Placas no notebook, sem medição: " + "; ".join(seen) + ".")
        lines.append("O programa não consegue usá-las. Placa parada não ganha.")
    lines.append("Medi uma de cada vez." if mode == "sequential" else "Medi ao mesmo tempo.")
    lines.append(why)
    lines.append(f"Sugestão: {recommended}. y aceita, n deixa como está.")
    return lines


def probe_devices(bench: Bench | None = None, candidates: list[str] | None = None) -> dict[str, Any]:
    found = list(candidates) if candidates is not None else _candidates()
    mode = "parallel" if len(found) > 1 else "sequential"
    run = bench or _bench_matmul
    if mode == "parallel":
        with ThreadPoolExecutor(max_workers=len(found)) as pool:
            measured = list(pool.map(lambda device: _safe(device, run), found))
    else:
        measured = [_safe(device, run) for device in found]
    recommended, why = choose(measured)
    seen = pci_display_names()
    return {
        "mode": mode,
        "measured": measured,
        "seen": seen,
        "recommended": recommended,
        "why": why,
        "lay": lay_lines(measured, seen, recommended, why, mode),
    }


def _candidates() -> list[str]:
    found = ["cpu"]
    try:
        import torch
    except ImportError:
        return found
    if torch.cuda.is_available():
        found.append("cuda")
    mps = getattr(getattr(torch, "backends", None), "mps", None)
    if mps is not None and mps.is_available():
        found.append("mps")
    return found


def _label(device: str) -> str:
    if device == "cpu":
        return "Processador"
    if device == "mps":
        return "Placa Apple"
    if device == "cuda":
        try:
            import torch

            return "Placa " + torch.cuda.get_device_name(0)
        except Exception:
            return "Placa NVIDIA"
    return device


def _safe(device: str, bench: Bench) -> dict[str, Any]:
    try:
        timed = bench(device)
    except Exception as exc:
        return {"id": device, "label": _label(device), "ok": False, "error": type(exc).__name__}
    return {
        "id": device,
        "label": _label(device),
        "ok": True,
        "median_ms": timed["median_ms"],
        "p95_ms": timed["p95_ms"],
        "reps": timed.get("reps", REPS),
        "error": None,
    }


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _sync(device: str) -> None:
    import torch

    if device == "cuda":
        torch.cuda.synchronize()
    elif device == "mps":
        torch.mps.synchronize()


def _bench_matmul(device: str) -> dict[str, Any]:
    import torch

    dev = torch.device(device)
    left = torch.randn(SIZE, SIZE, device=dev)
    right = torch.randn(SIZE, SIZE, device=dev)
    torch.mm(left, right)
    _sync(device)
    samples: list[float] = []
    for _ in range(REPS):
        started = time.perf_counter()
        torch.mm(left, right)
        _sync(device)
        samples.append((time.perf_counter() - started) * 1000)
    del left, right
    return {
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(_percentile(samples, 0.95), 3),
        "reps": len(samples),
    }


def pci_display_names() -> list[str]:
    try:
        out = subprocess.check_output(["lspci", "-mm"], text=True, timeout=2, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return []
    names: list[str] = []
    for line in out.splitlines():
        if "VGA" not in line and "3D" not in line and "Display" not in line:
            continue
        parts = line.split('"')
        if len(parts) >= 8:
            names.append(f"{parts[5]} {parts[7]}".strip())
    return names
