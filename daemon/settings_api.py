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

router = APIRouter()
CONFIG_PATH = Path(__file__).parent / "config.yaml"


class DaemonSettings(BaseModel):
    """Pydantic model representing local daemon configuration settings."""
    remote_base_url: str = "http://192.168.1.100:8000"
    api_key: str = ""


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
    }


class ConfigUpdate(BaseModel):
    """Payload schema for updating configuration."""
    remote_base_url: str
    api_key: str | None = None  # Empty/omitted value means do not touch the existing key


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
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                f"{settings.remote_base_url}/health",
                headers={"Authorization": f"Bearer {settings.api_key}"},
            )
        latency_ms = round((time.perf_counter() - start) * 1000)
        if resp.status_code == 200:
            logger.info("Remote server health-check succeeded: 200 OK.")
            return {"status": "ok", "latency_ms": latency_ms}
        logger.warning("Remote server health-check failed with HTTP: %s", resp.status_code)
        return {
            "status": "error",
            "latency_ms": latency_ms,
            "message": f"HTTP {resp.status_code}",
        }
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.warning("Remote server connection test failed: %s", e)
        return {
            "status": "error",
            "latency_ms": None,
            "message": "Server remoto non raggiungibile",
        }
