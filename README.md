# AI-Enhanced OpenBoard Ecosystem — LIM-AI Copilot

Welcome to the LIM-AI Copilot repository. This project enhances OpenBoard with a hybrid Edge-Cloud system for Interactive Whiteboards (LIM) in Italian classrooms, providing lightning-fast local computations (such as SymPy algebrics and local Fast OCR) and complex AI capabilities (visual processing, concept map generation, and quizzes) delegated to a high-performance remote server with GPU acceleration.

## Repository Structure

The project repository is structured as defined in the [Project Plan](docs/project-plan.md) (§5 and §11):

- `widget/`: Contains the front-end HTML5/CSS/JavaScript vanilla web widget for OpenBoard (`AI_LIM.wgt`).
- `daemon/`: Holds the Python FastAPI WebSocket Bridge running locally on the Interactive Whiteboard (LIM) computer.
- `server/`: Houses the Python FastAPI Remote Server codebase.
- `docs/`: Includes the project documentation, system architecture specifications, and communication contracts.

## Key Documentation

Please refer to the following documents for comprehensive specifications and development guidelines:

- **Project Architecture & Plan**: [docs/project-plan.md](docs/project-plan.md) — Contains the full architecture description, technological stack details, and the sprint-by-sprint release map.
- **Message Contract / API Specification**: [docs/api-contract.md](docs/api-contract.md) — Outlines the WebSocket and REST structure for local and remote communication between components.
- **Development & Coding Standards**: [AGENTS.md](AGENTS.md) — Describes the design philosophy and coding style guidelines based on ultimate simplicity, clear design notes, explicit composition, and testing strategy.

## Getting Started with Mock Remote Server

To allow fast and consistent development across different tasks without depending on a real remote GPU server, we provide a containerized lightweight Mock Remote Server.

### Prerequisites

- Docker and Docker Compose installed on your system.

### Running the Mock Server

Start the mock server container from the root directory of the repository:

```bash
docker compose up --build -d
```

This starts a mock server exposing FastAPI endpoints at `http://localhost:8000`:
- `GET /` -> Returns `200 OK` with JSON `{"status": "scaffolding"}`
- `GET /health` -> Returns `200 OK` with JSON `{"status": "ok"}`
- `POST /api/v1/analyze` -> Echoes back the request JSON with a `"source": "mock_server"` metadata field added.

### Stopping the Mock Server

To bring down the server:

```bash
docker compose down
```

## Contributing

Make sure to strictly adhere to the guidelines specified in `AGENTS.md` before making any commits or proposing pull requests.
