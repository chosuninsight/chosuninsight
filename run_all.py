import subprocess
import sys
import socket
from pathlib import Path

ROOT = Path(__file__).parent
PYTHON = ROOT / "venv" / "Scripts" / "python.exe"
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

def kill_port(port):
    result = subprocess.run(
        f'netstat -aon | findstr :{port}',
        shell=True, capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 5 and f':{port}' in parts[1]:
            pid = parts[4]
            if pid != '0':
                subprocess.run(f'taskkill /PID {pid} /F', shell=True, capture_output=True)
                print(f"Killed PID {pid} on port {port}")
                
def run_step(command, description, cwd=None):
    print(f"▶ {description} 시작...")
    process = subprocess.run(command, cwd=cwd, shell=True)
    if process.returncode != 0:
        print(f"❌ {description} 실패!")
        sys.exit(1)
    print(f"✅ {description} 완료.")

print("========================================")
print("[Chosun Insight] Starting servers...")
print("========================================")

run_step([f"{PYTHON}", "Update_date.py"], "데이터 수집 및 ChromaDB 빌드", cwd=ROOT)

kill_port(8000)

backend = subprocess.Popen(
    [str(PYTHON), "-m", "uvicorn", "main:app", "--reload", "--port", "8000"],
    cwd=BACKEND
)
print(f"Backend started (PID: {backend.pid})")

frontend = subprocess.Popen(
    ["npm", "run", "dev"],
    cwd=FRONTEND,
    shell=True
)
print(f"Frontend started (PID: {frontend.pid})")

print("\nBoth servers running. Press Ctrl+C to stop all.\n")

try:
    backend.wait()
    frontend.wait()
except KeyboardInterrupt:
    print("\nStopping servers...")
    backend.terminate()
    frontend.terminate()
