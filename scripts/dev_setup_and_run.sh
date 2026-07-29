#!/usr/bin/env bash

set -Eeuo pipefail

export PATH="$HOME/.local/bin:$PATH"

# Design Note:
# This script bootstraps the local LIM-AI Copilot development stack using the
# real repository layout documented in docs/setup-guide.md and verified against
# the current codebase. It intentionally keeps the flow linear and explicit:
# check host prerequisites, prepare env files, install Poetry dependencies for
# server/ and daemon/, then start server, daemon, and widget with health checks.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$PROJECT_ROOT/.run"
LOG_DIR="$RUN_DIR/logs"
ROOT_ENV_FILE="$PROJECT_ROOT/.env"
DAEMON_CONFIG_FILE="$PROJECT_ROOT/daemon/config.yaml"
POETRY_BOOTSTRAP_VENV="$HOME/.local/share/poetry-bootstrap/venv"
WIDGET_PACKAGE_NAME="AI_LIM.wgt"
WIDGET_RUNTIME_DIR="$RUN_DIR/$WIDGET_PACKAGE_NAME"
OPENBOARD_WIDGET_TARGET_DIR=""

ACTION="${1:-all}"
PYTHON_BIN=""
TAIL_PID=""
SERVER_PID=""
DAEMON_PID=""
WIDGET_PID=""
SERVER_PORT="8000"
DAEMON_PORT="5000"
WIDGET_PORT="3000"

log() {
    printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

warn() {
    printf '[%s] WARNING: %s\n' "$(date '+%H:%M:%S')" "$*" >&2
}

fail() {
    printf '[%s] ERROR: %s\n' "$(date '+%H:%M:%S')" "$*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Usage:
  scripts/dev_setup_and_run.sh [all|setup|run]

Commands:
  all    Install prerequisites, prepare local config, install dependencies, and start the stack.
  setup  Install prerequisites and dependencies, but do not start services.
  run    Reuse existing dependencies/config and only start services.
EOF
}

ensure_directory_layout() {
    mkdir -p "$RUN_DIR" "$LOG_DIR"
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

choose_python() {
    local candidate=""
    for candidate in python3.12 python3.11 python3; do
        if command_exists "$candidate"; then
            if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
                PYTHON_BIN="$(command -v "$candidate")"
                log "Using Python interpreter: $PYTHON_BIN"
                return
            fi
        fi
    done
    fail "Python 3.11+ is required. Install Python 3.11 or 3.12 and run this script again."
}

detect_platform() {
    case "$(uname -s)" in
        Darwin)
            printf 'macos'
            ;;
        Linux)
            printf 'linux'
            ;;
        *)
            printf 'other'
            ;;
    esac
}

brew_package_installed() {
    brew list "$1" >/dev/null 2>&1
}

apt_package_installed() {
    dpkg -s "$1" >/dev/null 2>&1
}

