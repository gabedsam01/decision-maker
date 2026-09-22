import io
import json
from typing import Any

from decisors.bridge import BridgeServer, serve


class FakeEngine:
    def status(self) -> dict[str, Any]:
        return {"active": False}

    def initialize(self) -> dict[str, Any]:
        return {"initialized": True}

    def start(self) -> dict[str, Any]:
        return {"active": True}

    def stop(self) -> dict[str, Any]:
        return {"active": False}

    def test(self) -> dict[str, Any]:
        return {"model": "fake"}

    def doctor(self) -> dict[str, Any]:
        return {"ok": True}

    def configure(self, **changes: Any) -> dict[str, Any]:
        return {"changes": changes}

    def evaluate(self, state: Any, questions: Any) -> dict[str, Any]:
        return {"state": state, "questions": questions}

    def probe(self) -> dict[str, Any]:
        return {"recommended": "cpu", "mode": "sequential"}


def test_referee_dispatch() -> None:
    class RefereeEngine(FakeEngine):
        def referee(self, tool: str, params: dict[str, Any]) -> dict[str, Any]:
            return {"tool": tool, "say": "ok"}

    server = BridgeServer(RefereeEngine())  # type: ignore[arg-type]
    response = server.handle({"id": "r", "method": "referee", "params": {"tool": "command"}})
    assert response["ok"] is True
    assert response["result"]["tool"] == "command"


def test_probe_dispatch() -> None:
    server = BridgeServer(FakeEngine())  # type: ignore[arg-type]
    response = server.handle({"id": "p", "method": "probe"})
    assert response["ok"] is True
    assert response["result"]["recommended"] == "cpu"


def test_dispatch_and_shutdown() -> None:
    server = BridgeServer(FakeEngine())  # type: ignore[arg-type]
    assert server.handle({"id": "1", "method": "ping"})["ok"] is True
    response = server.handle(
        {"id": "2", "method": "evaluate", "params": {"state": "x", "questions": {"q": {}}}}
    )
    assert response["result"]["state"] == "x"
    assert server.handle({"id": "3", "method": "shutdown"})["result"]["shutdown"] is True
    assert server.shutdown_requested is True


def test_jsonl_protocol() -> None:
    incoming = io.StringIO('{"id":"1","method":"ping","params":{}}\n')
    outgoing = io.StringIO()
    assert serve(incoming, outgoing) == 0
    response = json.loads(outgoing.getvalue())
    assert response["id"] == "1"
    assert response["result"]["protocol"] == 1
