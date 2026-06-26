"""Run the AI Personal University Assistant locally."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import threading
import time

import httpx

from config.settings import BASE_DIR, load_environment


LOCAL_PYTHON = BASE_DIR / "labenv" / "Scripts" / "python.exe"
PYTHON_EXE = str(LOCAL_PYTHON) if LOCAL_PYTHON.exists() else sys.executable
REQUEST_TIMEOUT_SECONDS = 2
STARTUP_TIMEOUT_SECONDS = 30

load_environment()

SERVER_URL = os.getenv("SERVER_URL", "localhost")
SERVERS = [
    {
        "name": "university_assistant_server",
        "module": "agents.title_agent.server:app",
        "port": os.getenv("TITLE_AGENT_PORT", "10007"),
    },
    {
        "name": "outline_agent_server",
        "module": "agents.outline_agent.server:app",
        "port": os.getenv("OUTLINE_AGENT_PORT", "10008"),
    },
    {
        "name": "routing_agent_server",
        "module": "agents.routing_agent.server:app",
        "port": os.getenv("ROUTING_AGENT_PORT", "10009"),
    },
]

server_processes: list[subprocess.Popen[str]] = []


async def wait_for_server_ready(server: dict[str, str], timeout: int = STARTUP_TIMEOUT_SECONDS) -> bool:
    async with httpx.AsyncClient() as client:
        start = time.time()
        health_url = f"http://{SERVER_URL}:{server['port']}/health"
        while time.time() - start <= timeout:
            try:
                response = await client.get(health_url, timeout=REQUEST_TIMEOUT_SECONDS)
                if response.status_code == 200:
                    print(f"[OK] {server['name']} is ready at {health_url}")
                    return True
            except Exception:
                pass
            await asyncio.sleep(1)

    print(f"[ERROR] Timeout waiting for {server['name']} at {health_url}")
    return False


def stream_subprocess_output(process: subprocess.Popen[str]) -> None:
    if process.stdout is None:
        return

    for line in process.stdout:
        print(line.rstrip())


def start_process(command: list[str]) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        command,
        cwd=BASE_DIR,
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        universal_newlines=True,
    )
    server_processes.append(process)
    thread = threading.Thread(target=stream_subprocess_output, args=(process,), daemon=True)
    thread.start()
    return process


def start_web_ui() -> subprocess.Popen[str]:
    command = [
        PYTHON_EXE,
        "-m",
        "streamlit",
        "run",
        "ui/app.py",
        "--server.address",
        SERVER_URL,
        "--server.port",
        "8501",
        "--server.headless",
        "true",
    ]
    print("[START] Starting Streamlit UI on port 8501")
    return start_process(command)


async def main() -> None:
    print("[START] Starting AI Personal University Assistant")
    for server in SERVERS:
        command = [
            PYTHON_EXE,
            "-m",
            "uvicorn",
            server["module"],
            "--host",
            SERVER_URL,
            "--port",
            str(server["port"]),
            "--log-level",
            "info",
        ]
        print(f"[START] Starting {server['name']} on port {server['port']}")
        process = start_process(command)
        if not await wait_for_server_ready(server):
            process.kill()
            raise SystemExit(1)

    try:
        ui_process = start_web_ui()
        print(f"[OK] UI ready at http://{SERVER_URL}:8501")
        ui_process.wait()
    finally:
        stop_processes()


def stop_processes() -> None:
    print("[STOP] Stopping subprocesses")
    for process in server_processes:
        if process.poll() is not None:
            continue

        if sys.platform == "win32":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