install_system_dependencies() {
    local platform
    platform="$(detect_platform)"

    log "Checking documented host dependencies from docs/setup-guide.md"

    if [[ "$platform" == "macos" ]]; then
        if ! command_exists brew; then
            warn "Homebrew not found. Install Homebrew manually if you still need host packages like portaudio, tesseract, or node."
            return
        fi

        local brew_packages=()
        brew_package_installed portaudio || brew_packages+=("portaudio")
        brew_package_installed tesseract || brew_packages+=("tesseract")
        brew_package_installed node || brew_packages+=("node")

        if [[ ${#brew_packages[@]} -gt 0 ]]; then
            log "Installing missing Homebrew packages: ${brew_packages[*]}"
            brew install "${brew_packages[@]}"
        else
            log "Required Homebrew packages are already installed."
        fi
        return
    fi

    if [[ "$platform" == "linux" ]]; then
        if ! command_exists apt-get; then
            warn "Unsupported Linux package manager. Install portaudio19-dev, tesseract-ocr, nodejs, and npm manually if needed."
            return
        fi

        local apt_packages=()
        apt_package_installed portaudio19-dev || apt_packages+=("portaudio19-dev")
        apt_package_installed tesseract-ocr || apt_packages+=("tesseract-ocr")
        apt_package_installed nodejs || apt_packages+=("nodejs")
        apt_package_installed npm || apt_packages+=("npm")

        if [[ ${#apt_packages[@]} -gt 0 ]]; then
            log "Installing missing apt packages: ${apt_packages[*]}"
            sudo apt-get update
            sudo apt-get install -y "${apt_packages[@]}"
        else
            log "Required apt packages are already installed."
        fi
        return
    fi

    warn "Unsupported operating system for automatic system package installation. Continue manually if needed."
}

detect_openboard_user_widget_dir() {
    local platform
    platform="$(detect_platform)"

    case "$platform" in
        macos)
            printf '%s' "$HOME/Library/Application Support/OpenBoard/interactive content"
            ;;
        linux)
            printf '%s' "$HOME/.local/share/OpenBoard/interactive content"
            ;;
        *)
            return 1
            ;;
    esac
}

install_openboard() {
    local platform
    platform="$(detect_platform)"

    if [[ "$platform" == "macos" ]]; then
        if [[ -d "/Applications/OpenBoard.app" ]]; then
            log "OpenBoard is already installed in /Applications/OpenBoard.app"
            return
        fi

        if ! command_exists brew; then
            warn "Homebrew is required to install OpenBoard automatically on macOS. Install OpenBoard manually from https://www.openboard.ch/en/download"
            return
        fi

        log "Installing OpenBoard with Homebrew cask"
        brew install --cask openboard
        return
    fi

    if [[ "$platform" == "linux" ]]; then
        warn "Automatic OpenBoard installation is not implemented for Linux in this script. Install it manually from https://www.openboard.ch/en/download or your distro package."
        return
    fi

    warn "Automatic OpenBoard installation is not supported on this operating system."
}

ensure_poetry() {
    if command_exists poetry; then
        log "Poetry already available: $(command -v poetry)"
        return
    fi

    command_exists curl || fail "Poetry is missing and curl is not available for automatic installation."
    [[ -n "$PYTHON_BIN" ]] || fail "Internal error: choose_python must run before ensure_poetry."

    log "Poetry not found. Installing it with the official installer."
    if ! curl -sSL https://install.python-poetry.org | "$PYTHON_BIN" -; then
        warn "Official Poetry installer failed. Falling back to a dedicated Poetry virtualenv."
        mkdir -p "$(dirname "$POETRY_BOOTSTRAP_VENV")" "$HOME/.local/bin"
        rm -rf "$POETRY_BOOTSTRAP_VENV"
        "$PYTHON_BIN" -m venv "$POETRY_BOOTSTRAP_VENV"
        "$POETRY_BOOTSTRAP_VENV/bin/python" -m pip install --upgrade pip
        "$POETRY_BOOTSTRAP_VENV/bin/python" -m pip install poetry
        ln -sf "$POETRY_BOOTSTRAP_VENV/bin/poetry" "$HOME/.local/bin/poetry"
    fi

    if ! command_exists poetry && [[ -x "$HOME/.local/bin/poetry" ]]; then
        log "Poetry found in $HOME/.local/bin/poetry after installation."
    fi

    command_exists poetry || fail "Poetry installation failed even after the dedicated virtualenv fallback."
    log "Poetry installed successfully: $(command -v poetry)"
}

create_poetry_env() {
    local project_dir="$1"
    local venv_dir="$project_dir/.venv"
    log "Creating Poetry virtual environment in $project_dir before dependency installation"
    (
        cd "$project_dir"
        if [[ -x "$venv_dir/bin/python" ]]; then
            if "$venv_dir/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
                log "Reusing existing project virtual environment: $venv_dir"
                exit 0
            fi
            warn "Existing virtual environment uses an unsupported Python version. Recreating $venv_dir"
            rm -rf "$venv_dir"
        fi

        "$PYTHON_BIN" -m venv "$venv_dir"

        unset VIRTUAL_ENV
        unset CONDA_PREFIX
        unset PYTHONHOME
        unset PYTHONPATH

        # Register the freshly created in-project interpreter with Poetry explicitly.
        poetry env use "$venv_dir/bin/python"
    )
}

ensure_env_line() {
    local key="$1"
    local value="$2"
    if [[ ! -f "$ROOT_ENV_FILE" ]]; then
        touch "$ROOT_ENV_FILE"
    fi
    if ! grep -Eq "^${key}=" "$ROOT_ENV_FILE"; then
        printf '%s=%s\n' "$key" "$value" >>"$ROOT_ENV_FILE"
        log "Added missing env key '$key' to $(basename "$ROOT_ENV_FILE")."
    fi
}

prepare_root_env() {
    if [[ ! -f "$ROOT_ENV_FILE" ]]; then
        log "Creating root .env file for local development."
        cat >"$ROOT_ENV_FILE" <<'EOF'
API_KEY=lim_ai_local_dev_token
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=replace_me_with_real_provider_key
LLM_API_BASE=
SKETCHFAB_ACCESS_TOKEN=replace_me_with_real_sketchfab_token
WHISPER_MODEL_SIZE=base
WHISPER_DEVICE=cpu
RATE_LIMIT_PER_MINUTE=30
EOF
    else
        log "Reusing existing root .env file."
    fi

    ensure_env_line "API_KEY" "lim_ai_local_dev_token"
    ensure_env_line "LLM_MODEL" "gpt-4o-mini"
    ensure_env_line "LLM_API_KEY" "replace_me_with_real_provider_key"
    ensure_env_line "LLM_API_BASE" ""
    ensure_env_line "SKETCHFAB_ACCESS_TOKEN" "replace_me_with_real_sketchfab_token"
    ensure_env_line "WHISPER_MODEL_SIZE" "base"
    ensure_env_line "WHISPER_DEVICE" "cpu"
    ensure_env_line "RATE_LIMIT_PER_MINUTE" "30"

    set -a
    # shellcheck disable=SC1090
    source "$ROOT_ENV_FILE"
    set +a

    if [[ "${LLM_API_KEY:-}" == "replace_me_with_real_provider_key" ]]; then
        warn "LLM_API_KEY is still a placeholder. Concept maps, quiz, translation, and summaries will not work until you replace it."
    fi
    if [[ "${SKETCHFAB_ACCESS_TOKEN:-}" == "replace_me_with_real_sketchfab_token" ]]; then
        warn "SKETCHFAB_ACCESS_TOKEN is still a placeholder. 3D model lookup will fail until you replace it."
    fi
    if [[ "${WHISPER_DEVICE:-}" == "cpu" ]]; then
        log "WHISPER_DEVICE is set to 'cpu'. This is safe for development but may be slower than GPU."
    fi
}

yaml_quote() {
    printf "%s" "$1" | sed "s/'/''/g"
}

prepare_daemon_config() {
    [[ -n "${API_KEY:-}" ]] || fail "API_KEY is not loaded. Root .env preparation failed."

    local tmp_file=""
    local timestamp=""
    tmp_file="$(mktemp)"

    cat >"$tmp_file" <<EOF
remote_base_url: 'http://127.0.0.1:${SERVER_PORT}'
api_key: '$(yaml_quote "$API_KEY")'
disable_local_backup: false
EOF

    if [[ -f "$DAEMON_CONFIG_FILE" ]]; then
        if cmp -s "$tmp_file" "$DAEMON_CONFIG_FILE"; then
            rm -f "$tmp_file"
            log "Daemon config already aligned with local development defaults."
            return
        fi

        timestamp="$(date '+%Y%m%d-%H%M%S')"
        cp "$DAEMON_CONFIG_FILE" "$DAEMON_CONFIG_FILE.bak.$timestamp"
        warn "Existing daemon config backed up to $(basename "$DAEMON_CONFIG_FILE").bak.$timestamp"
    fi

    mv "$tmp_file" "$DAEMON_CONFIG_FILE"
    log "Daemon config written to $DAEMON_CONFIG_FILE"
}

install_poetry_project() {
    local project_dir="$1"
    local venv_dir="$project_dir/.venv"
    log "Installing Poetry dependencies in $project_dir"
    (
        cd "$project_dir"
        [[ -x "$venv_dir/bin/python" ]] || fail "Missing virtual environment in $venv_dir"

        unset VIRTUAL_ENV
        unset CONDA_PREFIX
        unset PYTHONHOME
        unset PYTHONPATH

        # Activate the project venv first so installation never falls back to the shell's Python.
        # shellcheck disable=SC1091
        source "$venv_dir/bin/activate"
        POETRY_VIRTUALENVS_CREATE=false poetry install --no-interaction
    )
}

create_project_environments() {
    create_poetry_env "$PROJECT_ROOT/server"
    create_poetry_env "$PROJECT_ROOT/daemon"
}

install_project_dependencies() {
    install_poetry_project "$PROJECT_ROOT/server"
    install_poetry_project "$PROJECT_ROOT/daemon"
}

port_is_available() {
    local port="$1"
    [[ -n "$PYTHON_BIN" ]] || fail "Internal error: choose_python must run before port checks."
    "$PYTHON_BIN" - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    sock.bind(("127.0.0.1", port))
except OSError:
    raise SystemExit(1)
finally:
    sock.close()
PY
}

find_available_port() {
    local preferred_port="$1"
    local service_name="$2"
    local port="$preferred_port"

    while ! port_is_available "$port"; do
        port=$((port + 1))
        if [[ "$port" -gt 65535 ]]; then
            fail "No free TCP port found for $service_name starting from $preferred_port."
        fi
    done

    if [[ "$port" != "$preferred_port" ]]; then
        warn "$service_name default port $preferred_port is busy. Using free port $port instead."
    fi

    printf '%s' "$port"
}

choose_runtime_ports() {
    SERVER_PORT="$(find_available_port 8000 "Remote server")"
    DAEMON_PORT="$(find_available_port 5000 "Local daemon")"
    WIDGET_PORT="$(find_available_port 3000 "Widget")"
}

prepare_runtime_widget() {
    [[ -n "$PYTHON_BIN" ]] || fail "Internal error: choose_python must run before widget preparation."

    rm -rf "$WIDGET_RUNTIME_DIR"
    mkdir -p "$WIDGET_RUNTIME_DIR"
    cp -R "$PROJECT_ROOT/widget/." "$WIDGET_RUNTIME_DIR/"

    "$PYTHON_BIN" - "$WIDGET_RUNTIME_DIR/index.html" "$DAEMON_PORT" <<'PY'
from pathlib import Path
import sys

index_path = Path(sys.argv[1])
daemon_port = sys.argv[2]
old_url = 'ws://127.0.0.1:5000/ws'
new_url = f'ws://127.0.0.1:{daemon_port}/ws'

content = index_path.read_text(encoding='utf-8')
if old_url not in content:
    raise SystemExit("Widget websocket URL marker not found in index.html.")

index_path.write_text(content.replace(old_url, new_url), encoding='utf-8')
PY

    "$PYTHON_BIN" - "$WIDGET_RUNTIME_DIR/config.xml" <<'PY'
from pathlib import Path
import sys

config_path = Path(sys.argv[1])
if config_path.exists() and config_path.read_text(encoding="utf-8").strip():
    raise SystemExit(0)

config_path.write_text(
    """<?xml version="1.0" encoding="UTF-8"?>
<widget xmlns="http://www.w3.org/ns/widgets"
        xmlns:ub="http://uniboard.mnemis.com/widgets"
        id="http://openboard.org/widgets/lim-ai-copilot"
        version="1.0.0"
        width="1100"
        height="760"
        ub:resizable="true"
        ub:transparent="false">
    <name>LIM AI Copilot</name>
    <author email="support@example.invalid">LIM-AI Copilot</author>
    <description>Hybrid OpenBoard widget for local daemon and remote AI services.</description>
    <icon src="icon.png"/>
    <content src="index.html"/>
</widget>
""",
    encoding="utf-8",
)
PY

    "$PYTHON_BIN" - "$WIDGET_RUNTIME_DIR/icon.png" <<'PY'
from pathlib import Path
import binascii
import struct
import sys
import zlib

icon_path = Path(sys.argv[1])
if icon_path.exists() and icon_path.stat().st_size > 0:
    raise SystemExit(0)

width = 128
height = 128
color = (0x89, 0xB4, 0xFA, 0xFF)
row = bytes([0]) + bytes(color) * width
raw = row * height
compressed = zlib.compress(raw, 9)

def chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack("!I", len(data))
        + chunk_type
        + data
        + struct.pack("!I", binascii.crc32(chunk_type + data) & 0xFFFFFFFF)
    )

png = b"\x89PNG\r\n\x1a\n"
png += chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 6, 0, 0, 0))
png += chunk(b"IDAT", compressed)
png += chunk(b"IEND", b"")
icon_path.write_bytes(png)
PY

    log "Prepared runtime widget copy in $WIDGET_RUNTIME_DIR with WebSocket URL ws://127.0.0.1:${DAEMON_PORT}/ws"
}

