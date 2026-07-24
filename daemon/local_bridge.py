import asyncio
import io
import json
from enum import Enum
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import httpx
from mss import mss
from PIL import Image
import sympy as sp

# Import the configuration settings and routes router dynamically
from settings_api import settings, router as settings_router

app = FastAPI(title="LIM AI Local Daemon Bridge")

# Include the administrative and setup settings endpoints as specified
app.include_router(settings_router)


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

                # Heartbeat check dal Widget using dynamically read remote_base_url
                if action == "ping_remote":
                    try:
                        resp = await http_client.get(
                            f"{settings.remote_base_url}/health",
                            headers={"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
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
                    elif action == "fast_ocr":
                        # Fast OCR is not implemented locally yet, return explicit NotImplemented error shape
                        err_payload = {
                            "type": "error",
                            "code": "NOT_IMPLEMENTED",
                            "action": "fast_ocr",
                            "message": "OCR locale non ancora disponibile"
                        }
                        await websocket.send_text(json.dumps(err_payload))

                # --- ROUTE REMOTA ---
                elif target == RouteTarget.REMOTE:
                    try:
                        # Construct remote analyze URL dynamically
                        remote_analyze_url = f"{settings.remote_base_url}/api/v1/analyze"
                        response = await http_client.post(
                            remote_analyze_url,
                            json=payload,
                            headers={"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
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
