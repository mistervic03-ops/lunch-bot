from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_systemd_units_use_bapratustra_identifiers() -> None:
    service = (ROOT / "deploy" / "bapratustra.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy" / "bapratustra.timer").read_text(encoding="utf-8")

    assert "User=bapratustra" in service
    assert "Group=bapratustra" in service
    assert "WorkingDirectory=/opt/bapratustra" in service
    assert "EnvironmentFile=/etc/bapratustra/bapratustra.env" in service
    assert "python -m bapratustra --run-daily" in service
    assert "Unit=bapratustra.service" in timer
    assert not (ROOT / "deploy" / "babgwe.service").exists()
    assert not (ROOT / "deploy" / "babgwe.timer").exists()


def test_example_environment_uses_new_timezone_name() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "BAPRATUSTRA_TIMEZONE=Asia/Seoul" in example
    assert "BABGWE_TIMEZONE" not in example
