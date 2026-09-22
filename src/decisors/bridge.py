"""Persistent JSONL bridge used by the Pi adapter.

Two transports, one protocol: stdio (child of a client) and a local UNIX socket
(daemon shared across sessions; singleton by bind; self-stops on idle so nothing
runs 24h; first Ctrl+C stops gracefully, the second is a forced kill).
"""

from __future__ import annotations

import json
import os
import signal
import socket
import socketserver
import sys
import threading
import time
import traceback
from contextlib import suppress
from pathlib import Path
from typing import Any, TextIO, cast

from .engine import DecisionEngine
from .errors import DecisorsError

PROTOCOL_VERSION = 1
DEFAULT_IDLE_TIMEOUT = 900.0


class BridgeServer:
    def __init__(self, engine: DecisionEngine | None = None) -> None:
        self.engine = engine or DecisionEngine()
        self.shutdown_requested = False

    def dispatch(self, method: str, params: dict[str, Any] | None = None) -> Any:
        params = params or {}
        if method == "ping":
            return {"protocol": PROTOCOL_VERSION, "ok": True}
        if method == "status":
            return self.engine.status()
        if method == "plan":
            return self.engine.plan()
        if method == "probe":
            return self.engine.probe()
        if method == "referee":
            return self.engine.referee(str(params.get("tool") or ""), params)
        if method == "init":
            return self.engine.initialize()
        if method == "start":
            return self.engine.start()
        if method == "warm":
            return self.engine.start_async()
        if method == "stop":
            return self.engine.stop()
        if method == "test":
            return self.engine.test()
        if method == "doctor":
            return self.engine.doctor()
        if method == "config":
            return self.engine.configure(**params)
        if method == "evaluate":
            return self.engine.evaluate(params.get("state"), params.get("questions"))
        if method == "shutdown":
            self.engine.stop()
            self.shutdown_requested = True
            return {"shutdown": True}
        raise DecisorsError(f"Unknown bridge method {method!r}.")

    def handle(self, message: Any) -> dict[str, Any]:
        request_id: Any = None
        try:
            if not isinstance(message, dict):
                raise DecisorsError("Bridge request must be a JSON object.")
            request_id = message.get("id")
            method = message.get("method")
            params = message.get("params", {})
            if not isinstance(method, str) or not method:
                raise DecisorsError("Bridge request requires a method.")
            if not isinstance(params, dict):
                raise DecisorsError("Bridge params must be a JSON object.")
            result = self.dispatch(method, params)
            return {"id": request_id, "ok": True, "result": result}
        except DecisorsError as exc:
            return {
                "id": request_id,
                "ok": False,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
        except Exception as exc:
            return {
                "id": request_id,
                "ok": False,
                "error": {
                    "type": "InternalError",
                    "message": f"Unexpected bridge failure: {type(exc).__name__}.",
                },
            }


def serve(
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
) -> int:
    server = BridgeServer()
    for raw_line in input_stream:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = {
                "id": None,
                "ok": False,
                "error": {"type": "ProtocolError", "message": "Invalid JSONL request."},
            }
        else:
            response = server.handle(message)
        output_stream.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
        output_stream.flush()
        if server.shutdown_requested:
            break
    return 0


def socket_path() -> Path:
    """$XDG_RUNTIME_DIR/decisors/bridge.sock, else /tmp/decisors-$UID/bridge.sock."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime) / "decisors" / "bridge.sock"
    return Path(f"/tmp/decisors-{os.getuid()}") / "bridge.sock"


def pid_path(sock: Path | None = None) -> Path:
    return (sock or socket_path()).with_name("bridge.pid")


def call_daemon(
    method: str,
    params: dict[str, Any] | None = None,
    timeout: float = 5.0,
    path: Path | None = None,
) -> Any | None:
    """One JSONL round-trip against the daemon. None when it is not up."""
    sock_path = path or socket_path()
    if not sock_path.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(sock_path))
            payload = json.dumps({"id": "1", "method": method, "params": params or {}})
            client.sendall(payload.encode("utf-8") + b"\n")
            with client.makefile("r") as reader:
                line = reader.readline()
        return json.loads(line) if line else None
    except (OSError, json.JSONDecodeError):
        return None


def spawn_daemon() -> None:
    """Start the detached daemon; returns immediately."""
    import subprocess

    subprocess.Popen(
        [sys.executable, "-m", "decisors", "bridge", "--daemon"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def wait_for_socket(timeout: float = 5.0, path: Path | None = None) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if call_daemon("ping", timeout=0.5, path=path) is not None:
            return True
        time.sleep(0.05)
    return False


def force_kill_daemon() -> bool:
    """SIGKILL the daemon from its pidfile. Returns True when a pid was killed."""
    try:
        pid = int(pid_path().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return False
    with suppress(OSError):
        pid_path().unlink()
    with suppress(OSError):
        socket_path().unlink()
    return True


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        server = cast("_SocketServer", self.server)
        for raw_line in self.rfile:
            line = raw_line.decode("utf-8", "replace").strip()
            server.last_activity = time.monotonic()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                response = {
                    "id": None,
                    "ok": False,
                    "error": {"type": "ProtocolError", "message": "Invalid JSONL request."},
                }
            else:
                response = server.bridge.handle(message)
            payload = json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n"
            self.wfile.write(payload.encode("utf-8"))
            self.wfile.flush()
            if server.bridge.shutdown_requested:
                threading.Thread(target=server.shutdown, daemon=True).start()
                return


class _SocketServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def __init__(self, path: Path, bridge: BridgeServer, idle_timeout: float) -> None:
        self.bridge = bridge
        self.idle_timeout = idle_timeout
        self.last_activity = time.monotonic()
        super().__init__(str(path), _Handler)


def _idle_watchdog(server: _SocketServer) -> None:
    tick = min(30.0, max(1.0, server.idle_timeout))
    while True:
        time.sleep(tick)
        if time.monotonic() - server.last_activity > server.idle_timeout:
            server.bridge.engine.stop()
            os._exit(0)


def serve_socket(
    path: Path | None = None,
    idle_timeout: float | None = None,
    bridge: BridgeServer | None = None,
) -> int:
    """UNIX-socket daemon: singleton by bind, chmod 600, self-stops after idle."""
    sock_path = path or socket_path()
    if idle_timeout is None:
        idle_timeout = float(os.environ.get("DECISORS_IDLE_TIMEOUT", str(DEFAULT_IDLE_TIMEOUT)))
    sock_path.parent.mkdir(parents=True, exist_ok=True)
    with suppress(OSError):
        os.chmod(sock_path.parent, 0o700)
    if sock_path.exists():
        if call_daemon("ping", timeout=0.5, path=sock_path) is not None:
            return 0  # a live daemon already owns the socket; step aside
        with suppress(OSError):
            sock_path.unlink()
    try:
        daemon = _SocketServer(sock_path, bridge or BridgeServer(), idle_timeout)
    except OSError:
        return 1  # lost the singleton race
    with suppress(OSError):
        os.chmod(sock_path, 0o600)
    pid_path(sock_path).write_text(str(os.getpid()), encoding="utf-8")
    threading.Thread(target=_idle_watchdog, args=(daemon,), daemon=True).start()
    try:
        daemon.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        daemon.bridge.engine.stop()
        with suppress(OSError):
            daemon.server_close()
        with suppress(OSError):
            sock_path.unlink()
        with suppress(OSError):
            pid_path(sock_path).unlink()
    return 0


_interrupts = {"count": 0}


def _install_sigint() -> None:
    """First Ctrl+C: graceful stop. Second: forced exit (cancel everything)."""

    def handler(signum: int, frame: Any) -> None:
        _interrupts["count"] += 1
        if _interrupts["count"] >= 2:
            os._exit(130)
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, handler)


def main() -> None:
    _install_sigint()
    try:
        raise SystemExit(serve())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception:
        traceback.print_exc(file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
