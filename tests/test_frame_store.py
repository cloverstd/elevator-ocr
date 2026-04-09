import numpy as np

from app.config import Settings
from app.frame_store import FrameStore


async def test_frame_store_returns_jpeg() -> None:
    store = FrameStore(Settings())
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    await store.update(frame)

    payload = await store.get_jpeg()

    assert payload is not None
    assert payload[:2] == b"\xff\xd8"
