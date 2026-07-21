from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_systemd_units_use_bapratustra_identifiers() -> None:
    service = (ROOT / "deploy" / "bapratustra.service").read_text(encoding="utf-8")
    timer = (ROOT / "deploy" / "bapratustra.timer").read_text(encoding="utf-8")
    failure_service = (
        ROOT / "deploy" / "bapratustra-failure@.service"
    ).read_text(encoding="utf-8")
    slack_service = (
        ROOT / "deploy" / "bapratustra-slack.service"
    ).read_text(encoding="utf-8")
    leaderboard_service = (
        ROOT / "deploy" / "bapratustra-leaderboard.service"
    ).read_text(encoding="utf-8")
    alpha_service = (
        ROOT / "deploy" / "bapratustra-alpha.service"
    ).read_text(encoding="utf-8")
    alpha_backup_service = (
        ROOT / "deploy" / "bapratustra-alpha-backup.service"
    ).read_text(encoding="utf-8")
    alpha_backup_timer = (
        ROOT / "deploy" / "bapratustra-alpha-backup.timer"
    ).read_text(encoding="utf-8")

    assert "User=bapratustra" in service
    assert "Group=bapratustra" in service
    assert "WorkingDirectory=/opt/bapratustra" in service
    assert "EnvironmentFile=/etc/bapratustra/bapratustra.env" in service
    assert "python -m bapratustra --run-daily" in service
    assert "OnFailure=bapratustra-failure@%n.service" in service
    assert "TimeoutStartSec=120" in service
    assert "Unit=bapratustra.service" in timer
    assert "--notify-systemd-failure %i" in failure_service
    assert "TimeoutStartSec=60" in failure_service
    assert "python -m bapratustra --run-slack-service" in slack_service
    assert "Restart=on-failure" in slack_service
    assert "WantedBy=multi-user.target" in slack_service
    assert "uvicorn bapratustra.web:create_app --factory" in leaderboard_service
    assert "--host 0.0.0.0 --port 8030 --workers 1" in leaderboard_service
    assert "Restart=on-failure" in leaderboard_service
    assert "Environment=PYTHON_DOTENV_DISABLED=1" in leaderboard_service
    assert "UnsetEnvironment=SLACK_BOT_TOKEN SLACK_APP_TOKEN" in leaderboard_service
    assert "BAPRATUSTRA_LEADERBOARD_URL" in leaderboard_service
    assert "uvicorn bapratustra.alpha_web:create_app --factory" in alpha_service
    assert "--host 0.0.0.0 --port 8031 --workers 1" in alpha_service
    assert "Restart=on-failure" in alpha_service
    assert "python -m bapratustra --backup-alpha" in alpha_backup_service
    assert "OnFailure=bapratustra-failure@%n.service" in alpha_backup_service
    assert "OnCalendar=*-*-* 03:30:00 Asia/Seoul" in alpha_backup_timer
    assert "Persistent=true" in alpha_backup_timer
    assert "Unit=bapratustra-alpha-backup.service" in alpha_backup_timer
    assert not (ROOT / "deploy" / "babgwe.service").exists()
    assert not (ROOT / "deploy" / "babgwe.timer").exists()


def test_example_environment_uses_new_timezone_name() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "BAPRATUSTRA_TIMEZONE=Asia/Seoul" in example
    assert "SLACK_APP_TOKEN=xapp-replace-me" in example
    assert "BABGWE_TIMEZONE" not in example
