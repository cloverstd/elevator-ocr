from app.config import Settings


def test_rtsp_transport_defaults_to_tcp() -> None:
    settings = Settings()
    assert settings.rtsp_transport == "tcp"


def test_rtsp_transport_accepts_udp() -> None:
    settings = Settings(rtsp_transport="udp")
    assert settings.rtsp_transport == "udp"


def test_rtsp_flush_frames_configurable() -> None:
    settings = Settings(rtsp_flush_frames=12)
    assert settings.rtsp_flush_frames == 12
