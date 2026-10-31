import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class _MockError(Exception):
    def __init__(self, status, body):
        super().__init__(status)
        self.status = status
        self.body = body


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _reply(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self._reply(400, {"error": "bad json"})
            return
        server = self.server
        server.last_request = {
            "path": self.path,
            "headers": dict(self.headers.items()),
            "body": body,
        }
        server.requests.append(server.last_request)
        try:
            content = server.pick_content(body)
        except _MockError as exc:
            self._reply(exc.status, exc.body)
            return
        self._reply(
            200,
            {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "created": 1700000000,
                "model": (body or {}).get("model", "mock-model"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    def log_message(self, *_args, **_kwargs):
        return None


class MockOpenAIServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.default_content = "ok"
        self.rules = []
        self.requests = []
        self.last_request = None
        self.next_error = None

    def pick_content(self, body):
        if self.next_error is not None:
            status, payload = self.next_error
            self.next_error = None
            raise _MockError(status, payload)
        user_text = " ".join(
            str(message.get("content", ""))
            for message in body.get("messages", [])
            if message.get("role") == "user"
        )
        for marker, content in self.rules:
            if marker in user_text:
                return content
        return self.default_content

    @property
    def base_url(self):
        host, port = self.server_address[:2]
        return f"http://{host}:{port}/v1"


@pytest.fixture
def mock_server():
    server = MockOpenAIServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@pytest.fixture
def unused_port_factory():
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port
