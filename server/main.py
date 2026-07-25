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
import os
from typing import Any, Dict
from fastapi import FastAPI, Depends, Header, HTTPException, status

# Configure logging using standard logging library as per AGENTS.md philosophy
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("mock_remote_server")

# Retrieve the shared secret from environment variables
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    # Fail to start immediately with a clear error if it's not configured
    raise RuntimeError("API_KEY environment variable is not configured. Server startup aborted.")

# Import the graph service (will also validate LLM_MODEL is configured at startup)
from services.graph_service import generate_concept_map

app = FastAPI(
    title="LIM-AI Copilot Mock Remote Server",
    description="Mock remote server for development verification and API routing with authentication",
    version="1.0.0"
)


async def verify_api_key(authorization: str = Header(default=None)) -> None:
    """
    Dependency to verify that the Authorization header matches Bearer <token>.

    Args:
        authorization: The Authorization header parsed from the request.

    Raises:
        HTTPException: 401 Unauthorized if missing or invalid.
    """
    if not authorization:
        logger.warning("Access denied: Authorization header is missing.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning("Access denied: Authorization header format must be Bearer <token>.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )

    token = parts[1]
    if token != API_KEY:
        logger.warning("Access denied: Provided API key token does not match the configured secret.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
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
    Health check endpoint. Unauthenticated.

    Returns:
        A dictionary with status "ok".
    """
    logger.info("Health check endpoint queried.")
    return {"status": "ok"}


@app.post("/api/v1/analyze")
async def analyze(payload: Dict[str, Any], _auth: None = Depends(verify_api_key)) -> Dict[str, Any]:
    """
    Mock analyze endpoint that echoes back request payloads with added metadata.
    Requires dynamic bearer token verification.

    If the requested action is 'concept_map', generates a real concept map
    using LiteLLM.

    Args:
        payload: Arbitrary JSON data representing the requested action.
        _auth: Injected authentication dependency.

    Returns:
        The exact request payload processed or augmented with "source" metadata.
    """
    action = payload.get("action")
    logger.info("Authenticated analyze request with payload action: %s", action)

    if action == "concept_map":
        data_obj = payload.get("data") or {}
        topic = data_obj.get("topic")
        if not topic:
            raise HTTPException(
                status_code=400,
                detail="Missing 'topic' field inside 'data' for 'concept_map' action"
            )
        language = data_obj.get("language", "it")

        # Call the real concept map generator using LiteLLM
        mermaid_code = generate_concept_map(topic, language)

        return {
            "type": "concept_map",
            "source": "remote_llm",
            "mermaid_code": mermaid_code
        }

    # Mirror back the payload with augmented metadata for non-implemented remote actions
    response_data = dict(payload)
    response_data["source"] = "mock_server"

    logger.info("Responding with mock payload including source field.")
    return response_data
