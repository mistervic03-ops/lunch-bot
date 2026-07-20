from __future__ import annotations

import json
import re
from pathlib import Path


MANIFEST_PATH = Path(__file__).parents[1] / "slack" / "app-manifest.json"


def test_slack_manifest_uses_only_approved_bot_scopes() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["oauth_config"]["scopes"] == {
        "bot": [
            "chat:write",
            "pins:write",
            "reactions:read",
            "reactions:write",
        ]
    }


def test_slack_manifest_enables_socket_mode_interactivity() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["display_information"] == {
        "name": "밥라투스트라",
        "description": "매일 오전 11시, 세 갈래 점심의 길을 제시합니다",
        "background_color": "#523078",
    }
    assert manifest["features"] == {
        "bot_user": {"display_name": "bapratustra", "always_online": False}
    }
    assert manifest["settings"] == {
        "interactivity": {"is_enabled": True},
        "org_deploy_enabled": False,
        "socket_mode_enabled": True,
        "token_rotation_enabled": False,
    }
    assert "chat:write.public" not in manifest["oauth_config"]["scopes"]["bot"]


def test_slack_manifest_contains_no_workspace_credentials_or_channel_ids() -> None:
    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")

    assert "xox" not in manifest_text
    assert "LUNCH_CHANNEL_ID" not in manifest_text
    assert "OPS_CHANNEL_ID" not in manifest_text


def test_bot_display_name_uses_only_slack_allowed_characters() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    display_name = manifest["features"]["bot_user"]["display_name"]

    assert len(display_name) <= 80
    assert re.fullmatch(r"[a-z0-9._-]+", display_name)