install_widget_in_openboard() {
    local openboard_widget_root=""

    openboard_widget_root="$(detect_openboard_user_widget_dir || true)"
    if [[ -z "$openboard_widget_root" ]]; then
        warn "OpenBoard widget auto-install is not supported on this operating system."
        return
    fi

    mkdir -p "$openboard_widget_root"
    OPENBOARD_WIDGET_TARGET_DIR="$openboard_widget_root/$WIDGET_PACKAGE_NAME"

    rm -rf "$OPENBOARD_WIDGET_TARGET_DIR"
    cp -R "$WIDGET_RUNTIME_DIR" "$OPENBOARD_WIDGET_TARGET_DIR"

    log "OpenBoard widget installed in $OPENBOARD_WIDGET_TARGET_DIR"
}

wait_for_url() {
    local name="$1"
    local url="$2"
    local log_file="$3"
    local attempt=0

    for attempt in $(seq 1 30); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            log "$name is ready at $url"
            return
        fi
        sleep 1
    done

    warn "$name failed to become ready. Recent log output:"
    if [[ -f "$log_file" ]]; then
        tail -n 50 "$log_file" >&2 || true
    fi
    fail "$name did not start correctly."
}

cleanup() {
    set +e

    if [[ -n "$TAIL_PID" ]] && kill -0 "$TAIL_PID" >/dev/null 2>&1; then
        kill "$TAIL_PID" >/dev/null 2>&1 || true
    fi

    if [[ -n "$WIDGET_PID" ]] && kill -0 "$WIDGET_PID" >/dev/null 2>&1; then
        kill "$WIDGET_PID" >/dev/null 2>&1 || true
    fi

    if [[ -n "$DAEMON_PID" ]] && kill -0 "$DAEMON_PID" >/dev/null 2>&1; then
        kill "$DAEMON_PID" >/dev/null 2>&1 || true
    fi

    if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" >/dev/null 2>&1; then
        kill "$SERVER_PID" >/dev/null 2>&1 || true
    fi
}

