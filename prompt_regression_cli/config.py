import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .errors import ConfigError

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_TIMEOUT = 120
DEFAULT_REPORTS_DIR = "reports"

_VALID_CHECK_KEYS = (
    "equals",
    "contains",
    "contains_all",
    "contains_any",
    "not_contains",
    "regex",
    "starts_with",
    "ends_with",
    "min_words",
    "max_words",
)


@dataclass
class EndpointConfig:
    base_url: str = DEFAULT_BASE_URL
    model: str = ""
    api_key_env: str = ""
    timeout: int = DEFAULT_TIMEOUT
    temperature: float = float("nan")

    @property
    def api_key(self):
        if not self.api_key_env:
            return None
        value = os.environ.get(self.api_key_env, "")
        if not value:
            raise ConfigError(
                f"Environment variable '{self.api_key_env}' is not set. The config "
                f"file never stores API keys; set the variable before running, e.g. "
                f"export {self.api_key_env}=sk-..."
            )
        return value


@dataclass
class Config:
    path: Path = None
    root: Path = None
    endpoint: EndpointConfig = field(default_factory=EndpointConfig)
    variants: dict = field(default_factory=dict)
    case_files: list = field(default_factory=list)
    reports_dir: Path = None


def _require_mapping(value, what):
    if not isinstance(value, dict):
        raise ConfigError(f"{what} must be a mapping")
    return value


def _parse_endpoint(data, config_dir):
    endpoint = _require_mapping(data.get("endpoint") or {}, "'endpoint'")
    base_url = str(endpoint.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
    model = endpoint.get("model")
    if not model:
        raise ConfigError("'endpoint.model' is required in the config file")
    timeout = int(endpoint.get("timeout", DEFAULT_TIMEOUT))
    temperature = float("nan")
    if "temperature" in endpoint and endpoint["temperature"] is not None:
        temperature = float(endpoint["temperature"])
    return EndpointConfig(
        base_url=base_url,
        model=str(model),
        api_key_env=str(endpoint.get("api_key_env") or ""),
        timeout=timeout,
        temperature=temperature,
    )


def load_config(path):
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Could not parse YAML config {path}: {exc}")
    data = _require_mapping(data, f"Config file {path}")

    config = Config(path=path, root=path.parent)
    config.endpoint = _parse_endpoint(data, path.parent)

    variants = _require_mapping(data.get("variants") or {}, "'variants'")
    if not variants:
        raise ConfigError("No prompt variants defined. Add a 'variants' mapping of name -> directory")
    config.variants = {str(name): Path(str(directory)) for name, directory in variants.items()}

    cases = data.get("cases")
    if isinstance(cases, (str, Path)):
        cases = [cases]
    if not cases:
        raise ConfigError("No test cases defined. Add a 'cases' list of YAML files")
    config.case_files = [path.parent / Path(str(item)) for item in cases]
    for case_file in config.case_files:
        if not case_file.is_file():
            raise ConfigError(f"Test case file not found: {case_file}")

    reports_dir_name = str(data.get("reports_dir") or DEFAULT_REPORTS_DIR)
    config.reports_dir = path.parent / reports_dir_name
    return config
