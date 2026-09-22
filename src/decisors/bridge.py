"""Persistent JSONL bridge used by the Pi adapter."""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any, TextIO

from .engine import DecisionEngine
from .errors import DecisorsError

PROTOCOL_VERSION = 1


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


def main() -> None:
    try:
        raise SystemExit(serve())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception:
        traceback.print_exc(file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