start_server() {
    local log_file="$LOG_DIR/server.log"
    : >"$log_file"
    log "Starting remote server on http://127.0.0.1:${SERVER_PORT}"
    (
        cd "$PROJECT_ROOT/server"
        # shellcheck disable=SC1091
        source ".venv/bin/activate"
        set -a
        # shellcheck disable=SC1090
        source "$ROOT_ENV_FILE"
        set +a
        exec uvicorn main:app --host 127.0.0.1 --port "$SERVER_PORT"
    ) >"$log_file" 2>&1 &
    SERVER_PID="$!"
    printf '%s\n' "$SERVER_PID" >"$RUN_DIR/server.pid"
    wait_for_url "Remote server" "http://127.0.0.1:${SERVER_PORT}/health" "$log_file"
}

start_daemon() {
    local log_file="$LOG_DIR/daemon.log"
    : >"$log_file"
    log "Starting local daemon on ws://127.0.0.1:${DAEMON_PORT}/ws"
    (
        cd "$PROJECT_ROOT/daemon"
        # shellcheck disable=SC1091
        source ".venv/bin/activate"
        exec uvicorn local_bridge:app --host 127.0.0.1 --port "$DAEMON_PORT"
    ) >"$log_file" 2>&1 &
    DAEMON_PID="$!"
    printf '%s\n' "$DAEMON_PID" >"$RUN_DIR/daemon.pid"
    wait_for_url "Local daemon" "http://127.0.0.1:${DAEMON_PORT}/setup" "$log_file"
}

