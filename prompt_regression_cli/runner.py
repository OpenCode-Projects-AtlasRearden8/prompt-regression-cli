import json
import math
import urllib.error
import urllib.request

from .errors import RequestError


class ChatClient:
    def __init__(self, endpoint):
        self.endpoint = endpoint

    def chat_url(self):
        return self.endpoint.base_url + "/chat/completions"

    def complete(self, messages):
        body = {"model": self.endpoint.model, "messages": messages, "stream": False}
        temperature = self.endpoint.temperature
        if not math.isnan(temperature):
            body["temperature"] = temperature
        headers = {"Content-Type": "application/json"}
        api_key = self.endpoint.api_key
        if api_key:
            headers["Authorization"] = "Bearer " + api_key
        request = urllib.request.Request(
            self.chat_url(),
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.endpoint.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            excerpt = exc.read(2000).decode("utf-8", "replace")
            raise RequestError(
                f"{self.chat_url()} returned HTTP {exc.code}: {_compact(excerpt)}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RequestError(
                f"Could not reach {self.chat_url()} ({exc.reason}). "
                "Is the endpoint running? For Ollama: run 'ollama serve' "
                "and set base_url to http://localhost:11434/v1"
            ) from exc
        except TimeoutError as exc:
            raise RequestError(
                f"{self.chat_url()} timed out after {self.endpoint.timeout}s"
            ) from exc
        return parse_completion(raw, self.chat_url())


def parse_completion(raw, url):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RequestError(f"{url} returned invalid JSON: {exc}") from exc
    choices = data.get("choices") or []
    if not choices:
        raise RequestError(f"{url} response has no choices: {_compact(raw)}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if content is None:
        raise RequestError(f"{url} response has no message.content: {_compact(raw)}")
    return str(content)


def _compact(text, limit=500):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
