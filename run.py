#!/usr/bin/env python3
"""
NumbyAI cross-platform CLI — works on Windows, macOS, and Linux.

Usage:
    python run.py start          Start the full stack (venv, deps, migrate, build, serve)
    python run.py stop           Stop the backend server
    python run.py logs           Tail backend logs
    python run.py check          Run ruff + mypy + pytest
    python run.py setup-ollama   Install/verify Ollama and pull the default model
    python run.py test-e2e       Run end-to-end categorization test
    python run.py clear-db       Delete the SQLite database
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
SERVER_DIR = ROOT / "server"
WEB_DIR = ROOT / "web"
VENV_DIR = SERVER_DIR / ".venv"
LOG_DIR = SERVER_DIR / "logs"
LOG_FILE = LOG_DIR / "numbyai-backend.log"
PID_FILE = LOG_DIR / "server.pid"
REQUIREMENTS = SERVER_DIR / "requirements.txt"
DEV_REQUIREMENTS = SERVER_DIR / "requirements-dev.txt"
DB_FILE = SERVER_DIR / "finance_recon.db"

IS_WINDOWS = sys.platform == "win32"
OLLAMA_MODEL = "qwen3.5:9b"
OLLAMA_URL = "http://localhost:11434"
PORT = 8000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def venv_bin(name: str) -> Path:
    """Return the path to an executable inside the virtualenv."""
    if IS_WINDOWS:
        exe = VENV_DIR / "Scripts" / (name + ".exe")
        if exe.exists():
            return exe
        return VENV_DIR / "Scripts" / name
    return VENV_DIR / "bin" / name


def run(cmd: list[str], *, cwd: Path | None = None, check: bool = True,
        capture: bool = False, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run a command with consistent settings."""
    merged_env = {**os.environ, **(env or {})}
    return subprocess.run(
        cmd, cwd=cwd, check=check, text=True,
        capture_output=capture, env=merged_env,
    )


def banner(text: str) -> None:
    print(f"\n{'=' * 50}")
    print(f"  {text}")
    print(f"{'=' * 50}\n")


def step(n: int, text: str) -> None:
    print(f"Step {n}: {text}")


def ok(text: str) -> None:
    print(f"  [ok] {text}")


def warn(text: str) -> None:
    print(f"  [!!] {text}")


def fail(text: str) -> None:
    print(f"  [FAIL] {text}")
    sys.exit(1)


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def kill_port(port: int) -> bool:
    """Kill whatever is listening on *port*. Returns True if something was killed."""
    if IS_WINDOWS:
        return _kill_port_windows(port)
    return _kill_port_unix(port)


def _kill_port_unix(port: int) -> bool:
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, check=False,
        )
        pids = result.stdout.strip().split()
        for pid in pids:
            if pid:
                os.kill(int(pid), signal.SIGKILL)
        return bool(pids)
    except Exception:
        return False


def _kill_port_windows(port: int) -> bool:
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, check=False,
        )
        killed = False
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1]
                subprocess.run(
                    ["taskkill", "/F", "/PID", pid],
                    capture_output=True, check=False,
                )
                killed = True
        return killed
    except Exception:
        return False


def kill_by_pid_file() -> bool:
    """Kill the process recorded in the PID file."""
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        time.sleep(1)
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        PID_FILE.unlink(missing_ok=True)
        return True
    except (ValueError, OSError):
        PID_FILE.unlink(missing_ok=True)
        return False


# ---------------------------------------------------------------------------
# Ensure helpers (idempotent setup steps)
# ---------------------------------------------------------------------------
def ensure_venv() -> None:
    if not VENV_DIR.exists():
        print("Creating backend virtualenv...")
        run([sys.executable, "-m", "venv", str(VENV_DIR)])

    pip = venv_bin("pip")
    if not pip.exists():
        fail(f"Missing pip in virtualenv. Recreate with: {sys.executable} -m venv {VENV_DIR}")

    stamp = VENV_DIR / ".deps-installed"
    if not stamp.exists() or REQUIREMENTS.stat().st_mtime > stamp.stat().st_mtime:
        print("Installing backend dependencies...")
        run([str(pip), "install", "-r", str(REQUIREMENTS)])
        stamp.touch()
        ok("Backend dependencies installed")


