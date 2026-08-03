import asyncio
import json
import logging
import datetime
import math
import struct
from enum import Enum
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import httpx
from mss import mss
from PIL import Image
import sympy as sp
import pytesseract
import hashlib
import os
import sys
from fastapi.staticfiles import StaticFiles

DAEMON_HOST = "127.0.0.1"
DAEMON_PORT = 5000


def is_disconnect_exception(e: Exception) -> bool:
    """
    Helper to identify common websocket/client disconnection exceptions
    from Starlette/FastAPI/Uvicorn to handle them gracefully.
    """
    if isinstance(e, WebSocketDisconnect):
        return True
    if isinstance(e, RuntimeError):
        msg = str(e).lower()
        if (
            "is not connected" in msg
            or "disconnected" in msg
            or "unexpected asgi message" in msg
        ):
            return True
    return False


# Import the configuration settings and routes router dynamically
from settings_api import settings, router as settings_router, Credential

# Configure standard logger following AGENTS.md
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("local_bridge")

import re


def parse_filename_timestamp(filename: str) -> datetime.datetime | None:
    """
    Parses an ISO 8601 timestamp from a lesson backup filename.
    Format example: YYYY-MM-DDTHH-MM-SS.ffffff+HH-MM.jsonl (with colons replaced by dashes)
    """
    if not filename.endswith(".jsonl"):
        return None
    stem = filename[:-6]  # strip .jsonl

    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2})-(\d{2})-(\d{2})", stem)
    if not match:
        return None

    year, month, day, hour, minute, second = map(int, match.groups())

    tz = datetime.timezone.utc
    offset_match = re.search(r"([+-])(\d{2})-(\d{2})$", stem)
    if offset_match:
        sign, offset_h, offset_m = offset_match.groups()
        offset_val = int(offset_h) * 60 + int(offset_m)
        if sign == "-":
            offset_val = -offset_val
        tz = datetime.timezone(datetime.timedelta(minutes=offset_val))
    elif stem.endswith("Z"):
        tz = datetime.timezone.utc

    return datetime.datetime(year, month, day, hour, minute, second, tzinfo=tz)


def cleanup_old_backups(backups_dir: str | None = None) -> None:
    """
    Scans daemon/lesson_backups/ (or overridable backups_dir) and deletes any .jsonl backup file
    whose filename timestamp is older than LESSON_BACKUP_RETENTION_DAYS (default 30).
    Logs clearly whenever files are deleted.
    """
    try:
        retention_days = int(os.getenv("LESSON_BACKUP_RETENTION_DAYS", "30"))
        if backups_dir is None:
            backups_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "lesson_backups")
            )
        if not os.path.exists(backups_dir):
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        threshold = now - datetime.timedelta(days=retention_days)
        logger.info(
            f"Scanning '{backups_dir}' for lesson backups older than {retention_days} days "
            f"(threshold: {threshold.isoformat()})."
        )

        deleted_count = 0
        for filename in os.listdir(backups_dir):
            if not filename.endswith(".jsonl"):
                continue
            filepath = os.path.join(backups_dir, filename)
            try:
                dt = parse_filename_timestamp(filename)
                if dt and dt < threshold:
                    os.remove(filepath)
                    deleted_count += 1
                    logger.info(
                        f"Deleted old lesson backup file: '{filename}' (timestamp: {dt.isoformat()})"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to process backup file '{filename}' during cleanup: {e}"
                )

        if deleted_count > 0:
            logger.info(
                f"Cleanup complete. Deleted {deleted_count} old lesson backup files."
            )
        else:
            logger.info("Cleanup complete. No old lesson backup files were found.")
    except Exception as e:
        logger.error(f"Error during backup cleanup: {e}")


app = FastAPI(title="LIM AI Local Daemon Bridge")


@app.on_event("startup")
async def on_startup() -> None:
    cleanup_old_backups()


# Include the administrative and setup settings endpoints as specified
app.include_router(settings_router)

from fastapi import Response


class CORSStaticFiles(StaticFiles):
    """
    Custom StaticFiles wrapper that appends CORS headers to responses,
    allowing 3D model assets to be loaded by <model-viewer> inside
    the widget even when running on a different origin (like file://).
    """

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        return response


# Serve local 3D models cache under /models_cache
os.makedirs("model_cache", exist_ok=True)
app.mount(
    "/models_cache", CORSStaticFiles(directory="model_cache"), name="models_cache"
)


