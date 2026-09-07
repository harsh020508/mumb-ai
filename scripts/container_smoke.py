import subprocess
import sys
import time
import urllib.request

IMAGE_NAME = "mumb-ai-smoke"
CONTAINER_NAME = "mumb-ai-smoke-test"
PORT = 8085

def run(cmd, check=True):
    print(f"-> {cmd}")
    res = subprocess.run(cmd, shell=True, capture_output=False)
    if check and res.returncode != 0:
        print(f"Command failed with exit code {res.returncode}")
        sys.exit(res.returncode)
    return res.returncode

def cleanup():
    print("Cleaning up container...")
    run(f"docker stop {CONTAINER_NAME}", check=False)
    run(f"docker rm {CONTAINER_NAME}", check=False)


def check_url(url, expected_str=None):
    print(f"Checking {url}...")
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status != 200:
            raise RuntimeError(f"{url} returned HTTP {resp.status}")
        body = resp.read().decode("utf-8")
        if expected_str and expected_str not in body:
            raise RuntimeError(f"{url} response did not contain '{expected_str}'")
        print(f"  OK (HTTP {resp.status})")


def main():
    try:
        cleanup()
        print("Building Docker image...")
        run(f"docker build -t {IMAGE_NAME} .")

        print("Starting container...")
        run(f"docker run -d --name {CONTAINER_NAME} -p {PORT}:8080 {IMAGE_NAME}")

        print("Waiting for container to initialize...")
        time.sleep(5)

        base = f"http://127.0.0.1:{PORT}"
        check_url(f"{base}/health", "healthy")
        check_url(f"{base}/ready", "ready")
        check_url(f"{base}/api", "mumb-ai")
        check_url(f"{base}/", "<html")

        print("\nAll container smoke checks passed successfully!")
    except Exception as e:
        print(f"\nContainer smoke test failed: {e}")
        subprocess.run(f"docker logs {CONTAINER_NAME}", shell=True)
        cleanup()
        sys.exit(1)
    else:
        cleanup()

if __name__ == "__main__":
    main()
