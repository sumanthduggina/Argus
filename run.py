# Root folder: firetiger-demo/run.py
# Use this instead of run.sh on Windows
# Run with: python run.py

import subprocess
import sys
import os
import time

# Create logs folder if it doesn't exist
os.makedirs("logs", exist_ok=True)

print("Firetiger Demo Starting...")

# Start Flask app
print("Starting Flask app on port 5000...")
flask_proc = subprocess.Popen(
    [sys.executable, "-m", "app.main"],
    stdout=open("logs/app.log", "w"),
    stderr=subprocess.STDOUT
)

# Save PID
with open("app.pid", "w") as f:
    f.write(str(flask_proc.pid))

print(f"Flask app started (PID: {flask_proc.pid})")

# Wait for Flask to be ready
time.sleep(3)

# Start agent
print("Starting agent...")
agent_proc = subprocess.Popen(
    [sys.executable, "main_agent.py"],
    stdout=open("logs/agent.log", "w"),
    stderr=subprocess.STDOUT
)

# Save PID
with open("agent.pid", "w") as f:
    f.write(str(agent_proc.pid))

print(f"Agent started (PID: {agent_proc.pid})")

print("")
print("System running!")
print("  Flask app:  http://localhost:5000/health")
print("  Collector:  http://localhost:8001/health")
print("")
print("Next steps:")
print("  1. python scripts/seed_db.py")
print("  2. python scripts/run_load.py  (new terminal)")
print("  3. python scripts/simulate_bad_deploy.py  (to trigger demo)")
print("")
print("Press Ctrl+C to stop everything")

# Keep running and watch both processes
try:
    while True:
        time.sleep(1)
        
        # Restart if crashed
        if flask_proc.poll() is not None:
            print("Flask app crashed - restarting...")
            flask_proc = subprocess.Popen(
                [sys.executable, "-m", "app.main"],
                stdout=open("logs/app.log", "a"),
                stderr=subprocess.STDOUT
            )
        
        if agent_proc.poll() is not None:
            print("Agent crashed - restarting...")
            agent_proc = subprocess.Popen(
                [sys.executable, "main_agent.py"],
                stdout=open("logs/agent.log", "a"),
                stderr=subprocess.STDOUT
            )

except KeyboardInterrupt:
    print("\nShutting down...")
    flask_proc.terminate()
    agent_proc.terminate()
    print("Stopped.")