async def send_and_backup(
    websocket: WebSocket, message: dict | str, backup_path: str | None
) -> None:
    """
    Sends the message over the websocket and, if the message represents valid lesson content,
    appends it as a single JSON line to the session's backup file.
    """
    message_str = message if isinstance(message, str) else json.dumps(message)
    try:
        await websocket.send_text(message_str)
    except Exception as e:
        if is_disconnect_exception(e):
            logger.info(
                "Widget disconnesso durante l'invio (send_and_backup), arresto pulito."
            )
            raise WebSocketDisconnect()
        raise

    # Return early and bypass file writing if backup is disabled in settings
    if settings.disable_local_backup:
        return

    if not backup_path:
        return

    try:
        msg_dict = json.loads(message_str) if isinstance(message, str) else message
    except Exception:
        return

    # Filter out non-content messages (errors, warnings, ping/pong, and non-final subtitles)
    msg_type = msg_dict.get("type")
    if msg_type in ("error", "system_warning", "pong_remote"):
        return

    if msg_type == "subtitle" and not msg_dict.get("is_final", False):
        return

    # Only backup valid lesson content (sympy_math, concept_map, load_3d_model, generate_quiz, generate_summary, and final subtitle)
    backup_entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "message": msg_dict,
    }

    try:
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        with open(backup_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(backup_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to write to backup file {backup_path}: {e}")


class MissingCredentialsError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def get_active_llm_credential(action: str | None) -> Credential | None:
    """Resolves active LLM credential based on action scope with fallback to global."""
    scope_map = {
        "concept_map": "concept_map",
        "generate_quiz": "quiz_and_summary",
        "generate_summary": "quiz_and_summary",
        "transcribe_audio": "translation",
        "fast_ocr": "ocr",
        "ocr_vision": "ocr",
        "ocr": "ocr",
    }
    target_scope = scope_map.get(action, "global") if action else "global"

    # 1. Search for specifically scoped LLM credential that is enabled
    for c in settings.credentials:
        if (
            c.enabled
            and c.type in ("llm_cloud", "llm_ollama")
            and getattr(c, "scope", "global") == target_scope
        ):
            return c

    # 2. Fallback to 'global' scope
    if target_scope != "global":
        for c in settings.credentials:
            if (
                c.enabled
                and c.type in ("llm_cloud", "llm_ollama")
                and getattr(c, "scope", "global") == "global"
            ):
                return c

    return None


def get_outgoing_headers(action: str, payload_data: dict) -> dict:
    headers = {}

    # 1. LLM action check
    is_llm_action = action in (
        "concept_map",
        "generate_quiz",
        "generate_summary",
        "ocr_vision",
    )
    is_translation_stt = action == "transcribe_audio" and bool(
        payload_data.get("target_language")
    )

    if is_llm_action or is_translation_stt:
        active_llm = get_active_llm_credential(action)
        if active_llm:
            if active_llm.model:
                headers["X-LLM-Model"] = active_llm.model
            if active_llm.type == "llm_cloud" and active_llm.api_key:
                headers["X-LLM-API-Key"] = active_llm.api_key
            if active_llm.api_base:
                headers["X-LLM-API-Base"] = active_llm.api_base
        else:
            if is_llm_action:
                raise MissingCredentialsError(
                    "Nessuna credenziale LLM configurata e abilitata. Vai su /setup per aggiungerne una."
                )

    # 2. Sketchfab action check
    if action == "load_3d_model":
        active_sf = next(
            (c for c in settings.credentials if c.enabled and c.type == "sketchfab"),
            None,
        )
        if active_sf:
            if active_sf.access_token:
                headers["X-Sketchfab-Token"] = active_sf.access_token
        else:
            raise MissingCredentialsError(
                "Nessuna credenziale Sketchfab configurata e abilitata. Vai su /setup per aggiungerne una."
            )

    return headers


def attach_active_credentials(payload: dict) -> None:
    """Helper to attach active LLM and Sketchfab credentials from settings into the request payload."""
    action = payload.get("action")
    active_llm = get_active_llm_credential(action)
    active_sf = next(
        (c for c in settings.credentials if c.enabled and c.type == "sketchfab"), None
    )

    daemon_credentials = {}
    if active_llm:
        daemon_credentials["llm"] = {
            "type": active_llm.type,
            "model": active_llm.model,
            "api_key": active_llm.api_key,
            "api_base": active_llm.api_base,
        }
    if active_sf:
        daemon_credentials["sketchfab"] = {"access_token": active_sf.access_token}

    if daemon_credentials:
        payload["credentials"] = daemon_credentials


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


CACHE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "model_cache"))


