import pytest

from prompt_regression_cli.cases import load_cases, parse_case
from prompt_regression_cli.errors import CaseError


VALID = {
    "id": "c1",
    "variant": "demo",
    "variables": {"name": "Sam"},
    "expect": {
        "max_words": 50,
        "rubric": [{"id": "r1", "description": "d", "contains": "sorry"}],
    },
}


class TestParseCase:
    def test_valid(self):
        case = parse_case(dict(VALID), "inline")
        assert case.id == "c1"
        assert case.rubric[0].id == "r1"
        assert case.expect["max_words"] == 50

    def test_unknown_case_keys(self):
        with pytest.raises(CaseError, match="unknown case keys"):
            parse_case({**VALID, "flavor": "vanilla"}, "inline")

    def test_id_required(self):
        with pytest.raises(CaseError, match="string 'id'"):
            parse_case({"variant": "demo"}, "inline")

    def test_variant_required(self):
        with pytest.raises(CaseError, match="variant"):
            parse_case({"id": "x"}, "inline")

    def test_rubric_item_needs_id(self):
        with pytest.raises(CaseError, match="string 'id'"):
            parse_case({**VALID, "expect": {"rubric": [{"contains": "sorry"}]}}, "inline")

    def test_rubric_item_needs_exactly_one_check(self):
        item = {"id": "r", "contains": "a", "regex": "b"}
        with pytest.raises(CaseError, match="exactly one check"):
            parse_case({**VALID, "expect": {"rubric": [item]}}, "inline")

    def test_rubric_item_without_check(self):
        with pytest.raises(CaseError, match="exactly one check"):
            parse_case({**VALID, "expect": {"rubric": [{"id": "r", "description": "no check"}]}}, "inline")

    def test_unsupported_expect_check(self):
        with pytest.raises(CaseError, match="unsupported expect"):
            bad = {**VALID, "expect": {"mood_score": 5}}
            parse_case(bad, "inline")

    def test_expect_list_is_a_rubric_shorthand(self):
        case = parse_case(
            {"id": "c", "variant": "demo", "expect": [{"id": "r1", "contains": "sorry"}]},
            "inline",
        )
        assert len(case.rubric) == 1
        assert "rubric" not in case.expect or case.expect.get("rubric")

    def test_variables_must_be_mapping(self):
        with pytest.raises(CaseError, match="variables"):
            parse_case({**VALID, "variables": ["Sam"]}, "inline")


class TestLoadCases:
    def test_loads_list(self, tmp_path):
        path = tmp_path / "cases.yaml"
        path.write_text(
            "- id: a\n  variant: demo\n  expect:\n    max_words: 5\n"
            "- id: b\n  variant: demo\n  expect:\n    rubric:\n      - id: r\n        regex: x\n"
        )
        cases = load_cases([path])
        assert [case.id for case in cases] == ["a", "b"]

    def test_duplicate_ids(self, tmp_path):
        path = tmp_path / "cases.yaml"
        path.write_text("- id: a\n  variant: demo\n  expect:\n    max_words: 1\n- id: a\n  variant: demo\n  expect:\n    max_words: 1\n")
        with pytest.raises(CaseError, match="Duplicate case id"):
            load_cases([path])

    def test_not_a_list(self, tmp_path):
        path = tmp_path / "cases.yaml"
        path.write_text("id: a\nvariant: demo\n")
        with pytest.raises(CaseError, match="must contain a list"):
            load_cases([path])

    def test_empty_file_skipped_but_all_empty_raises(self, tmp_path):
        empty = tmp_path / "empty.yaml"
        empty.write_text("")
        with pytest.raises(CaseError, match="No test cases"):
            load_cases([empty])
