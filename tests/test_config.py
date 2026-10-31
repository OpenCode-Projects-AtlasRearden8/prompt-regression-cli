import pytest

from prompt_regression_cli.config import load_config
from prompt_regression_cli.errors import ConfigError

FULL_CONFIG = """
endpoint:
  base_url: http://localhost:11434/v1
  model: llama3.2
  api_key_env: MY_KEY_ENV
  timeout: 42
  temperature: 0.1
variants:
  demo: prompts/demo
cases:
  - cases/demo.yaml
reports_dir: saved-runs
"""


@pytest.fixture
def project(tmp_path):
    (tmp_path / "prompts" / "demo").mkdir(parents=True)
    (tmp_path / "prompts" / "demo" / "v1.md").write_text("hi {name}")
    (tmp_path / "cases").mkdir()
    (tmp_path / "cases" / "demo.yaml").write_text("- id: c1\n  variant: demo\n  expect:\n    max_words: 50\n")
    config = tmp_path / "suite.yaml"
    config.write_text(FULL_CONFIG)
    return config


class TestLoadConfig:
    def test_full(self, project, tmp_path):
        config = load_config(project)
        assert config.endpoint.base_url == "http://localhost:11434/v1"
        assert config.endpoint.model == "llama3.2"
        assert config.endpoint.api_key_env == "MY_KEY_ENV"
        assert config.endpoint.timeout == 42
        assert config.endpoint.temperature == 0.1
        assert config.root == tmp_path
        assert set(config.variants) == {"demo"}
        assert config.case_files[0].name == "demo.yaml"
        assert config.reports_dir.name == "saved-runs"

    def test_defaults(self, tmp_path):
        config_file = tmp_path / "c.yaml"
        (tmp_path / "prompts" / "a").mkdir(parents=True)
        (tmp_path / "prompts" / "a" / "v1.md").write_text("x")
        (tmp_path / "cases").mkdir()
        (tmp_path / "cases" / "x.yaml").write_text("- id: c\n  variant: a\n  expect:\n    max_words: 5\n")
        config_file.write_text("endpoint:\n  model: m\nvariants:\n  a: prompts/a\ncases:\n  - cases/x.yaml\n")
        config = load_config(config_file)
        assert config.endpoint.base_url == "http://localhost:11434/v1"
        assert config.endpoint.timeout == 120
        assert config.reports_dir.name == "reports"
        assert config.endpoint.api_key_env == ""

    def test_missing_file(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "nope.yaml")

    def test_model_required(self, tmp_path):
        config_file = tmp_path / "c.yaml"
        config_file.write_text("variants:\n  a: prompts/a\ncases:\n  - cases/x.yaml\n")
        with pytest.raises(ConfigError, match="model"):
            load_config(config_file)

    def test_missing_case_file(self, project):
        (project.parent / "cases" / "demo.yaml").unlink()
        with pytest.raises(ConfigError, match="Test case file not found"):
            load_config(project)

    def test_api_key_from_env_only(self, project, monkeypatch):
        config = load_config(project)
        with pytest.raises(ConfigError, match="MY_KEY_ENV"):
            _ = config.endpoint.api_key
        monkeypatch.setenv("MY_KEY_ENV", "secret-but-never-in-a-file")
        assert config.endpoint.api_key == "secret-but-never-in-a-file"

    def test_no_api_key_configured_is_fine(self, tmp_path):
        config_file = tmp_path / "c.yaml"
        config_file.write_text(
            "endpoint:\n  model: m\nvariants:\n  a: prompts/a\ncases:\n  - cases/x.yaml\n"
        )
        (tmp_path / "prompts" / "a").mkdir(parents=True)
        (tmp_path / "prompts" / "a" / "v1.md").write_text("x")
        (tmp_path / "cases").mkdir()
        (tmp_path / "cases" / "x.yaml").write_text("- id: c\n  variant: a\n  expect:\n    max_words: 5\n")
        config = load_config(config_file)
        assert config.endpoint.api_key is None
