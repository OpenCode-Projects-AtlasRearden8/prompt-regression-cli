import json

import pytest

from prompt_regression_cli.config import EndpointConfig
from prompt_regression_cli.errors import RequestError
from prompt_regression_cli.runner import ChatClient, parse_completion


def make_client(url, **kwargs):
    return ChatClient(EndpointConfig(base_url=url, model="mock-model", timeout=5, **kwargs))


class TestChatClient:
    def test_success_returns_content(self, mock_server):
        mock_server.default_content = "Sorry Sam, we can help."
        client = make_client(mock_server.base_url)
        assert client.complete([{"role": "user", "content": "hi"}]) == "Sorry Sam, we can help."

    def test_request_body_shape(self, mock_server):
        client = make_client(mock_server.base_url, api_key_env=None)
        client.complete([{"role": "user", "content": "hi"}])
        body = mock_server.last_request["body"]
        assert body["model"] == "mock-model"
        assert body["stream"] is False
        assert body["messages"][0]["content"] == "hi"
        assert "temperature" not in body

    def test_temperature_sent_when_set(self, mock_server):
        client = make_client(mock_server.base_url)
        client.endpoint.temperature = 0.4
        client.complete([{"role": "user", "content": "hi"}])
        assert mock_server.last_request["body"]["temperature"] == 0.4

    def test_url_hits_chat_completions(self, mock_server):
        client = make_client(mock_server.base_url)
        client.complete([{"role": "user", "content": "hi"}])
        assert mock_server.last_request["path"] == "/v1/chat/completions"

    def test_http_error_surfaces_status_and_body(self, mock_server):
        mock_server.next_error = (500, {"error": "internal"})
        client = make_client(mock_server.base_url)
        with pytest.raises(RequestError, match="HTTP 500"):
            client.complete([{"role": "user", "content": "hi"}])

    def test_connection_refused_hint(self, unused_port_factory):
        client = make_client(f"http://127.0.0.1:{unused_port_factory}/v1")
        with pytest.raises(RequestError, match="Ollama"):
            client.complete([{"role": "user", "content": "hi"}])

    def test_authorization_header_when_key_env_set(self, mock_server, monkeypatch):
        monkeypatch.setenv("SECRET_ENV_NAME", "env-only-key")
        endpoint = EndpointConfig(
            base_url=mock_server.base_url, model="mock-model", api_key_env="SECRET_ENV_NAME"
        )
        ChatClient(endpoint).complete([{"role": "user", "content": "hi"}])
        headers = {key.lower(): value for key, value in mock_server.last_request["headers"].items()}
        assert headers.get("authorization") == "Bearer env-only-key"
        body_text = json.dumps(mock_server.last_request["body"])
        assert "env-only-key" not in body_text

    def test_no_authorization_by_default(self, mock_server):
        make_client(mock_server.base_url).complete([{"role": "user", "content": "hi"}])
        headers = {key.lower(): value for key, value in mock_server.last_request["headers"].items()}
        assert "authorization" not in headers


class TestParseCompletion:
    def test_valid(self):
        raw = json.dumps({"choices": [{"message": {"role": "assistant", "content": "cut"}}]})
        assert parse_completion(raw, "url") == "cut"

    def test_no_choices(self):
        with pytest.raises(RequestError, match="no choices"):
            parse_completion(json.dumps({"choices": []}), "url")

    def test_no_content(self):
        with pytest.raises(RequestError, match="message.content"):
            parse_completion(json.dumps({"choices": [{"message": {}}]}), "url")

    def test_bad_json(self):
        with pytest.raises(RequestError, match="invalid JSON"):
            parse_completion("{not json", "url")
