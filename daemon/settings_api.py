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
import os
import time
import uuid
from pathlib import Path
from typing import Literal
import httpx
import yaml
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

# Initialize standard logging following AGENTS.md guidelines
logger = logging.getLogger("daemon_settings_api")

router = APIRouter()
CONFIG_PATH = Path(__file__).parent / "config.yaml"


class Credential(BaseModel):
    """Pydantic model representing LLM or Sketchfab provider credentials."""

    id: str
    name: str
    type: Literal["llm_cloud", "llm_ollama", "sketchfab"]
    scope: Literal[
        "global", "concept_map", "quiz_and_summary", "translation", "ocr"
    ] = "global"
    enabled: bool = False
    model: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    access_token: str | None = None


class DaemonSettings(BaseModel):
    """Pydantic model representing local daemon configuration settings."""

    remote_base_url: str = "http://192.168.1.100:8000"
    api_key: str = ""
    disable_local_backup: bool = False
    credentials: list[Credential] = []
    remote_action_timeout_seconds: int = int(
        os.getenv("REMOTE_ACTION_TIMEOUT_SECONDS", "30")
    )
    silence_rms_threshold: int = int(os.getenv("SILENCE_RMS_THRESHOLD", "400"))


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
        "disable_local_backup": settings.disable_local_backup,
        "remote_action_timeout_seconds": settings.remote_action_timeout_seconds,
        "silence_rms_threshold": settings.silence_rms_threshold,
    }


class ConfigUpdate(BaseModel):
    """Payload schema for updating configuration."""

    remote_base_url: str
    api_key: str | None = (
        None  # Empty/omitted value means do not touch the existing key
    )
    disable_local_backup: bool | None = None
    remote_action_timeout_seconds: int | None = None
    silence_rms_threshold: int | None = None


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
    if update.remote_action_timeout_seconds is not None:
        settings.remote_action_timeout_seconds = update.remote_action_timeout_seconds
    if update.silence_rms_threshold is not None:
        settings.silence_rms_threshold = update.silence_rms_threshold
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
        logger.warning(
            "Remote server health-check failed with HTTP: %s", resp.status_code
        )
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


def mask_key(val: str | None) -> str:
    if not val:
        return ""
    return f"••••••{val[-4:]}" if len(val) >= 4 else "••••••"


def enforce_mutual_exclusivity(active_cred: Credential) -> None:
    # Resolve type group
    active_group = (
        "llm" if active_cred.type in ("llm_cloud", "llm_ollama") else "sketchfab"
    )
    active_scope = getattr(active_cred, "scope", "global")

    for c in settings.credentials:
        if c.id == active_cred.id:
            continue
        c_group = "llm" if c.type in ("llm_cloud", "llm_ollama") else "sketchfab"
        c_scope = getattr(c, "scope", "global")
        if c_group == active_group and c_scope == active_scope:
            c.enabled = False


class CredentialCreate(BaseModel):
    name: str
    type: Literal["llm_cloud", "llm_ollama", "sketchfab"]
    scope: Literal[
        "global", "concept_map", "quiz_and_summary", "translation", "ocr"
    ] = "global"
    enabled: bool = False
    model: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    access_token: str | None = None


class CredentialToggle(BaseModel):
    enabled: bool


@router.get("/api/credentials")
async def list_credentials() -> list[dict]:
    logger.info("Listing credentials.")
    result = []
    for cred in settings.credentials:
        # Default scope to 'global' if not present in loaded credential
        scope_val = getattr(cred, "scope", "global")
        result.append(
            {
                "id": cred.id,
                "name": cred.name,
                "type": cred.type,
                "scope": scope_val,
                "enabled": cred.enabled,
                "model": cred.model,
                "api_key_masked": mask_key(cred.api_key),
                "api_base": cred.api_base,
                "access_token_masked": mask_key(cred.access_token),
            }
        )
    return result


@router.post("/api/credentials")
async def add_credential(payload: CredentialCreate) -> dict:
    logger.info("Creating a new credential.")
    new_id = str(uuid.uuid4())
    cred = Credential(
        id=new_id,
        name=payload.name,
        type=payload.type,
        scope=payload.scope,
        enabled=payload.enabled,
        model=payload.model,
        api_key=payload.api_key,
        api_base=payload.api_base,
        access_token=payload.access_token,
    )
    if cred.enabled:
        enforce_mutual_exclusivity(cred)
    settings.credentials.append(cred)
    save_settings(settings)
    return {"status": "created", "id": new_id}


@router.patch("/api/credentials/{id}")
async def toggle_credential(id: str, payload: CredentialToggle) -> dict:
    logger.info("Patching credential %s.", id)
    target = None
    for c in settings.credentials:
        if c.id == id:
            target = c
            break
    if not target:
        return {"status": "error", "message": "Credential not found"}
    target.enabled = payload.enabled
    if target.enabled:
        enforce_mutual_exclusivity(target)
    save_settings(settings)
    return {"status": "updated"}


@router.delete("/api/credentials/{id}")
async def delete_credential(id: str) -> dict:
    logger.info("Deleting credential %s.", id)
    settings.credentials = [c for c in settings.credentials if c.id != id]
    save_settings(settings)
    return {"status": "deleted"}
