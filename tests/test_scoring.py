import pytest

from prompt_regression_cli.errors import CaseError
from prompt_regression_cli.scoring import evaluate_check, evaluate_expect, CHECK_KEYS


class TestIndividualChecks:
    def setup_method(self):
        self.gold = "Sorry Jordan, a replacement clip pen ships within 3 business days. - Pen & Pencil Co."

    def test_equals(self):
        assert evaluate_check("equals", self.gold, self.gold).passed
        passed = evaluate_check("equals", " different ", self.gold + " ")
        assert passed.passed is False

    def test_contains_string_and_list(self):
        assert evaluate_check("contains", "replacement", self.gold).passed
        result = evaluate_check("contains", ["replacement", "missing-thing"], self.gold)
        assert not result.passed
        assert "missing-thing" in result.detail

    def test_contains_all(self):
        assert evaluate_check("contains_all", ["Sorry", "clip"], self.gold).passed
        assert not evaluate_check("contains_all", ["sorry"], self.gold).passed

    def test_contains_any(self):
        assert evaluate_check("contains_any", ["nope", "Sorry"], self.gold).passed
        assert not evaluate_check("contains_any", ["nope", "nada"], self.gold).passed

    def test_not_contains(self):
        assert evaluate_check("not_contains", "refund", self.gold).passed
        assert not evaluate_check("not_contains", ["Sorry"], self.gold).passed

    def test_regex(self):
        assert evaluate_check("regex", r"\d+ business days", self.gold).passed
        assert not evaluate_check("regex", r"^\d", self.gold).passed

    def test_starts_and_ends_with(self):
        assert evaluate_check("starts_with", "Sorry", self.gold).passed
        assert evaluate_check("ends_with", "- Pen & Pencil Co.", self.gold).passed
        assert not evaluate_check("starts_with", "Hi", self.gold).passed

    def test_word_limits(self):
        assert evaluate_check("max_words", 16, self.gold).passed
        assert not evaluate_check("max_words", 15, self.gold).passed
        assert evaluate_check("min_words", 16, self.gold).passed
        assert not evaluate_check("min_words", 17, self.gold).passed

    def test_unknown_check(self):
        with pytest.raises(CaseError, match="unknown check"):
            evaluate_check("fuzzy_match", "x", self.gold)

    def test_invalid_regex_is_case_error(self):
        with pytest.raises(CaseError, match="invalid regex"):
            evaluate_check("regex", "(unclosed", self.gold)

    def test_bad_value_types(self):
        with pytest.raises(CaseError, match="string"):
            evaluate_check("equals", 42, self.gold)
        with pytest.raises(CaseError, match="list"):
            evaluate_check("contains_all", ["ok", 5], self.gold)
        with pytest.raises(CaseError, match="integer"):
            evaluate_check("max_words", "lots", self.gold)


class TestEvaluateExpect:
    def test_mixes_exact_and_rubric(self):
        expect = {
            "max_words": 100,
            "rubric": [
                {"id": "r1", "description": "d", "contains": "Sorry"},
                {"id": "r2", "contains_any": [":)", "sorry"]},
            ],
        }
        rubric_items = expect["rubric"]
        exact, rubric = evaluate_expect(expect, "Sorry friend.", rubric_items)
        assert len(exact) == 1 and exact[0].passed
        assert len(rubric) == 2
        assert [r.id for r in rubric] == ["r1", "r2"]
        assert rubric[0].description == "d"

    def test_rubric_result_carries_value(self):
        expect = {
            "rubric": [{"id": "r1", "regex": "ship"}],
        }
        exact, rubric = evaluate_expect(expect, "It will ship tomorrow.", expect["rubric"])
        assert exact == []
        assert rubric[0].passed and rubric[0].value == "ship"

    def test_check_keys_surface(self):
        assert "equals" in CHECK_KEYS and "max_words" in CHECK_KEYS
