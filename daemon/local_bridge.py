import asyncio
import json
import logging
from enum import Enum
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import httpx
from mss import mss
from PIL import Image
import sympy as sp
import pytesseract

# Import the configuration settings and routes router dynamically
from settings_api import settings, router as settings_router

# Configure standard logger following AGENTS.md
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("local_bridge")

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
        "start_transcription": RouteTarget.LOCAL,
        "stop_transcription": RouteTarget.LOCAL,
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
        except Exception:
            return {
                "type": "math",
                "source": "local_engine",
                "latex": r"\text{Errore parsing math locale}",
            }


class TranscriptionSession:
    """
    Design Note:
        This class manages local microphone audio capture and its lifecycle.
        It runs an asynchronous background task which reads from a PyAudio input stream
        in chunks. Reading is offloaded to a separate worker thread using `asyncio.to_thread`
        to prevent blocking FastAPI's central single-threaded event loop.
        It records raw audio in 16kHz, mono, 16-bit format (paInt16), and accumulates chunks
        until they reach a ~1 second size (32,000 bytes).
        Each 1s chunk is base64-encoded and posted to the remote server. On success, the
        transcription is forwarded back to the widget as a consolidated subtitle. If the remote
        call fails (timeout/connection error), the exception is caught and logged, sending a
        fallback warning to the widget, without interrupting the capture loop.
        It handles errors gracefully (e.g. lack of default input device or audio hardware) by raising
        and returning a well-defined error JSON back to the widget.
    """

    def __init__(self) -> None:
        self.task: asyncio.Task | None = None
        self.stream = None
        self.pyaudio_instance = None
        self.is_running: bool = False
        self.websocket: WebSocket | None = None
        self.target_language: str | None = None

    async def start(self, websocket: WebSocket, target_language: str | None) -> None:
        """Starts a background audio capture loop."""
        if self.is_running:
            logger.warning("Transcription already running. Stopping previous stream first.")
            await self.stop()

        self.websocket = websocket
        self.target_language = target_language

        import pyaudio

        try:
            self.pyaudio_instance = pyaudio.PyAudio()
            # Try to open default input stream
            # 16kHz mono 16-bit (2 bytes per sample)
            self.stream = self.pyaudio_instance.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=1024
            )
        except Exception as e:
            logger.error(f"Failed to open PyAudio input device: {e}")
            if self.stream:
                try:
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None
            if self.pyaudio_instance:
                try:
                    self.pyaudio_instance.terminate()
                except Exception:
                    pass
                self.pyaudio_instance = None

            # Send standard error payload back to the widget
            error_payload = {
                "type": "error",
                "code": "NO_AUDIO_DEVICE",
                "action": "start_transcription",
                "message": f"Could not open audio input device: {e}"
            }
            await websocket.send_text(json.dumps(error_payload))
            return

        self.is_running = True
        self.task = asyncio.create_task(self._capture_loop())
        logger.info("Transcription session started successfully.")

    async def _capture_loop(self) -> None:
        """Background loop reading from PyAudio stream using asyncio.to_thread."""
        rate = 16000
        channels = 1
        bytes_per_sample = 2  # paInt16
        chunk_size_frames = 1024
        target_bytes = 32000  # exactly 1 second (16000 * 1 * 2)

        logger.info("Microphone background capture loop started.")
        import base64
        try:
            buffer = bytearray()
            async with httpx.AsyncClient(timeout=2.5) as http_client:
                while self.is_running and self.stream:
                    # Read frames in a thread to avoid blocking the event loop
                    data = await asyncio.to_thread(
                        self.stream.read, chunk_size_frames, exception_on_overflow=False
                    )
                    if not data:
                        await asyncio.sleep(0.01)
                        continue

                    buffer.extend(data)

                    # Accumulate and log raw audio chunks of ~1-second duration
                    while len(buffer) >= target_bytes:
                        chunk_to_process = buffer[:target_bytes]
                        buffer = buffer[target_bytes:]

                        # Calculate duration
                        duration = len(chunk_to_process) / (rate * channels * bytes_per_sample)
                        logger.info(
                            f"[Audio Capture] Captured chunk: size={len(chunk_to_process)} bytes, "
                            f"duration={duration:.2f}s"
                        )

                        # Base64-encode chunk and send to remote server
                        audio_b64 = base64.b64encode(chunk_to_process).decode("utf-8")
                        payload = {
                            "action": "transcribe_audio",
                            "data": {
                                "audio_base64": audio_b64,
                                "sample_rate": 16000,
                                "encoding": "pcm_s16le",
                                "target_language": self.target_language
                            }
                        }

                        headers = {}
                        if settings.api_key:
                            headers["Authorization"] = f"Bearer {settings.api_key}"

                        try:
                            remote_analyze_url = f"{settings.remote_base_url}/api/v1/analyze"
                            response = await http_client.post(
                                remote_analyze_url,
                                json=payload,
                                headers=headers
                            )
                            response.raise_for_status()
                            response_data = response.json()

                            websocket_msg = {
                                "type": "subtitle",
                                "source": "remote_stt",
                                "text": response_data.get("text"),
                                "translated_text": response_data.get("translated_text"),
                                "is_final": True
                            }

                            if self.websocket:
                                await self.websocket.send_text(json.dumps(websocket_msg))

                        except (httpx.ConnectError, httpx.TimeoutException) as e:
                            logger.warning(
                                f"Server remoto irraggiungibile per la trascrizione audio: {e}"
                            )
                            fallback_msg = {
                                "type": "system_warning",
                                "message": "Server remoto offline. Passaggio a Modalità Locale.",
                            }
                            if self.websocket:
                                try:
                                    await self.websocket.send_text(json.dumps(fallback_msg))
                                except Exception as ws_err:
                                    logger.error(
                                        f"Failed to send system_warning to websocket: {ws_err}"
                                    )
                        except Exception as e:
                            logger.error(
                                f"Errore non gestito durante l'invio della trascrizione: {e}"
                            )

        except asyncio.CancelledError:
            logger.info("Microphone capture loop background task cancelled.")
        except Exception as e:
            logger.error(f"Error in microphone capture loop: {e}")
        finally:
            logger.info("Microphone capture loop finished.")

    async def stop(self) -> None:
        """Cleans up active transcription tasks and releases PyAudio resources."""
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None

        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception as e:
                logger.error(f"Error closing PyAudio stream: {e}")
            self.stream = None

        if self.pyaudio_instance:
            try:
                self.pyaudio_instance.terminate()
            except Exception as e:
                logger.error(f"Error terminating PyAudio instance: {e}")
            self.pyaudio_instance = None

        logger.info("Transcription session stopped cleanly.")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Widget LIM connesso via WebSocket.")

    # Instantiate per-connection transcription session manager
    transcription_session = TranscriptionSession()

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
                logger.info(f"Action: '{action}' ➔ Target selezionato: {target.value}")

                # --- ROUTE LOCALE ---
                if target == RouteTarget.LOCAL:
                    if action == "sympy_math":
                        res = LocalEngine.process_math(
                            payload.get("data", "x^2 - 4")
                        )
                        await websocket.send_text(json.dumps(res))
                    elif action == "fast_ocr":
                        data_obj = payload.get("data") or {}
                        region = data_obj.get("region") or {}
                        x = region.get("x", 0)
                        y = region.get("y", 0)
                        width = region.get("width", 1920)
                        height = region.get("height", 1080)

                        try:
                            import tempfile
                            with mss() as sct:
                                monitor = {"top": int(y), "left": int(x), "width": int(width), "height": int(height)}
                                sct_img = sct.grab(monitor)
                                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

                                # Save to a temporary file
                                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
                                    img.save(tmp_file.name)

                            # Perform real OCR on the captured PIL Image using pytesseract
                            response_text = pytesseract.image_to_string(img).strip()
                            logger.info("Screen capture successfully processed with Tesseract OCR.")
                        except Exception as e:
                            # Note display access limitation explicitly
                            logger.error(f"Failed to capture screen or perform OCR: {e}. Headless display environment restriction may apply.")
                            response_text = f"[OCR non ancora integrato, cattura fallita a causa di restrizioni display/headless: {e}]"

                        ocr_payload = {
                            "type": "ocr",
                            "source": "local_engine",
                            "text": response_text
                        }
                        await websocket.send_text(json.dumps(ocr_payload))

                    elif action == "start_transcription":
                        data_obj = payload.get("data") or {}
                        target_lang = data_obj.get("target_language")
                        await transcription_session.start(websocket, target_lang)

                    elif action == "stop_transcription":
                        await transcription_session.stop()

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
                        logger.warning(f"Server remoto irraggiungibile per action: {action}")
                        fallback_msg = {
                            "type": "system_warning",
                            "message": "Server remoto offline. Passaggio a Modalità Locale.",
                        }
                        await websocket.send_text(json.dumps(fallback_msg))

        except WebSocketDisconnect:
            logger.info("Widget disconnesso.")
        finally:
            # Clean up the transcription stream on websocket disconnection
            await transcription_session.stop()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=5000)
