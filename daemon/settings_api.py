"""
Settings API for LIM-AI Copilot Local Daemon.

Design Note:
    This module encapsulates setting management and validation for the local
    daemon. It reads and writes settings from/to an external YAML configuration file
    using Pydantic validation (v2). It exposes APIRouter routes to manage and test
    connectivity with the remote server. Circular dependencies are avoided by keeping
    settings loading and routing in this module, allowing the main entry point to
    import and mount the router cleanly.
"""

import logging
import time
from pathlib import Path
import httpx
import yaml
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

# Initialize standard logging following AGENTS.md guidelines
logger = logging.getLogger("daemon_settings_api")
PROBE_CANDIDATES = (
    ("health", "/health"),
    ("ollama", "/api/tags"),
    ("base", ""),
)

router = APIRouter()
CONFIG_PATH = Path(__file__).parent / "config.yaml"


class DaemonSettings(BaseModel):
    """Pydantic model representing local daemon configuration settings."""
    remote_base_url: str = "http://192.168.1.100:8000"
    api_key: str = ""
    disable_local_backup: bool = False


def load_settings() -> DaemonSettings:
    """
    Loads daemon settings from config.yaml.

    Returns:
        A DaemonSettings object populated with config values, or defaults.
    """
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r") as f:
                data = yaml.safe_load(f)
                if data:
                    logger.info("Configuration successfully loaded from config.yaml.")
                    return DaemonSettings(**data)
        except Exception as e:
            logger.error("Failed to load config.yaml, using defaults. Error: %s", e)
    logger.info("config.yaml not found or empty. Using default configurations.")
    return DaemonSettings()


def save_settings(s: DaemonSettings) -> None:
    """
    Persists DaemonSettings to config.yaml.

    Args:
        s: The DaemonSettings instance to save.
    """
    try:
        with open(CONFIG_PATH, "w") as f:
            yaml.safe_dump(s.model_dump(), f)
        logger.info("Configuration successfully written to config.yaml.")
    except Exception as e:
        logger.error("Failed to write to config.yaml: %s", e)


def build_auth_headers(api_key: str) -> dict[str, str]:
    """Builds Authorization headers only when an API key is configured."""
    if api_key.strip():
        return {"Authorization": f"Bearer {api_key}"}
    return {}


async def probe_remote_base_url(
    base_url: str,
    api_key: str,
    timeout_seconds: float = 3.0,
) -> dict:
    """
    Tests reachability of the configured remote base URL.

    Design Note:
        The original implementation only probed `<base>/health`, which works for the
        project FastAPI server but incorrectly reports a failure for alternative local
        endpoints such as Ollama (`http://localhost:11434`) that expose other probe
        paths like `/api/tags`. We now try a short ordered list of well-known probe
        endpoints and accept the first successful 2xx response.

    Args:
        base_url: Base URL configured by the user.
        api_key: Optional bearer token.
        timeout_seconds: HTTP timeout used for each probe request.

    Returns:
        A dictionary containing:
        - `ok`: whether the target is reachable through a supported probe.
        - `latency_ms`: elapsed milliseconds when available.
        - `probe_label`: matched probe type (`health`, `ollama`, `base`) on success.
        - `message`: user-friendly diagnostic when no probe succeeded.
    """
    start = time.perf_counter()
    headers = build_auth_headers(api_key)
    normalized_base_url = base_url.rstrip("/")
    last_status_code: int | None = None

    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=True,
        ) as client:
            for probe_label, suffix in PROBE_CANDIDATES:
                probe_url = normalized_base_url if not suffix else f"{normalized_base_url}{suffix}"
                try:
                    resp = await client.get(probe_url, headers=headers)
                except (httpx.ConnectError, httpx.TimeoutException):
                    continue

                last_status_code = resp.status_code
                latency_ms = round((time.perf_counter() - start) * 1000)

                if 200 <= resp.status_code < 300:
                    return {
                        "ok": True,
                        "latency_ms": latency_ms,
                        "probe_label": probe_label,
                        "message": f"Endpoint raggiungibile tramite '{probe_label}'.",
                    }

                if resp.status_code == 404:
                    continue

                if resp.status_code in (401, 403):
                    return {
                        "ok": False,
                        "latency_ms": latency_ms,
                        "probe_label": probe_label,
                        "message": (
                            "Endpoint raggiungibile, ma autenticazione rifiutata "
                            f"(HTTP {resp.status_code})."
                        ),
                    }

                return {
                    "ok": False,
                    "latency_ms": latency_ms,
                    "probe_label": probe_label,
                    "message": (
                        "Endpoint raggiungibile, ma ha restituito una risposta inattesa "
                        f"(HTTP {resp.status_code})."
                    ),
                }
    except Exception as e:
        logger.warning("Unexpected remote probe failure for '%s': %s", normalized_base_url, e)

    message = "Server remoto non raggiungibile"
    if last_status_code == 404:
        message = (
            "Host raggiungibile, ma nessuno degli endpoint supportati "
            "(/health, /api/tags, /) ha risposto correttamente."
        )

    return {
        "ok": False,
        "latency_ms": None,
        "probe_label": None,
        "message": message,
    }


# Globally shared setting state in memory, as required by design
settings = load_settings()


@router.get("/setup", response_class=HTMLResponse)
async def setup_page() -> FileResponse:
    """
    Serves the setup.html page.

    Returns:
        The FileResponse containing setup.html.
    """
    logger.info("Serving settings setup HTML page.")
    return FileResponse(Path(__file__).parent / "setup.html")


@router.get("/api/config")
async def get_config() -> dict:
    """
    Retrieves current configuration settings with a masked API key.

    Returns:
        A dictionary containing the base URL and the masked API key.
    """
    logger.info("Configuration settings requested.")
    masked = f"••••••{settings.api_key[-4:]}" if len(settings.api_key) >= 4 else ""
    return {
        "remote_base_url": settings.remote_base_url,
        "api_key_masked": masked,
        "disable_local_backup": settings.disable_local_backup,
    }


class ConfigUpdate(BaseModel):
    """Payload schema for updating configuration."""
    remote_base_url: str
    api_key: str | None = None  # Empty/omitted value means do not touch the existing key
    disable_local_backup: bool | None = None


@router.post("/api/config")
async def update_config(update: ConfigUpdate) -> dict:
    """
    Updates in-memory settings and saves them to the config file.

    Args:
        update: The validated ConfigUpdate payload.

    Returns:
        Status dict indicating success.
    """
    logger.info("Received configuration update request.")
    settings.remote_base_url = update.remote_base_url.rstrip("/")
    if update.api_key is not None and update.api_key.strip() != "":
        settings.api_key = update.api_key
    if update.disable_local_backup is not None:
        settings.disable_local_backup = update.disable_local_backup
    save_settings(settings)
    return {"status": "saved"}


@router.post("/api/test-connection")
async def test_connection() -> dict:
    """
    Tests HTTP connectivity with the remote server.

    Returns:
        A response containing status, latency_ms and optional error messages.
    """
    logger.info("Testing connection to remote server: %s", settings.remote_base_url)
    probe = await probe_remote_base_url(
        base_url=settings.remote_base_url,
        api_key=settings.api_key,
        timeout_seconds=3.0,
    )
    if probe["ok"]:
        logger.info(
            "Remote server probe succeeded using '%s'.",
            probe["probe_label"],
        )
        return {
            "status": "ok",
            "latency_ms": probe["latency_ms"],
            "message": probe["message"],
        }

    logger.warning("Remote server connection test failed: %s", probe["message"])
    return {
        "status": "error",
        "latency_ms": probe["latency_ms"],
        "message": probe["message"],
    }
