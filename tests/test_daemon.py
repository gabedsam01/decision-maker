"""Daemon lifecycle: socket round-trip, non-blocking warm-up, persisted intent."""

import threading
import time
from pathlib import Path
from typing import Any

import pytest

import decisors.engine as engine_module
from decisors.bridge import BridgeServer, call_daemon, serve_socket, wait_for_socket
from decisors.config import ConfigStore
from decisors.engine import DecisionEngine
from decisors.errors import NotStartedError


class FakeLaya:
    name = "laya"

    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self.stopped = False

    def prepare(self) -> dict[str, Any]:
        return {"provider": "laya", "model": "fake", "ready": True}

    def evaluate(self, request: Any) -> dict[str, Any]:
        qid = next(iter(request.questions))
        return {
            "provider": "laya",
            "model": "fake",
            "usage": {"input_tokens": 3, "output_tokens": 0},
            "answers": {qid: {"type": "noul", "noul": 0.9}},
        }

    def stop(self) -> None:
        self.stopped = True

    def status(self) -> dict[str, Any]:
        return {"provider": "laya", "ready": not self.stopped, "model": "fake"}


def test_socket_daemon_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine_module, "LayaProvider", FakeLaya)
    sock = tmp_path / "bridge.sock"
    engine = DecisionEngine(ConfigStore(tmp_path / "config.toml"))
    thread = threading.Thread(
        target=serve_socket,
        kwargs={"path": sock, "idle_timeout": 600.0, "bridge": BridgeServer(engine)},
        daemon=True,
    )
    thread.start()
    # Same readiness gate the production clients use (bind creates the socket
    # file before listen; a bare connect in that window gets ECONNREFUSED).
    assert wait_for_socket(timeout=5, path=sock)

    reply = call_daemon("ping", path=sock)
    assert reply["ok"] is True
    assert reply["result"]["protocol"] == 1

    warm = call_daemon("warm", path=sock)
    assert warm["ok"] is True
    for _ in range(200):
        status = call_daemon("status", path=sock)
        if status["result"]["active"]:
            break
        time.sleep(0.01)
    assert call_daemon("status", path=sock)["result"]["active"] is True

    shutdown = call_daemon("shutdown", path=sock)
    assert shutdown["result"]["shutdown"] is True
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_start_async_is_non_blocking_and_persists_intent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = threading.Event()

    class SlowLaya(FakeLaya):
        def prepare(self) -> dict[str, Any]:
            gate.wait(5)
            return {"provider": "laya", "model": "fake", "ready": True}

    monkeypatch.setattr(engine_module, "LayaProvider", SlowLaya)
    engine = DecisionEngine(ConfigStore(tmp_path / "config.toml"))

    started = time.monotonic()
    status = engine.start_async()
    assert time.monotonic() - started < 0.5
    assert status["warming"] is True

    with pytest.raises(NotStartedError):
        engine.evaluate("x", {"q": {"type": "noul", "instructions": "ok?"}})

    gate.set()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not engine.status()["active"]:
        time.sleep(0.01)
    assert engine.status()["active"] is True
    assert engine.settings.active is True

    engine.stop()
    assert engine.settings.active is False
