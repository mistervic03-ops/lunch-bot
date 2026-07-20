"""Small Socket Mode boundary for acknowledging Slack link buttons."""

from __future__ import annotations

from threading import Event
from typing import Any

from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.response import SocketModeResponse

from bapratustra.config import SlackServiceSettings


def acknowledge_interactive_request(client: Any, request: Any) -> bool:
    """Acknowledge interactive envelopes so Slack link buttons finish cleanly."""
    if request.type != "interactive":
        return False
    client.send_socket_mode_response(
        SocketModeResponse(envelope_id=request.envelope_id)
    )
    return True


def build_socket_mode_client(settings: SlackServiceSettings) -> SocketModeClient:
    client = SocketModeClient(
        app_token=settings.slack_app_token,
        web_client=WebClient(token=settings.slack_bot_token),
    )
    client.socket_mode_request_listeners.append(acknowledge_interactive_request)
    return client


def serve_socket_mode(settings: SlackServiceSettings) -> None:
    """Connect once; the SDK handles reconnects while systemd keeps the process up."""
    client = build_socket_mode_client(settings)
    client.connect()
    print("밥라투스트라 Slack 상호작용 서비스 연결 완료")
    Event().wait()
