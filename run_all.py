"""Run each agent server and start the Streamlit demo UI."""

import asyncio
import subprocess
import sys
import time
import signal
import httpx
import os
import threading
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_PYTHON = os.path.join(BASE_DIR, "labenv", "Scripts", "python.exe")
PYTHON_EXE = LOCAL_PYTHON if os.path.exists(LOCAL_PYTHON) else sys.executable

server_url = os.environ["SERVER_URL"]
servers = [
    {
        "name": "title_agent_server",
        "module": "title_agent.server:app",
        "port": os.environ["TITLE_AGENT_PORT"]
    },
    {
        "name": "outline_agent_server",
        "module": "outline_agent.server:app",
        "port": os.environ["OUTLINE_AGENT_PORT"]
    },
    {
        "name": "routing_agent_server",
        "module": "routing_agent.server:app",
        "port": os.environ["ROUTING_AGENT_PORT"]
    },
]

server_procs = []

async def wait_for_server_ready(server, timeout=30):
    async with httpx.AsyncClient() as client:
        start = time.time()
        while True:
            try:
                health_url = f"http://{server_url}:{server['port']}/health"
                r = await client.get(health_url, timeout=2)
                if r.status_code == 200:
                    print(f"[OK] {server['name']} is healthy and ready!")
                    return True
            except Exception:
                pass
            if time.time() - start > timeout:
                print(f"[ERROR] Timeout waiting for server health at {health_url}")
                return False
            await asyncio.sleep(1)

def stream_subprocess_output(process):
    while True:
        line = process.stdout.readline()
        if not line:
            break
        print(line.rstrip())


def run_web_ui():
    ui_cmd = [
        PYTHON_EXE,
        "-m",
        "streamlit",
        "run",
        "web_ui.py",
        "--server.address",
        server_url,
        "--server.port",
        "8501",
        "--server.headless",
        "true",
    ]

    print("[UI] Starting Streamlit UI on port 8501")
    process = subprocess.Popen(
        ui_cmd,
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        universal_newlines=True,
    )
    server_procs.append(process)

    thread = threading.Thread(target=stream_subprocess_output, args=(process,), daemon=True)
    thread.start()

    return process

async def main():
    print("[START] Starting server subprocesses...")
    for server in servers:
        cmd = [
            PYTHON_EXE,
            "-m",
            "uvicorn",
            server["module"],
            "--host",
            server_url,
            "--port",
            str(server["port"]),
            "--log-level",
            "info"
        ]
        
        print(f"[START] Starting {server['name']} on port {server['port']}")
        process = subprocess.Popen(
            cmd,
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            universal_newlines=True,
        )
        server_procs.append(process)

        thread = threading.Thread(target=stream_subprocess_output, args=(process,), daemon=True)
        thread.start()

        ready = await wait_for_server_ready(server)
        if not ready:
            print(f"[ERROR] Server '{server['name']}' failed to start, killing process...")
            process.kill()
            sys.exit(1)

    try:
        ui_process = run_web_ui()
        print(f"[OK] UI ready at http://{server_url}:8501")
        ui_process.wait()
    except Exception as e:
        print(f"[ERROR] UI stopped: {e}")
    finally:
        print("[STOP] Stopping subprocesses...")
        # Terminate the server subprocess gracefully
        for process in server_procs:
            if process.poll() is None:  # Still running
                if sys.platform == "win32":
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

if __name__ == "__main__":
    asyncio.run(main())