start_widget() {
    local log_file="$LOG_DIR/widget.log"
    : >"$log_file"
    [[ -n "$PYTHON_BIN" ]] || fail "Internal error: choose_python must run before start_widget."
    log "Starting widget static server on http://127.0.0.1:${WIDGET_PORT}"
    (
        cd "$WIDGET_RUNTIME_DIR"
        exec "$PYTHON_BIN" -m http.server "$WIDGET_PORT" --bind 127.0.0.1
    ) >"$log_file" 2>&1 &
    WIDGET_PID="$!"
    printf '%s\n' "$WIDGET_PID" >"$RUN_DIR/widget.pid"
    wait_for_url "Widget" "http://127.0.0.1:${WIDGET_PORT}" "$log_file"
}

show_runtime_summary() {
    cat <<EOF

LIM-AI Copilot is running.

  Widget:        http://127.0.0.1:${WIDGET_PORT}
  Daemon setup:  http://127.0.0.1:${DAEMON_PORT}/setup
  Remote server: http://127.0.0.1:${SERVER_PORT}/health

Log files:
  $LOG_DIR/server.log
  $LOG_DIR/daemon.log
  $LOG_DIR/widget.log

Press Ctrl+C to stop all services.
EOF
}

follow_logs() {
    tail -n 20 -f \
        "$LOG_DIR/server.log" \
        "$LOG_DIR/daemon.log" \
        "$LOG_DIR/widget.log" &
    TAIL_PID="$!"
}

start_stack() {
    choose_runtime_ports
    prepare_daemon_config
    prepare_runtime_widget
    install_widget_in_openboard
    trap cleanup EXIT INT TERM
    start_server
    start_daemon
    start_widget
    show_runtime_summary
    follow_logs
    wait "$SERVER_PID" "$DAEMON_PID" "$WIDGET_PID"
}

run_setup() {
    ensure_directory_layout
    choose_python
    ensure_poetry
    prepare_root_env
    prepare_daemon_config
    install_system_dependencies
    install_openboard
    create_project_environments
    install_project_dependencies
    prepare_runtime_widget
    install_widget_in_openboard
    log "Setup completed successfully."
}

main() {
    case "$ACTION" in
        all)
            run_setup
            start_stack
            ;;
        setup)
            run_setup
            ;;
        run)
            ensure_directory_layout
            choose_python
            prepare_root_env
            prepare_daemon_config
            ensure_poetry
            start_stack
            ;;
        -h|--help|help)
            usage
            ;;
        *)
            usage
            exit 1
            ;;
    esac
}

main

