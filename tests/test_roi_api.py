from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


async def test_roi_endpoint_returns_settings_values() -> None:
    settings = Settings(
        floor_roi="10,20,30,40",
        direction_roi="50,60,70,80",
    )
    app = create_app(settings, start_runtime=False)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/roi")

    assert response.status_code == 200
    payload = response.json()
    assert payload["floor_roi"] == {"x": 10, "y": 20, "w": 30, "h": 40, "angle": 0.0}
    assert payload["direction_roi"] == {"x": 50, "y": 60, "w": 70, "h": 80, "angle": 0.0}
    assert payload["frame_size"] is None
