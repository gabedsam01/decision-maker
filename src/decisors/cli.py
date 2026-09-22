"""Small stdlib CLI; Pi owns the persistent interactive lifecycle."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from typing import Any

from .bridge import serve
from .config import ConfigStore
from .engine import DecisionEngine
from .errors import DecisorsError
from .integrate import install_pi_assets, install_pi_extension


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="decisors", description="Typed System One decisions for AI agents")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Prepare the selected provider and model")
    sub.add_parser("start", help="Start the background bridge and warm the model (non-blocking)")
    sub.add_parser("stop", help="Stop the engine and unload local weights")
    sub.add_parser("status", help="Show live daemon status (or config-only when the daemon is off)")
    sub.add_parser("test", help="Run one explicit sample decision")
    sub.add_parser("doctor", help="Check runtime, config, model package, and credentials")
    bridge = sub.add_parser("bridge", help=argparse.SUPPRESS)
    bridge.add_argument("--daemon", action="store_true", help=argparse.SUPPRESS)
    kill = sub.add_parser("kill", help="Shut down the background bridge daemon")
    kill.add_argument("--force", action="store_true", help="SIGKILL via pidfile when graceful fails")

    config = sub.add_parser("config", help="Show or change provider/model/device settings")
    config.add_argument("--provider", choices=["laya", "typesafe", "openrouter"])
    config.add_argument("--model")
    config.add_argument("--device", choices=["auto", "cpu", "cuda", "mps"])
    config.add_argument("--confidence-threshold", type=float)
    config.add_argument("--max-loaded", type=int)
    config.add_argument("--timeout-seconds", type=float)
    config.add_argument("--max-requests-per-session", type=int)

    integrate = sub.add_parser("integrate", help="Install an explicit agent integration")
    integrate.add_argument("target", choices=["pi"])

    return parser


def _config_changes(args: argparse.Namespace) -> dict[str, Any]:
    mapping = {
        "provider": args.provider,
        "model": args.model,
        "device": args.device,
        "confidence_threshold": args.confidence_threshold,
        "max_loaded": args.max_loaded,
        "timeout_seconds": args.timeout_seconds,
        "max_requests_per_session": args.max_requests_per_session,
    }
    return {key: value for key, value in mapping.items() if value is not None}


def run(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "bridge":
        if args.daemon:
            from .bridge import serve_socket

            return serve_socket()
        return serve()
    if args.command == "integrate":
        path = install_pi_extension()
        assets = install_pi_assets()
        _print(
            {
                "installed": True,
                "target": "pi",
                "path": str(path),
                "skill": str(assets["skill"]),
                "prompt": str(assets["prompt"]),
                "next": "Run /reload in Pi, then /decision init.",
            }
        )
        return 0

    store = ConfigStore()
    engine = DecisionEngine(store)
    if args.command == "config":
        changes = _config_changes(args)
        if changes:
            _print(engine.configure(**changes))
        else:
            _print({"config_path": str(store.path), "config": asdict(store.load())})
        return 0
    if args.command == "init":
        _print(engine.initialize())
    elif args.command == "start":
        _print(_daemon_start())
    elif args.command == "stop":
        from .bridge import call_daemon

        live = call_daemon("stop")
        _print(live["result"] if live and live.get("ok") else engine.stop())
    elif args.command == "kill":
        _print(_daemon_kill(force=args.force))
    elif args.command == "status":
        _print(_daemon_status(engine))
    elif args.command == "test":
        _print(engine.test())
    elif args.command == "doctor":
        _print(engine.doctor())
    return 0


def _ensure_daemon() -> dict[str, Any] | None:
    from .bridge import call_daemon, spawn_daemon, wait_for_socket

    reply = call_daemon("status")
    if reply is None:
        spawn_daemon()
        if not wait_for_socket():
            return None
        reply = call_daemon("status")
    if reply and reply.get("ok"):
        result: dict[str, Any] = reply["result"]
        return result
    return None


def _daemon_start() -> dict[str, Any]:
    from .bridge import call_daemon

    if _ensure_daemon() is None:
        return {"ok": False, "error": "BridgeDaemonError", "message": "daemon did not start"}
    warm = call_daemon("warm")
    result: dict[str, Any] = warm["result"] if warm and warm.get("ok") else {}
    result["note"] = "Warm-up runs in the background; the model is available as soon as it finishes."
    return result


def _daemon_status(engine: DecisionEngine) -> dict[str, Any]:
    from .bridge import call_daemon

    live = call_daemon("status")
    if live and live.get("ok"):
        result: dict[str, Any] = live["result"]
        return result
    status = engine.status()
    status["note"] = (
        "Bridge daemon off: provider_status reflects configuration only. "
        "Run `decisors start` to warm the model."
    )
    return status


def _daemon_kill(force: bool) -> dict[str, Any]:
    from .bridge import call_daemon, force_kill_daemon

    reply = call_daemon("shutdown")
    if reply and reply.get("ok"):
        return {"shutdown": True, "forced": False}
    killed = force_kill_daemon() if force else False
    return {"shutdown": bool(killed), "forced": bool(killed)}


def main() -> None:
    try:
        raise SystemExit(run())
    except DecisorsError as exc:
        _print({"ok": False, "error": type(exc).__name__, "message": str(exc)})
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
