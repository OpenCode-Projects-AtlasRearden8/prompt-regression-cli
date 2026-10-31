import json
from pathlib import Path

import pytest
import yaml

from prompt_regression_cli.cli import main

MARKER_V2 = "SUPPORT-TEMPLATE-V2"
MARKER_V1 = "SUPPORT-TEMPLATE-V1"
GOOD = f"Sorry, happy to help! OK-PHRASE here. {MARKER_V2} is the version being used."


def write_project(tmp_path, mock_base_url, extra_cases=None):
    (tmp_path / "prompts" / "support-reply").mkdir(parents=True)
    (tmp_path / "prompts" / "support-reply" / "v1.md").write_text(
        f"Reply about {{customer_name}}. {MARKER_V1}\n"
    )
    (tmp_path / "prompts" / "support-reply" / "v2.md").write_text(
        f"Reply about {{customer_name}}. {MARKER_V2}\n"
    )
    (tmp_path / "cases").mkdir()
    case = {
        "id": "basic",
        "variant": "support-reply",
        "variables": {"customer_name": "Sam"},
        "expect": {
            "max_words": 50,
            "rubric": [
                {
                    "id": "phrase",
                    "description": "mentions the controlled phrase",
                    "contains_all": "OK-PHRASE",
                }
            ],
        },
    }
    cases = [case] + list(extra_cases or [])
    (tmp_path / "cases" / "support.yaml").write_text(yaml.safe_dump(cases))
    config_path = tmp_path / "prompt-regression.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "endpoint": {"base_url": mock_base_url, "model": "mock-model"},
                "variants": {"support-reply": "prompts/support-reply"},
                "cases": ["cases/support.yaml"],
            }
        )
    )
    return config_path


def modify_case(tmp_path, filename, function):
    path = tmp_path / "cases" / filename
    data = yaml.safe_load(path.read_text())
    function(data)
    path.write_text(yaml.safe_dump(data))