async def handle_load_3d_model(
    query: str,
    http_client: httpx.AsyncClient,
    payload: dict,
    custom_headers: dict | None = None,
) -> dict:
    """
    Handles loading a 3D model with local caching on the daemon.
    Checks the local cache first by hashing the query. If a hit occurs, serves it immediately.
    On a miss, fetches from the remote server, downloads any external assets, caches them,
    and returns the local file URL path.
    """
    q_clean = query.lower().strip()
    cache_key = hashlib.sha256(q_clean.encode("utf-8")).hexdigest()
    model_dir = os.path.join(CACHE_DIR, cache_key)
    metadata_file = os.path.join(model_dir, "metadata.json")
    gltf_file = os.path.join(model_dir, "scene.gltf")

    # Cache HIT
    if os.path.exists(metadata_file) and os.path.exists(gltf_file):
        logger.info("Local Daemon Cache HIT for 3D model query: '%s'", query)
        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            return {
                "type": "model_3d",
                "source": "remote_index",
                "model_url": f"http://{DAEMON_HOST}:{DAEMON_PORT}/models_cache/{cache_key}/scene.gltf",
                "label": metadata["title"],
                "attribution": metadata["attribution"],
            }
        except Exception as e:
            logger.error("Failed to read metadata.json from local cache: %s", e)

    # Cache MISS
    logger.info("Local Daemon Cache MISS for 3D model query: '%s'", query)

    remote_analyze_url = f"{settings.remote_base_url}/api/v1/analyze"
    headers = (
        {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
    )
    if custom_headers:
        headers.update(custom_headers)

    response = await http_client.post(remote_analyze_url, json=payload, headers=headers)
    response.raise_for_status()
    response_data = response.json()

    if response_data.get("type") == "error":
        return response_data

    remote_model_url = response_data.get("model_url")
    if not remote_model_url:
        return response_data

    # Extract base remote model folder
    parts = remote_model_url.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "models":
        uid = parts[1]
        remote_base = f"/models/{uid}"
    else:
        remote_base = os.path.dirname(remote_model_url)

    os.makedirs(model_dir, exist_ok=True)

    # Download scene.gltf
    gltf_url = f"{settings.remote_base_url}{remote_model_url}"
    gltf_resp = await http_client.get(gltf_url, headers=headers)
    gltf_resp.raise_for_status()
    gltf_text = gltf_resp.text

    with open(gltf_file, "w", encoding="utf-8") as f:
        f.write(gltf_text)

    # Parse and download dependent assets
    try:
        gltf_json = json.loads(gltf_text)
        dependent_uris = []

        for buf in gltf_json.get("buffers", []):
            uri = buf.get("uri")
            if uri and not uri.startswith("data:"):
                dependent_uris.append(uri)

        for img in gltf_json.get("images", []):
            uri = img.get("uri")
            if uri and not uri.startswith("data:"):
                dependent_uris.append(uri)

        for uri in dependent_uris:
            local_uri_path = os.path.join(model_dir, uri)
            os.makedirs(os.path.dirname(local_uri_path), exist_ok=True)

            remote_uri_url = f"{settings.remote_base_url}{remote_base}/{uri}"
            uri_resp = await http_client.get(remote_uri_url, headers=headers)
            uri_resp.raise_for_status()

            with open(local_uri_path, "wb") as f:
                f.write(uri_resp.content)
            logger.info("Daemon cached dependent resource: '%s'", uri)

    except Exception as e:
        logger.error("Failed to cache dependent assets for model %s: %s", query, e)

    # Save metadata
    metadata = {
        "uid": response_data.get("uid", cache_key),
        "title": response_data.get("label", query),
        "attribution": response_data.get("attribution", {}),
    }
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=4)

    return {
        "type": "model_3d",
        "source": "remote_index",
        "model_url": f"http://{DAEMON_HOST}:{DAEMON_PORT}/models_cache/{cache_key}/scene.gltf",
        "label": metadata["title"],
        "attribution": metadata["attribution"],
    }


