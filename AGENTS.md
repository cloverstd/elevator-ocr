# Repository Guidelines

## Project Structure & Module Organization
Core application code lives in `app/`. Use `app/main.py` for FastAPI startup and route wiring, `app/rtsp.py` for stream ingestion, `app/recognition.py` for OCR and direction detection, `app/state.py` for debouncing and fan-out, and `app/metrics.py` / `app/mqtt.py` for external publishing. Shared models and settings are in `app/models.py` and `app/config.py`. The browser UI is a single embedded page in `app/web.py`. Tests live under `tests/` and mirror behavior by subsystem: `test_api.py`, `test_recognition.py`, and `test_state.py`.

## Build, Test, and Development Commands
- `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`: create a local dev environment.
- `.venv/bin/uvicorn app.main:app --reload`: run the API locally on `http://127.0.0.1:8000`.
- `.venv/bin/pytest -q`: run the full test suite.
- `docker compose up --build`: build the image and start the service with `.env`.

Set runtime configuration through `.env`; start from `.env.example`.

## Coding Style & Naming Conventions
Target Python 3.11. Use 4-space indentation and keep modules focused on one responsibility. Follow existing naming patterns: `snake_case` for functions and variables, `PascalCase` for classes, and short, descriptive module names such as `state.py` or `mqtt.py`. Prefer explicit typing on public functions and dataclasses. Keep FastAPI payloads and internal state models separate when their roles differ.

No formatter or linter is configured yet. Match the current style and keep imports grouped and stable.

## Testing Guidelines
Tests use `pytest` with `pytest-asyncio`. Name files `test_*.py` and test functions `test_*`. Add unit tests for normalization, state transitions, and interface contracts when touching OCR, debouncing, HTTP, SSE, MQTT, or metrics behavior. Run `.venv/bin/pytest -q` before submitting changes.

## Commit & Pull Request Guidelines
Git history is not available in this workspace, so use concise imperative commit messages, for example: `Add MQTT heartbeat publishing`. Keep one logical change per commit when practical.

For pull requests, include:
- a short summary of the behavior change
- any `.env` or deployment changes
- test results
- screenshots for UI changes at `/`

## Security & Configuration Tips
Do not commit `.env`, RTSP credentials, or broker passwords. Keep `ALLOWED_FLOORS`, `FLOOR_ROI`, and `DIRECTION_ROI` environment-specific. Validate with a real stream before production rollout because OCR accuracy depends heavily on ROI tuning and display contrast.
