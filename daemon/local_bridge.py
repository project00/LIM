import asyncio
import io
import json
from enum import Enum
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import httpx
from mss import mss
from PIL import Image
import sympy as sp

app = FastAPI(title="LIM AI Local Daemon Bridge")

REMOTE_SERVER_URL = "http://192.168.1.100:8000/api/v1/analyze"


class RouteTarget(Enum):
    LOCAL = "local"
    REMOTE = "remote"


class ModelRouter:
    """Smart Model Router per discriminare le richieste tra Edge e Cloud."""

    ROUTING_TABLE = {
        "sympy_math": RouteTarget.LOCAL,
        "fast_ocr": RouteTarget.LOCAL,
        "concept_map": RouteTarget.REMOTE,
        "load_3d_model": RouteTarget.REMOTE,
        "generate_quiz": RouteTarget.REMOTE,
    }

    @classmethod
    def get_target(cls, action: str) -> RouteTarget:
        return cls.ROUTING_TABLE.get(action, RouteTarget.REMOTE)


class LocalEngine:
    """Engine di esecuzione locale a latenza zero."""

    @staticmethod
    def process_math(expr_str: str) -> dict:
        try:
            x = sp.Symbol("x")
            expr = sp.sympify(expr_str)
            simplified = sp.simplify(expr)
            return {
                "type": "math",
                "source": "local_engine",
                "latex": f"f(x) = {sp.latex(simplified)}",
            }
        except Exception as e:
            return {
                "type": "math",
                "source": "local_engine",
                "latex": r"\text{Errore parsing math locale}",
            }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("[LOCAL DAEMON] Widget LIM connesso via WebSocket.")

    async with httpx.AsyncClient(timeout=2.5) as http_client:
        try:
            while True:
                raw_data = await websocket.receive_text()
                payload = json.loads(raw_data)
                action = payload.get("action")

                # Heartbeat check dal Widget
                if action == "ping_remote":
                    try:
                        resp = await http_client.get(
                            "http://192.168.1.100:8000/health"
                        )
                        if resp.status_code == 200:
                            await websocket.send_text(
                                json.dumps({"type": "pong_remote"})
                            )
                    except Exception:
                        pass
                    continue

                target = ModelRouter.get_target(action)
                print(
                    f"[ROUTER] Action: '{action}' ➔ Target selezionato: {target.value}"
                )

                # --- ROUTE LOCALE ---
                if target == RouteTarget.LOCAL:
                    if action == "sympy_math":
                        res = LocalEngine.process_math(
                            payload.get("data", "x^2 - 4")
                        )
                        await websocket.send_text(json.dumps(res))

                # --- ROUTE REMOTA ---
                elif target == RouteTarget.REMOTE:
                    try:
                        response = await http_client.post(
                            REMOTE_SERVER_URL, json=payload
                        )
                        response.raise_for_status()
                        await websocket.send_text(response.text)

                    except (httpx.ConnectError, httpx.TimeoutException):
                        print(
                            f"[ROUTER WARN] Server remoto irraggiungibile per action: {action}"
                        )
                        fallback_msg = {
                            "type": "system_warning",
                            "message": "Server remoto offline. Passaggio a Modalità Locale.",
                        }
                        await websocket.send_text(json.dumps(fallback_msg))

        except WebSocketDisconnect:
            print("[LOCAL DAEMON] Widget disconnesso.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=5000)
