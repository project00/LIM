"""
Mock Remote Server for LIM-AI Copilot.

Design Note:
    This module implements a minimal, stateless mock remote server. It stands in
    for the real cloud GPU server during initial integration and offline testing phases.
    The goal is to provide reliable, highly performant REST endpoints that mimic the
    production contract. All endpoints use modern FastAPI ASGI structures with strict PEP 484
    type annotations. Logging is handled via standard library logging module. No DI/IoC
    frameworks are used, ensuring grep-ability and maximum simplicity.
"""

import logging
from typing import Any, Dict
from fastapi import FastAPI

# Configure logging using standard logging library as per AGENTS.md philosophy
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("mock_remote_server")

app = FastAPI(
    title="LIM-AI Copilot Mock Remote Server",
    description="Mock remote server for development verification and API routing",
    version="1.0.0"
)


@app.get("/")
async def root() -> Dict[str, str]:
    """
    Root scaffolding endpoint.

    Returns:
        A dictionary with the scaffolding status.
    """
    logger.info("Scaffolding root endpoint queried.")
    return {"status": "scaffolding"}


@app.get("/health")
async def health() -> Dict[str, str]:
    """
    Health check endpoint.

    Returns:
        A dictionary with status "ok".
    """
    logger.info("Health check endpoint queried.")
    return {"status": "ok"}


@app.post("/api/v1/analyze")
async def analyze(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mock analyze endpoint that echoes back request payloads with added metadata.

    This acts as a transparent mirror to verify communication contracts (e.g.,
    concept maps, 3D model lookups, quizzes) before the actual heavy model routing
    logic is deployed.

    Args:
        payload: Arbitrary JSON data representing the requested action.

    Returns:
        The exact request payload augmented with "source": "mock_server".
    """
    logger.info("Received analyze request with payload action: %s", payload.get("action"))

    # Mirror back the payload with augmented metadata
    response_data = dict(payload)
    response_data["source"] = "mock_server"

    logger.info("Responding with mock payload including source field.")
    return response_data