class LocalEngine:
    """Engine di esecuzione locale a latenza zero."""

    @staticmethod
    def process_math(expr_str: str) -> dict:
        try:
            expr = sp.sympify(expr_str)
            simplified = sp.simplify(expr)

            # Retrieve free symbols
            free_symbols = list(simplified.free_symbols)
            plot_data = None

            if len(free_symbols) == 1:
                symbol = free_symbols[0]
                try:
                    f = sp.lambdify(symbol, simplified, "math")
                    x_vals = []
                    y_vals = []

                    # Generate 101 points from -10 to 10 with step 0.2
                    for i in range(101):
                        x_val = -10.0 + i * 0.2
                        x_val = round(x_val, 5)
                        try:
                            y_val = f(x_val)

                            # Verify y_val is real and finite
                            if isinstance(y_val, complex):
                                continue
                            import math

                            if not math.isfinite(y_val):
                                continue

                            x_vals.append(float(x_val))
                            y_vals.append(float(y_val))
                        except Exception:
                            # Skip points with evaluation errors
                            continue

                    if len(x_vals) > 0:
                        plot_data = {"x": x_vals, "y": y_vals}
                except Exception:
                    plot_data = None

            return {
                "type": "math",
                "source": "local_engine",
                "latex": f"f(x) = {sp.latex(simplified)}",
                "plot_data": plot_data,
            }
        except Exception:
            return {
                "type": "math",
                "source": "local_engine",
                "latex": r"\text{Errore parsing math locale}",
                "plot_data": None,
            }