class TestRunAgainstMock:
    def test_passing_run(self, tmp_path, mock_server, capsys):
        mock_server.default_content = GOOD
        config_path = write_project(tmp_path, mock_server.base_url)
        exit_code = main(["run", str(config_path), "--suite", "demo"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "[PASS] basic (support-reply@v2)" in captured.out
        assert "PASS: 1/1 cases, 2/2 checks" in captured.out
        sent = mock_server.last_request["body"]
        assert sent["messages"][0]["content"].rstrip().endswith(MARKER_V2)
        reports = sorted((tmp_path / "reports").glob("demo-*.json"))
        assert len(reports) == 1
        report = json.loads(reports[0].read_text())
        assert report["summary"]["status"] == "pass"
        assert "# Prompt regression report" in reports[0].with_suffix(".md").read_text()

    def test_failing_rubric_exit_code(self, tmp_path, mock_server, capsys):
        mock_server.default_content = "Nothing useful at all."
        config_path = write_project(tmp_path, mock_server.base_url)
        exit_code = main(["run", str(config_path), "--suite", "demo"])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "[FAIL] basic" in captured.out
        assert "FAIL: 0/1 cases" in captured.out

    def test_endpoint_error_marks_case_errored(self, tmp_path, mock_server, capsys):
        mock_server.default_content = GOOD
        mock_server.next_error = (500, {"error": "splat"})
        config_path = write_project(tmp_path, mock_server.base_url)
        exit_code = main(["run", str(config_path), "--suite", "demo"])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "[ERROR] basic" in captured.out
        report_file = next(iter((tmp_path / "reports").glob("demo-*.json")))
        report = json.loads(report_file.read_text())
        assert report["cases"][0]["status"] == "error"
        assert "HTTP 500" in report["cases"][0]["error"]

    def test_version_pinned_to_v1(self, tmp_path, mock_server):
        mock_server.default_content = GOOD
        config_path = write_project(tmp_path, mock_server.base_url)
        modify_case(tmp_path, "support.yaml", lambda data: data[0].update(version=1))
        assert main(["run", str(config_path), "--suite", "demo"]) == 0
        assert mock_server.last_request["body"]["messages"][0]["content"].rstrip().endswith(MARKER_V1)

    def test_dry_run_never_contacts_endpoint(self, tmp_path, mock_server, capsys):
        config_path = write_project(tmp_path, "http://127.0.0.1:9/v1")
        exit_code = main(["run", str(config_path), "--dry-run"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "not contacted" in captured.out
        assert mock_server.requests == []
        assert MARKER_V2 in captured.out

    def test_limit_runs_subset(self, tmp_path, mock_server, capsys):
        mock_server.default_content = GOOD
        extra = {
            "id": "second",
            "variant": "support-reply",
            "variables": {"customer_name": "Alex"},
            "expect": {"max_words": 50},
        }
        config_path = write_project(tmp_path, mock_server.base_url, extra_cases=[extra])
        exit_code = main(["run", str(config_path), "--suite", "demo", "--limit", "1"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "basic" in captured.out
        assert "second" not in captured.out

    def test_unknown_variant_is_config_error(self, tmp_path, mock_server, capsys):
        config_path = write_project(tmp_path, mock_server.base_url)
        modify_case(tmp_path, "support.yaml", lambda data: data[0].update(variant="ghost-reply"))
        exit_code = main(["run", str(config_path)])
        captured = capsys.readouterr()
        assert exit_code == 2
        assert "ghost-reply" in captured.err

    def test_missing_variable_is_template_error(self, tmp_path, mock_server, capsys):
        config_path = write_project(tmp_path, mock_server.base_url)

        def break_variables(data):
            del data[0]["variables"]

        modify_case(tmp_path, "support.yaml", break_variables)
        exit_code = main(["run", str(config_path)])
        captured = capsys.readouterr()
        assert exit_code == 2
        assert "{customer_name}" in captured.err


class TestCheckAndList:
    def test_check_ok(self, tmp_path, mock_server, capsys):
        config_path = write_project(tmp_path, mock_server.base_url)
        assert main(["check", str(config_path)]) == 0
        captured = capsys.readouterr()
        assert "Config OK" in captured.out
        assert "Cases OK" in captured.out
        assert mock_server.requests == []

    def test_check_finds_missing_template_variable(self, tmp_path, mock_server, capsys):
        config_path = write_project(tmp_path, mock_server.base_url)
        assert main(["check", str(config_path)]) == 0
        modify_case(tmp_path, "support.yaml", lambda data: data[0].update(variables={"wrong_name": "x"}))
        exit_code = main(["check", str(config_path)])
        captured = capsys.readouterr()
        assert exit_code == 2
        assert "{customer_name}" in captured.err

    def test_list_shows_versions(self, tmp_path, mock_server, capsys):
        config_path = write_project(tmp_path, mock_server.base_url)
        assert main(["list", str(config_path)]) == 0
        captured = capsys.readouterr()
        assert "variant support-reply: v1, v2 (latest)" in captured.out
        assert "case basic:" in captured.out

    def test_missing_config_is_usage_error(self, tmp_path, capsys):
        exit_code = main(["check", str(tmp_path / "missing.yaml")])
        captured = capsys.readouterr()
        assert exit_code == 2
        assert "error:" in captured.err


class TestDiffCommand:
    @pytest.fixture
    def two_runs(self, tmp_path, mock_server):
        config_path = write_project(tmp_path, mock_server.base_url)
        mock_server.default_content = GOOD
        assert main(["run", str(config_path)]) == 0
        mock_server.default_content = "Unrelated words entirely."
        assert main(["run", str(config_path)]) == 1
        return config_path

    def test_latest_diff_detects_regression(self, two_runs, capsys):
        exit_code = main(["diff", "latest", "--config", str(two_runs)])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "# Prompt regression diff" in captured.out
        assert "**REGRESSED**" in captured.out
        assert "0 fixed, 1 regressed" in captured.out

    def test_diff_two_files(self, two_runs, tmp_path, capsys):
        reports = sorted((tmp_path / "reports").glob("*.json"))
        assert len(reports) == 2
        assert main(["diff", str(reports[0]), str(reports[1])]) == 0

    def test_fail_on_regression_flag(self, two_runs):
        assert main(["diff", "latest", "--config", str(two_runs), "--fail-on-regression"]) == 1

    def test_diff_out_file(self, two_runs, tmp_path, capsys):
        out_path = tmp_path / "diff.md"
        assert main(["diff", "latest", "--config", str(two_runs), "--out", str(out_path)]) == 0
        assert "REGRESSED" in out_path.read_text()


class TestShippedExamples:
    def test_repo_examples_validate(self, capsys):
        repo_root = Path(__file__).resolve().parent.parent
        exit_code = main(["check", str(repo_root / "prompt-regression.yaml")])
        assert exit_code == 0
