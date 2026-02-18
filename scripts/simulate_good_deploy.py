# Folder: firetiger-demo/scripts/simulate_good_deploy.py
# Reverts to fast mode. Run this if you want to manually reset.
# Normally the agent handles this automatically.

import subprocess
import requests
import time
import os

def simulate_good_deploy():
    print("\n" + "="*50)
    print("🔧 REVERTING TO FAST MODE")
    print("="*50)
    
    _update_env("USE_SLOW_QUERY", "false")
    print("✓ Switched back to fast query mode")
    
    subprocess.run(["git", "add", ".env"])
    subprocess.run([
        "git", "commit", "-m",
        "fix: revert N+1 query regression on checkout"
    ])
    
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True
    ).stdout.strip()
    
    print(f"✓ Committed fix: {sha}")
    
    print("\n📊 Verifying recovery...")
    latencies = []
    for i in range(10):
        start = time.time()
        try:
            requests.get("http://localhost:5000/checkout", timeout=5)
            latencies.append((time.time() - start) * 1000)
        except Exception:
            pass
        time.sleep(0.3)
    
    if latencies:
        avg = sum(latencies) / len(latencies)
        print(f"✓ /checkout now averaging {avg:.1f}ms")
        if avg < 100:
            print("✅ Recovery confirmed!")
        else:
            print("⚠️  Still slow - may need more time")


def _update_env(key: str, value: str):
    with open(".env", "r") as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            break
    with open(".env", "w") as f:
        f.writelines(lines)
    os.environ[key] = value


if __name__ == "__main__":
    simulate_good_deploy()