def compute_rms(chunk_bytes: bytes) -> float:
    """Computes the Root Mean Square (RMS) amplitude of signed 16-bit PCM bytes."""
    num_samples = len(chunk_bytes) // 2
    if num_samples == 0:
        return 0.0
    fmt = f"<{num_samples}h"
    samples = struct.unpack(fmt, chunk_bytes)
    sum_squares = sum(s * s for s in samples)
    mean_squares = sum_squares / num_samples
    return math.sqrt(mean_squares)


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
        self.backup_path: str | None = None

    async def start(
        self,
        websocket: WebSocket,
        target_language: str | None,
        backup_path: str | None = None,
    ) -> None:
        """Starts a background audio capture loop."""
        if self.is_running:
            logger.warning(
                "Transcription already running. Stopping previous stream first."
            )
            await self.stop()

        self.websocket = websocket
        self.target_language = target_language
        self.backup_path = backup_path

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
                frames_per_buffer=1024,
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
                "message": f"Could not open audio input device: {e}",
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
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(
                    settings.remote_action_timeout_seconds, connect=5.0
                )
            ) as http_client:
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

                        # Compute RMS amplitude of the chunk to detect silence
                        rms_val = compute_rms(chunk_to_process)
                        if rms_val < settings.silence_rms_threshold:
                            logger.debug(
                                f"[Audio Capture] Skipped silent chunk: RMS={rms_val:.1f} "
                                f"below threshold={settings.silence_rms_threshold}"
                            )
                            await asyncio.sleep(
                                0.01
                            )  # Safe yield to prevent tight loop CPU starvation
                            continue

                        # Calculate duration
                        duration = len(chunk_to_process) / (
                            rate * channels * bytes_per_sample
                        )
                        logger.info(
                            f"[Audio Capture] Captured chunk: size={len(chunk_to_process)} bytes, "
                            f"duration={duration:.2f}s, RMS={rms_val:.1f}"
                        )

                        # Base64-encode chunk and send to remote server
                        audio_b64 = base64.b64encode(chunk_to_process).decode("utf-8")
                        payload = {
                            "action": "transcribe_audio",
                            "data": {
                                "audio_base64": audio_b64,
                                "sample_rate": 16000,
                                "encoding": "pcm_s16le",
                                "target_language": self.target_language,
                            },
                        }
                        attach_active_credentials(payload)

                        headers = {}
                        if settings.api_key:
                            headers["Authorization"] = f"Bearer {settings.api_key}"

                        try:
                            llm_headers = get_outgoing_headers(
                                "transcribe_audio", payload["data"]
                            )
                            headers.update(llm_headers)

                            remote_analyze_url = (
                                f"{settings.remote_base_url}/api/v1/analyze"
                            )
                            response = await http_client.post(
                                remote_analyze_url, json=payload, headers=headers
                            )
                            response.raise_for_status()
                            response_data = response.json()

                            websocket_msg = {
                                "type": "subtitle",
                                "source": "remote_stt",
                                "text": response_data.get("text"),
                                "translated_text": response_data.get("translated_text"),
                                "is_final": True,
                            }

                            if self.websocket:
                                await send_and_backup(
                                    self.websocket, websocket_msg, self.backup_path
                                )

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
                                    await self.websocket.send_text(
                                        json.dumps(fallback_msg)
                                    )
                                except Exception as ws_err:
                                    logger.error(
                                        f"Failed to send system_warning to websocket: {ws_err}"
                                    )
                        except Exception as e:
                            if is_disconnect_exception(e):
                                logger.info(
                                    "Widget disconnesso durante l'invio della trascrizione, arresto del loop."
                                )
                                self.is_running = False
                                break
                            logger.error(
                                f"Errore non gestito durante l'invio della trascrizione: {e}",
                                exc_info=True,
                            )

        except asyncio.CancelledError:
            logger.info("Microphone capture loop background task cancelled.")
        except Exception as e:
            if is_disconnect_exception(e) or isinstance(e, WebSocketDisconnect):
                logger.info(
                    "Widget disconnesso durante l'ascolto, arresto del loop di cattura."
                )
            else:
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

    # Create session backup path under daemon/lesson_backups/<timestamp>.jsonl
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    now_clean = now_iso.replace(":", "-")
    backup_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "lesson_backups")
    )
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, f"{now_clean}.jsonl")

    # Instantiate per-connection transcription session manager
    transcription_session = TranscriptionSession()

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.remote_action_timeout_seconds, connect=5.0)
    ) as http_client:
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
                            headers=(
                                {"Authorization": f"Bearer {settings.api_key}"}
                                if settings.api_key
                                else {}
                            ),
                            timeout=2.5,
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
                        res = LocalEngine.process_math(payload.get("data", "x^2 - 4"))
                        await send_and_backup(websocket, res, backup_path)
                    elif action == "fast_ocr":
                        data_obj = payload.get("data") or {}
                        region = data_obj.get("region") or {}
                        x = region.get("x", 0)
                        y = region.get("y", 0)
                        width = region.get("width", 1920)
                        height = region.get("height", 1080)

                        img = None
                        capture_error = None
                        try:
                            import tempfile

                            with mss() as sct:
                                monitor = {
                                    "top": int(y),
                                    "left": int(x),
                                    "width": int(width),
                                    "height": int(height),
                                }
                                sct_img = sct.grab(monitor)
                                img = Image.frombytes(
                                    "RGB", sct_img.size, sct_img.bgra, "raw", "BGRX"
                                )

                                # Save to a temporary file
                                with tempfile.NamedTemporaryFile(
                                    suffix=".png", delete=False
                                ) as tmp_file:
                                    img.save(tmp_file.name)
                        except Exception as e:
                            logger.error(
                                f"Failed to capture screen or perform OCR: {e}. Headless display environment restriction may apply."
                            )
                            capture_error = e

                        # 1. OCR Vision Dynamic Routing Exception:
                        # Check for an enabled credential with scope=="ocr". If found, send the image
                        # (base64) to the server action "ocr_vision" instead of running local Tesseract.
                        # If NOT found, or if the vision call fails, fall back to local Tesseract OCR.
                        active_ocr_cred = get_active_llm_credential("fast_ocr")
                        response_text = None
                        source_engine = "local_engine"

                        if capture_error is not None:
                            response_text = f"[OCR non ancora integrato, cattura fallita a causa di restrizioni display/headless: {capture_error}]"
                        elif active_ocr_cred and img is not None:
                            logger.info(
                                "Enabled 'ocr' scope credential found. Attempting remote Vision-LLM OCR..."
                            )
                            try:
                                import io
                                import base64

                                buffered = io.BytesIO()
                                img.save(buffered, format="PNG")
                                image_base64 = base64.b64encode(
                                    buffered.getvalue()
                                ).decode("utf-8")

                                ocr_vision_payload = {
                                    "action": "ocr_vision",
                                    "data": {"image_base64": image_base64},
                                }

                                remote_analyze_url = (
                                    f"{settings.remote_base_url}/api/v1/analyze"
                                )
                                req_headers = (
                                    {"Authorization": f"Bearer {settings.api_key}"}
                                    if settings.api_key
                                    else {}
                                )
                                custom_headers = get_outgoing_headers("ocr_vision", {})
                                req_headers.update(custom_headers)

                                response = await http_client.post(
                                    remote_analyze_url,
                                    json=ocr_vision_payload,
                                    headers=req_headers,
                                )
                                response.raise_for_status()
                                response_json = response.json()

                                if response_json.get("type") == "error":
                                    logger.warning(
                                        "Remote Vision OCR returned error response: %s. Falling back to Tesseract.",
                                        response_json.get("message"),
                                    )
                                else:
                                    response_text = response_json.get("text")
                                    source_engine = "remote_vision_llm"
                                    logger.info(
                                        "Successfully completed remote Vision-LLM OCR."
                                    )
                            except Exception as ve:
                                logger.error(
                                    "Remote Vision OCR call failed due to: %s. Falling back to Tesseract.",
                                    ve,
                                    exc_info=True,
                                )

                        # Fallback to local Tesseract if remote Vision OCR was not used or failed
                        if response_text is None:
                            if img is not None:
                                try:
                                    response_text = pytesseract.image_to_string(
                                        img
                                    ).strip()
                                    logger.info(
                                        "Screen capture successfully processed with Tesseract OCR (fallback/default)."
                                    )
                                except Exception as e:
                                    logger.error(
                                        f"Failed to perform local Tesseract OCR: {e}."
                                    )
                                    response_text = f"[OCR local fallback failed: {e}]"
                            else:
                                response_text = "[OCR failed: capture failed]"

                        ocr_payload = {
                            "type": "ocr",
                            "source": source_engine,
                            "text": response_text,
                        }
                        await websocket.send_text(json.dumps(ocr_payload))

                    elif action == "start_transcription":
                        data_obj = payload.get("data") or {}
                        target_lang = data_obj.get("target_language")
                        await transcription_session.start(
                            websocket, target_lang, backup_path
                        )

                    elif action == "stop_transcription":
                        await transcription_session.stop()

                # --- ROUTE REMOTA ---
                elif target == RouteTarget.REMOTE:
                    attach_active_credentials(payload)
                    try:
                        # Extract the data object safely and resolve custom headers
                        payload_data = payload.get("data") or {}
                        custom_headers = get_outgoing_headers(action, payload_data)
                    except MissingCredentialsError as e:
                        err_res = {
                            "type": "error",
                            "code": "MISSING_CREDENTIALS",
                            "action": action,
                            "message": e.message,
                        }
                        await websocket.send_text(json.dumps(err_res))
                        continue

                    try:
                        if action == "load_3d_model":
                            query = payload.get("data", {}).get("query")
                            if query:
                                res_metadata = await handle_load_3d_model(
                                    query, http_client, payload, custom_headers
                                )
                                await send_and_backup(
                                    websocket, res_metadata, backup_path
                                )
                                continue

                        # Construct remote analyze URL dynamically
                        remote_analyze_url = (
                            f"{settings.remote_base_url}/api/v1/analyze"
                        )
                        req_headers = (
                            {"Authorization": f"Bearer {settings.api_key}"}
                            if settings.api_key
                            else {}
                        )
                        req_headers.update(custom_headers)

                        response = await http_client.post(
                            remote_analyze_url, json=payload, headers=req_headers
                        )
                        response.raise_for_status()
                        await send_and_backup(websocket, response.text, backup_path)

                    except (httpx.ConnectError, httpx.TimeoutException):
                        logger.warning(
                            f"Server remoto irraggiungibile per action: {action}"
                        )
                        fallback_msg = {
                            "type": "system_warning",
                            "message": "Server remoto offline. Passaggio a Modalità Locale.",
                        }
                        await websocket.send_text(json.dumps(fallback_msg))

        except WebSocketDisconnect:
            logger.info("Widget disconnesso.")
        except Exception as e:
            if is_disconnect_exception(e):
                logger.info(
                    "Widget disconnesso (eccezione di disconnessione rilevata nel loop principale)."
                )
            else:
                logger.error(
                    f"Errore imprevisto nel loop websocket: {e}", exc_info=True
                )
        finally:
            # Clean up the transcription stream on websocket disconnection
            await transcription_session.stop()


def configure_tesseract_path() -> None:
    """Configures Pytesseract command path dynamically when running inside a PyInstaller package (frozen)."""
    if getattr(sys, "frozen", False):
        mei_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        bundled_tesseract_path = os.path.join(mei_dir, "tesseract", "tesseract.exe")
        pytesseract.pytesseract.tesseract_cmd = bundled_tesseract_path


configure_tesseract_path()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=DAEMON_HOST, port=DAEMON_PORT)
