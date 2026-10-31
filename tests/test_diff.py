import pytest

from prompt_regression_cli import diff as diff_mod


def case_result(case_id, rubric_states):
    return {
        "id": case_id,
        "exact": [],
        "rubric": [
            {
                "id": rubric_id,
                "description": f"desc {rubric_id}",
                "check": "contains",
                "passed": state,
                "detail": f"detail {rubric_id}",
            }
            for rubric_id, state in rubric_states.items()
        ],
    }


def report_for(case_a):
    return {
        "schema": 1,
        "suite": "suite-x",
        "created_utc": "2026-10-31T00:00:00Z",
        "summary": {"cases": 1, "cases_passed": 1 if case_a["rubric"][0]["passed"] else 0},
        "cases": [case_a],
    }


class TestDiffCase:
    def test_fix_and_regress(self):
        old = case_result("c1", {"apology": False, "signoff": True})
        new = case_result("c1", {"apology": True, "signoff": False})
        changes = diff_mod.diff_case(old, new)
        statuses = {change["id"]: change["status"] for change in changes}
        assert statuses == {"apology": diff_mod.FIXED, "signoff": diff_mod.REGRESSED}

    def test_added_and_removed_rubric_items(self):
        old = case_result("c1", {"old_item": True})
        new = case_result("c1", {"new_item": False})
        statuses = {change["id"]: change["status"] for change in diff_mod.diff_case(old, new)}
        assert statuses == {"old_item": "removed", "new_item": "added"}

    def test_exact_checks_compared_too(self):
        old = case_result("c1", {})
        old["exact"] = [{"check": "max_words", "passed": True, "detail": "d"}]
        new = case_result("c1", {})
        new["exact"] = [{"check": "max_words", "passed": False, "detail": "d"}]
        statuses = {change["id"]: change["status"] for change in diff_mod.diff_case(old, new)}
        assert statuses == {"max_words": diff_mod.REGRESSED}

    def test_unchanged_yields_no_changes(self):
        assert diff_mod.diff_case(case_result("c1", {"a": True}), case_result("c1", {"a": True})) == []


class TestDiffReports:
    def test_summary_counts_and_bounds(self):
        old = report_for(case_result("c1", {"apology": False}))
        new = report_for(case_result("c2", {"apology": True}))
        result = diff_mod.diff_reports(old, new)
        assert result["added_cases"] == ["c2"]
        assert result["removed_cases"] == ["c1"]
        assert result["total"]["fixed"] == 0
        assert result["total"]["regressed"] == 0
        assert "c1#apology" not in {f"{c['case']}#{c['id']}" for c in result["changes"]}

    def test_regressed_count(self):
        old = report_for(case_result("c1", {"apology": True}))
        new = report_for(case_result("c1", {"apology": False}))
        result = diff_mod.diff_reports(old, new)
        assert result["total"]["regressed"] == 1


class TestRenderDiff:
    def test_marks_regressions_and_fixes(self):
        old = report_for(case_result("c1", {"apology": True, "signoff": False}))
        new = report_for(case_result("c1", {"apology": False, "signoff": True}))
        result = diff_mod.diff_reports(old, new)
        text = diff_mod.render_diff_markdown(result, old_path="a.json", new_path="b.json")
        assert "# Prompt regression diff" in text
        assert "REGRESSED" in text
        assert "fixed" in text
        assert "1 fixed, 1 regressed" in text

    def test_no_changes_message(self):
        result = diff_mod.diff_reports(report_for(case_result("c1", {"a": True})), report_for(case_result("c1", {"a": True})))
        text = diff_mod.render_diff_markdown(result)
        assert "No rubric or exact-check results changed" in text