def ensure_dev_deps() -> None:
    ensure_venv()
    if not DEV_REQUIREMENTS.exists():
        return
    stamp = VENV_DIR / ".dev-deps-installed"
    if not stamp.exists() or DEV_REQUIREMENTS.stat().st_mtime > stamp.stat().st_mtime:
        print("Installing Python dev tools...")
        run([str(venv_bin("pip")), "install", "-r", str(DEV_REQUIREMENTS)])
        stamp.touch()
        ok("Python dev tools installed")


def ensure_frontend() -> None:
    node_modules = WEB_DIR / "node_modules"
    lock_file = WEB_DIR / "package-lock.json"
    stamp = node_modules / ".deps-installed"
    needs_install = (
        not node_modules.exists()
        or (lock_file.exists() and (not stamp.exists() or lock_file.stat().st_mtime > stamp.stat().st_mtime))
    )
    if needs_install:
        print("Installing frontend dependencies...")
        run(["npm", "install"], cwd=WEB_DIR)
        stamp.touch()
        ok("Frontend dependencies installed")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_start() -> None:
    banner("Starting NumbyAI")

    step(1, "Ensuring Python virtualenv and dependencies...")
    ensure_venv()
    ok("Backend ready")

    step(2, "Ensuring frontend dependencies...")
    ensure_frontend()
    ok("Frontend deps ready")

    step(3, "Stopping any existing server...")
    kill_by_pid_file()
    kill_port(PORT)
    time.sleep(1)
    ok("Port clear")

    step(4, "Running database migrations...")
    alembic = venv_bin("alembic")
    result = run([str(alembic), "upgrade", "head"], cwd=SERVER_DIR, check=False, capture=True)
    if result.returncode == 0:
        ok("Database migrations applied")
    else:
        warn("Database migration check completed (may be first run)")

    step(5, "Building frontend app...")
    run(["npm", "run", "build"], cwd=WEB_DIR)
    ok("Frontend built")

    step(6, "Starting backend server on port 8000...")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_fh = open(LOG_FILE, "w")  # noqa: SIM115
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    uvicorn = venv_bin("uvicorn")
    proc = subprocess.Popen(
        [str(uvicorn), "app.main:asgi_app",
         "--host", "0.0.0.0", "--port", str(PORT), "--reload"],
        cwd=SERVER_DIR,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        env=env,
    )
    PID_FILE.write_text(str(proc.pid))
    ok(f"Server started (PID {proc.pid})")

    step(7, "Waiting for server to respond...")
    for _ in range(10):
        time.sleep(1)
        if port_in_use(PORT):
            ok("Backend health check passed")
            break
    else:
        warn("Backend not responding yet (check logs with: python run.py logs)")

    banner("NumbyAI is running!")
    print(f"  App:    http://localhost:{PORT}")
    print(f"  Health: http://localhost:{PORT}/health")
    print(f"  Logs:   python run.py logs")
    print(f"  Stop:   python run.py stop")
    print()

    print("Opening in browser...")
    webbrowser.open(f"http://localhost:{PORT}")


def cmd_stop() -> None:
    banner("Stopping NumbyAI")

    killed = kill_by_pid_file()
    if killed:
        ok("Server stopped via PID file")
    else:
        killed = kill_port(PORT)
        if killed:
            ok(f"Process on port {PORT} stopped")
        else:
            ok(f"No process found on port {PORT}")

    if not IS_WINDOWS:
        subprocess.run(
            ["pkill", "-f", "uvicorn app.main:asgi_app"],
            capture_output=True, check=False,
        )

    banner("All services stopped")


