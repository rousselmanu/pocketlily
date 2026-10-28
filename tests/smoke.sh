#!/usr/bin/env bash
# Start the PocketLily image with the same hardening as docker-compose.yml and run the smoke test.
# Usage: tests/smoke.sh [image]        (default image: pocketlily:test)
set -euo pipefail
IMAGE="${1:-pocketlily:test}"
TOKEN="smoke-$RANDOM"
DATA="$(mktemp -d)"
NAME="pocketlily-smoke"

cleanup() {
  echo "--- server log ---"; docker logs "$NAME" 2>&1 | tail -n 40 || true
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  rm -rf "$DATA"
}
trap cleanup EXIT

docker run -d --name "$NAME" -p 8090:8090 \
  -e LILY_TOKEN="$TOKEN" -v "$DATA:/scores" --user "$(id -u):$(id -g)" \
  --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true \
  "$IMAGE" >/dev/null

for _ in $(seq 60); do
  curl -fs -o /dev/null http://localhost:8090/api/ping && break
  sleep 1
done

python3 "$(dirname "$0")/smoke.py" http://localhost:8090 "$TOKEN"
