# Elevator OCR

Single-service RTSP elevator floor recognition with OCR, Prometheus, MQTT, HTTP APIs, and a simple realtime web page.

## Features

- Reads one RTSP stream and samples frames on a fixed interval
- OCR on a configurable floor ROI
- Direction detection on a configurable arrow ROI
- Debounced state transitions to avoid noisy jumps
- Publishes state to HTTP, SSE, MQTT, and Prometheus
- Serves a lightweight dashboard page at `/`

## Quick start

1. Copy `.env.example` to `.env` and adjust:
   - `RTSP_URL`
   - `FLOOR_ROI`
   - `DIRECTION_ROI`
   - `ALLOWED_FLOORS`
   - `MQTT_BROKER_URL`
   - `MQTT_TOPIC_STATE`
2. Start the service:

```bash
docker compose up --build
```

3. Open:
   - `http://localhost:8000/`
   - `http://localhost:8000/api/v1/state`
   - `http://localhost:8000/metrics`

## Development workflow

For local development, build the image once, then use the dev compose override with bind mounts and `uvicorn --reload`.

Initial build:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d
```

After that, most Python/UI changes do not need a rebuild:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

Useful dev commands:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f
docker compose -f docker-compose.yml -f docker-compose.dev.yml restart elevator-ocr
```

Rebuild is only needed when dependencies or the base image change, for example after editing `pyproject.toml` or `Dockerfile`.

## CI and image publishing

- GitHub Actions `Test` runs `ruff check .` and `pytest -q` on `push` and `pull_request`
- Every push to `main` publishes a preview image to GHCR:
  - `ghcr.io/cloverstd/elevator-ocr:main`
  - `ghcr.io/cloverstd/elevator-ocr:test`
  - `ghcr.io/cloverstd/elevator-ocr:test-<run_number>`
  - `ghcr.io/cloverstd/elevator-ocr:sha-<commit>`
- Pushing a tag like `v1.2.3` triggers the release workflow:
  - publishes release images to GHCR
  - creates a GitHub Release
  - tags include `v1.2.3`, `1.2.3`, `1.2`, `1`

## State payload

HTTP, SSE, and MQTT use the same JSON payload:

```json
{
  "elevator_id": "elevator-1",
  "floor": "12",
  "direction": "up",
  "source_ts": "2026-04-09T09:00:00Z",
  "published_ts": "2026-04-09T09:00:01Z",
  "stream_connected": true,
  "ocr_confidence": 95.5
}
```

## MQTT

- Topic: `MQTT_TOPIC_STATE`
- Payload: same as `/api/v1/state`
- Retain: enabled
- Publish policy: on stable state changes plus periodic heartbeats

## Prometheus metrics

- `elevator_stream_connected{elevator_id}`
- `elevator_current_floor{elevator_id,floor}`
- `elevator_direction{elevator_id,direction}`
- `elevator_last_update_unixtime{elevator_id}`
- `elevator_ocr_success_total{elevator_id}`
- `elevator_ocr_failure_total{elevator_id}`
- `elevator_state_changes_total{elevator_id}`

## ROI tuning

Use coordinates in `x,y,w,h` format. The floor ROI should tightly cover only the floor digits. The direction ROI should tightly cover only the arrow indicator.

If OCR is unstable:

- tighten the ROI to remove reflections and decorations
- keep `ALLOWED_FLOORS` limited to real floors only
- raise `STABLE_FRAMES`
- verify the displayed digits have enough contrast after thresholding
