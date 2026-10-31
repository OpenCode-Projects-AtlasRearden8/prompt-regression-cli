import json

import pytest

from prompt_regression_cli import report as report_mod
from prompt_regression_cli.errors import ReportError


def sample_report(status="pass"):
    return report_mod.build_report(
        suite="demo",
        created_utc="2026-10-31T00:00:00Z",
        endpoint={"base_url": "http://localhost:11434/v1", "model": "llama3.2"},
        variant_versions={"demo": "v2"},
        case_results=[
            {
                "id": "case-a",
                "description": "",
                "variant": "demo",
                "version": "v2",
                "status": status,
                "error": None,
                "prompt": "hello",
                "output": "world",
                "exact": [{"check": "max_words", "value": 5, "passed": True, "detail": "2 words"}],
                "rubric": [
                    {
                        "id": "apology",
                        "description": "Apologizes using the word sorry",
                        "check": "contains",
                        "value": "sorry",
                        "passed": status == "pass",
                        "detail": "detail text",
                    }
                ],
            }
        ],
    )


@pytest.fixture
def two_reports(tmp_path):
    first = report_mod.build_report(
        suite="demo",
        created_utc="2026-10-31T00:00:00Z",
        endpoint={},
        variant_versions={},
        case_results=sample_report("pass")["cases"],
    )
    second = report_mod.build_report(
        suite="demo",
        created_utc="2026-10-31T01:00:00Z",
        endpoint={},
        variant_versions={},
        case_results=sample_report("fail")["cases"],
    )
    report_mod.save_report(tmp_path, first, report_mod.report_basename("demo", "STAMP1"))
    report_mod.save_report(tmp_path, second, report_mod.report_basename("demo", "STAMP2"))
    return tmp_path


class TestSaveLoad:
    def test_roundtrip(self, tmp_path):
        json_path, md_path = report_mod.save_report(tmp_path, sample_report(), "demo-x")
        assert json_path.name == "demo-x.json" and md_path.name == "demo-x.md"
        loaded = report_mod.load_report(json_path)
        assert loaded["suite"] == "demo"
        assert loaded["cases"][0]["rubric"][0]["id"] == "apology"

    def test_load_report_rejects_garbage(self, tmp_path):
        path = tmp_path / "x.json"
        path.write_text(json.dumps([1, 2, 3]))
        with pytest.raises(ReportError, match="prompt-regression report"):
            report_mod.load_report(path)

    def test_report_markdown_sections(self, tmp_path):
        text = report_mod.render_markdown(sample_report("fail"))
        assert "# Prompt regression report" in text
        assert "| Case |" in text
        assert "**FAIL**" in text
        assert "| apology |" in text
        assert "## fail: case-a" in text


class TestResolveReferences:
    def test_load_reports_filters_by_suite(self, two_reports):
        found = report_mod.load_reports(two_reports, "demo")
        assert [entry[1]["created_utc"] for entry in found] == [
            "2026-10-31T00:00:00Z",
            "2026-10-31T01:00:00Z",
        ]

    def test_load_reports_ignores_foreign_json(self, two_reports):
        (two_reports / "other.json").write_text(json.dumps({"schema": 1, "cases": {}}, sort_keys=True))
        assert len(report_mod.load_reports(two_reports, "demo")) == 2

    def test_latest_and_previous(self, two_reports):
        (_, old), (_, new) = report_mod.latest_and_previous(two_reports, "demo")
        assert old["created_utc"] == "2026-10-31T00:00:00Z"
        assert new["created_utc"] == "2026-10-31T01:00:00Z"

    def test_latest_and_previous_single_report(self, tmp_path):
        report_mod.save_report(tmp_path, sample_report(), "demo-only")
        with pytest.raises(ReportError, match="run the suite again"):
            report_mod.latest_and_previous(tmp_path, "demo")

    def test_previous_and_report(self, two_reports):
        new_file = two_reports / "demo-STAMP2.json"
        (old_path, old_report), (new_path, new_report) = report_mod.previous_and_report(new_file)
        assert old_report["created_utc"] == "2026-10-31T00:00:00Z"
        assert new_path == new_file
