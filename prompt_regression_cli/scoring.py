import re
from dataclasses import dataclass, field

from .errors import CaseError

CHECK_KEYS = {
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
}

_WORD_RE = re.compile(r"\S+")


@dataclass
class CheckResult:
    check: str
    value: object
    passed: bool
    detail: str
    id: str = ""
    description: str = ""

    def to_dict(self):
        data = {
            "check": self.check,
            "value": self.value,
            "passed": self.passed,
            "detail": self.detail,
        }
        if self.id:
            data["id"] = self.id
        if self.description:
            data["description"] = self.description
        return data


def _short(text, limit=160):
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _as_str(value, check):
    if not isinstance(value, str):
        raise CaseError(f"check '{check}' expects a string value, got {type(value).__name__}")
    return value


def _as_str_list(value, check):
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise CaseError(f"check '{check}' expects a string or a list of strings")


def _as_int(value, check):
    if not isinstance(value, int) or isinstance(value, bool):
        raise CaseError(f"check '{check}' expects an integer, got {type(value).__name__}")
    return value


def check_equals(value, output):
    expected = _as_str(value, "equals")
    passed = output.strip() == expected.strip()
    detail = "matches exactly" if passed else f"expected: '{_short(expected)}' / got: '{_short(output)}'"
    return passed, detail


def check_contains(value, output):
    needles = _as_str_list(value, "contains")
    hits = [needle for needle in needles if needle in output]
    passed = len(hits) == len(needles)
    missing = [needle for needle in needles if needle not in output]
    detail = "all substrings found" if passed else "missing: " + ", ".join(f"'{_short(m)}'" for m in missing)
    return passed, detail


def check_contains_all(value, output):
    needles = _as_str_list(value, "contains_all")
    missing = [needle for needle in needles if needle not in output]
    passed = not missing
    detail = "all substrings found" if passed else "missing: " + ", ".join(f"'{_short(m)}'" for m in missing)
    return passed, detail


def check_contains_any(value, output):
    needles = _as_str_list(value, "contains_any")
    hits = [needle for needle in needles if needle in output]
    passed = bool(hits)
    detail = "found: " + ", ".join(f"'{_short(h)}'" for h in hits) if hits else "none of " + ", ".join(
        f"'{_short(n)}'" for n in needles
    ) + " present"
    return passed, detail


def check_not_contains(value, output):
    needles = _as_str_list(value, "not_contains")
    found = [needle for needle in needles if needle in output]
    passed = not found
    detail = "none present" if passed else "forbidden text present: " + ", ".join(f"'{_short(f)}'" for f in found)
    return passed, detail


def check_regex(value, output):
    pattern = _as_str(value, "regex")
    match = re.search(pattern, output)
    if match:
        return True, f"matched '{_short(match.group(0))}'"
    return False, f"no match for pattern '{_short(pattern)}'"


def check_starts_with(value, output):
    prefix = _as_str(value, "starts_with")
    stripped = output.strip()
    passed = stripped.startswith(prefix)
    detail = f"starts with '{_short(prefix)}'" if passed else f"output starts with '{_short(stripped)}'"
    return passed, detail


def check_ends_with(value, output):
    suffix = _as_str(value, "ends_with")
    stripped = output.strip()
    passed = stripped.endswith(suffix)
    detail = f"ends with '{_short(suffix)}'" if passed else f"output ends with '{_short(stripped)}'"
    return passed, detail


def check_min_words(value, output):
    minimum = _as_int(value, "min_words")
    count = len(_WORD_RE.findall(output))
    passed = count >= minimum
    detail = f"{count} words (required >= {minimum})"
    return passed, detail


def check_max_words(value, output):
    maximum = _as_int(value, "max_words")
    count = len(_WORD_RE.findall(output))
    passed = count <= maximum
    detail = f"{count} words (required <= {maximum})"
    return passed, detail


CHECKS = {
    "equals": check_equals,
    "contains": check_contains,
    "contains_all": check_contains_all,
    "contains_any": check_contains_any,
    "not_contains": check_not_contains,
    "regex": check_regex,
    "starts_with": check_starts_with,
    "ends_with": check_ends_with,
    "min_words": check_min_words,
    "max_words": check_max_words,
}


def evaluate_check(check, value, output):
    if check not in CHECKS:
        raise CaseError(f"unknown check '{check}' (choose from {sorted(CHECKS)})")
    try:
        passed, detail = CHECKS[check](value, output)
    except re.error as exc:
        raise CaseError(f"invalid regex in check '{check}': {exc}")
    return CheckResult(check=check, value=value, passed=passed, detail=detail)


def _rubric_item_fields(item):
    if hasattr(item, "check") and hasattr(item, "value"):
        return item.id, item.description, item.check, item.value
    if isinstance(item, dict):
        item_id = str(item.get("id") or "")
        description = str(item.get("description") or "")
        checks = [key for key in CHECK_KEYS if key in item]
        if len(checks) != 1:
            raise CaseError(
                f"rubric item '{item_id or index}' must define exactly one check "
                f"(found {checks or 'none'})"
            )
        return item_id, description, checks[0], item[checks[0]]
    raise CaseError(f"unsupported rubric item: {item!r}")


def evaluate_expect(expect, output, rubric_items=None):
    exact = []
    rubric = []
    for key, value in expect.items():
        if key == "rubric":
            continue
        result = evaluate_check(key, value, output)
        result.id = key
        exact.append(result)
    for item in rubric_items or []:
        item_id, description, check, value = _rubric_item_fields(item)
        result = evaluate_check(check, value, output)
        result.id = item_id
        result.description = description
        rubric.append(result)
    return exact, rubric
