from __future__ import annotations

import json
from pathlib import Path


MANIFEST_PATH = Path(__file__).parents[1] / "slack" / "app-manifest.json"


def test_slack_manifest_uses_only_approved_bot_scopes() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["oauth_config"]["scopes"] == {
        "bot": ["chat:write", "reactions:read", "reactions:write"]
    }


def test_slack_manifest_excludes_interactive_and_public_posting_features() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["features"] == {
        "bot_user": {"display_name": "밥괘", "always_online": False}
    }
    assert manifest["settings"] == {
        "org_deploy_enabled": False,
        "socket_mode_enabled": False,
        "token_rotation_enabled": False,
    }
    assert "chat:write.public" not in manifest["oauth_config"]["scopes"]["bot"]


def test_slack_manifest_contains_no_workspace_credentials_or_channel_ids() -> None:
    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")

    assert "xox" not in manifest_text
    assert "LUNCH_CHANNEL_ID" not in manifest_text
    assert "OPS_CHANNEL_ID" not in manifest_text

