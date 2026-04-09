from app.config import Settings


def test_settings_parse_rotated_roi() -> None:
    settings = Settings(
        floor_roi="10,20,30,40,12.5",
        direction_roi="50,60,70,80,-7",
    )

    assert settings.floor_roi.x == 10
    assert settings.floor_roi.h == 40
    assert settings.floor_roi.angle == 12.5
    assert settings.direction_roi.angle == -7.0