def cmd_logs() -> None:
    if not LOG_FILE.exists():
        fail(f"Log file not found: {LOG_FILE}")

    print(f"Tailing logs: {LOG_FILE}")
    print("(Press Ctrl+C to stop)\n")

    with open(LOG_FILE) as f:
        f.seek(0, 2)
        try:
            while True:
                line = f.readline()
                if line:
                    print(line, end="")
                else:
                    time.sleep(0.3)
        except KeyboardInterrupt:
            print("\nStopped tailing logs.")


def cmd_check() -> None:
    banner("Running Python quality checks")

    ensure_dev_deps()

    ruff = venv_bin("ruff")
    mypy = venv_bin("mypy")
    pytest = venv_bin("pytest")

    print("\n--- ruff check ---")
    run([str(ruff), "check", "app", "tests"], cwd=SERVER_DIR)
    print("\n--- mypy ---")
    run([str(mypy)], cwd=SERVER_DIR)
    print("\n--- pytest ---")
    run([str(pytest), "tests", "--cov=app", "--cov-report=term-missing"], cwd=SERVER_DIR)

    banner("All checks passed")


def cmd_setup_ollama() -> None:
    banner("Ollama Setup")
    import shutil
    import platform
    import urllib.request

    ollama_path = shutil.which("ollama")
    if ollama_path:
        ok(f"ollama binary found: {ollama_path}")
    else:
        system = platform.system()
        print("  ollama not found on PATH.\n")
        if system == "Darwin":
            print("  Install with:  brew install ollama")
        elif system == "Linux":
            print("  Install with:  curl -fsSL https://ollama.com/install.sh | sh")
        elif system == "Windows":
            print("  Install from:  https://ollama.com/download/windows")
            print("  Or via winget: winget install Ollama.Ollama")
        else:
            print(f"  Visit https://ollama.com/download for {system} instructions.")
        print("\n  After installing, re-run: python run.py setup-ollama")
        sys.exit(1)

    # Check if Ollama server is running
    try:
        urllib.request.urlopen(OLLAMA_URL, timeout=3)
        ok(f"Ollama server running at {OLLAMA_URL}")
    except Exception:
        print("  Starting ollama serve in background...")
        if IS_WINDOWS:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        time.sleep(3)
        try:
            urllib.request.urlopen(OLLAMA_URL, timeout=3)
            ok(f"Ollama server started at {OLLAMA_URL}")
        except Exception:
            fail("Failed to start Ollama server. Try running 'ollama serve' manually.")

    # Check if model is available
    result = run(["ollama", "list"], capture=True, check=False)
    if OLLAMA_MODEL in result.stdout:
        ok(f"Model {OLLAMA_MODEL} already available")
    else:
        print(f"  Pulling {OLLAMA_MODEL} (this may take a few minutes on first run)...")
        run(["ollama", "pull", OLLAMA_MODEL])
        ok(f"Model {OLLAMA_MODEL} pulled successfully")

    banner("Ollama ready")
    print(f"  URL:   {OLLAMA_URL}")
    print(f"  Model: {OLLAMA_MODEL}")


def cmd_test_e2e() -> None:
    ensure_venv()
    python = venv_bin("python")
    run([str(python), "tests/test_e2e_categorization.py"], cwd=SERVER_DIR)


def cmd_clear_db() -> None:
    if DB_FILE.exists():
        DB_FILE.unlink()
        ok("Database cleared")
    else:
        ok("No database file found")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
COMMANDS = {
    "start": cmd_start,
    "stop": cmd_stop,
    "logs": cmd_logs,
    "check": cmd_check,
    "setup-ollama": cmd_setup_ollama,
    "test-e2e": cmd_test_e2e,
    "clear-db": cmd_clear_db,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        print("Available commands:")
        for name in COMMANDS:
            print(f"  {name}")
        print()
        sys.exit(0)

    cmd_name = sys.argv[1]
    if cmd_name not in COMMANDS:
        print(f"Unknown command: {cmd_name}")
        print(f"Available: {', '.join(COMMANDS)}")
        sys.exit(1)

    COMMANDS[cmd_name]()


if __name__ == "__main__":
    main()
