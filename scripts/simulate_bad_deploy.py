# Folder: firetiger-demo/scripts/simulate_bad_deploy.py
# Simulates a bad commit being deployed.
# Run this on camera to trigger the full investigation chain.

import subprocess
import requests
import time
import threading
import os

def simulate_bad_deploy():
    print("\n" + "="*50)
    print("🚀 SIMULATING BAD DEPLOY")
    print("="*50)
    
    # Switch to slow query mode
    _update_env("USE_SLOW_QUERY", "true")
    print("✓ Switched to slow query mode (N+1 enabled)")
    
    # Make a fake commit so git diff shows something
    with open("app/db.py", "r") as f:
        content = f.read()
    
    # Add a comment that will show in git diff
    bad_comment = "\n# TODO: optimize this loop - added by refactor branch\n"
    if bad_comment not in content:
        with open("app/db.py", "a") as f:
            f.write(bad_comment)
    
    subprocess.run(["git", "add", "app/db.py", ".env"])
    result = subprocess.run(
        ["git", "commit", "-m", 
         "refactor: optimize checkout query performance"],
        capture_output=True, text=True
    )
    
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True
    ).stdout.strip()
    
    print(f"✓ Committed: {sha}")
    print(f"✓ Message: 'refactor: optimize checkout query performance'")
    
    # Notify collector about the deploy
    try:
        requests.post(
            "http://localhost:8001/deploy",
            json={"commit_sha": sha},
            timeout=2
        )
    except Exception:
        pass
    
    # Generate traffic to make regression visible immediately
    print("\n📊 Generating traffic to expose regression...")
    
    def send_traffic():
        for i in range(30):
            try:
                requests.get(
                    "http://localhost:5000/checkout",
                    headers={
                        "X-User-ID": f"user-{i % 10}",
                        "X-Session-ID": f"session-{i}"
                    },
                    timeout=10
                )
            except Exception:
                pass
            time.sleep(0.5)
    
    traffic_thread = threading.Thread(target=send_traffic)
    traffic_thread.start()
    
    print(f"\n⏳ Detector will fire in ~30 seconds...")
    print(f"   Watch the terminal for: 🚨 REGRESSION CONFIRMED")
    print(f"   Then watch for the GitHub PR and Slack message\n")


def _update_env(key: str, value: str):
    """Update a key in .env file"""
    env_path = ".env"
    
    with open(env_path, "r") as f:
        lines = f.readlines()
    
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            updated = True
            break
    
    if not updated:
        lines.append(f"{key}={value}\n")
    
    with open(env_path, "w") as f:
        f.writelines(lines)
    
    # Also update os.environ for running process
    os.environ[key] = value


if __name__ == "__main__":
    simulate_bad_deploy()