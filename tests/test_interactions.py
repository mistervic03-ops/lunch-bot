from types import SimpleNamespace
from unittest.mock import MagicMock

import bapratustra.interactions as interactions
from bapratustra.config import SlackServiceSettings
from bapratustra.interactions import acknowledge_interactive_request


def test_acknowledge_interactive_request_sends_empty_envelope_ack() -> None:
    client = MagicMock()
    request = SimpleNamespace(type="interactive", envelope_id="env-123")

    handled = acknowledge_interactive_request(client, request)

    assert handled is True
    response = client.send_socket_mode_response.call_args.args[0]
    assert response.envelope_id == "env-123"
    assert response.payload is None


def test_acknowledge_interactive_request_ignores_other_envelopes() -> None:
    client = MagicMock()
    request = SimpleNamespace(type="events_api", envelope_id="env-123")

    handled = acknowledge_interactive_request(client, request)

    assert handled is False
    client.send_socket_mode_response.assert_not_called()


def test_build_socket_mode_client_uses_both_tokens_and_registers_ack(
    monkeypatch,
) -> None:
    web_client = object()
    socket_client = SimpleNamespace(socket_mode_request_listeners=[])
    socket_factory = MagicMock(return_value=socket_client)
    monkeypatch.setattr(
        interactions, "WebClient", MagicMock(return_value=web_client)
    )
    monkeypatch.setattr(interactions, "SocketModeClient", socket_factory)

    result = interactions.build_socket_mode_client(
        SlackServiceSettings("xapp-test", "xoxb-test")
    )

    assert result is socket_client
    interactions.WebClient.assert_called_once_with(token="xoxb-test")
    socket_factory.assert_called_once_with(
        app_token="xapp-test", web_client=web_client
    )
    assert socket_client.socket_mode_request_listeners == [
        acknowledge_interactive_request
    ]
