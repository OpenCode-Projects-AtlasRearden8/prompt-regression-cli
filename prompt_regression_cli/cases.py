from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .errors import CaseError
from .scoring import CHECK_KEYS

_CASE_KEYS = {"id", "variant", "version", "variables", "expect", "description"}
_CHECK_KEYS = CHECK_KEYS
_EXACT_EXPECT_KEYS = CHECK_KEYS | {"rubric"}


@dataclass
class RubricItem:
    id: str = ""
    description: str = ""
    check: str = ""
    value: object = None

    def to_dict(self):
        return {
            "id": self.id,
            "description": self.description,
            "check": self.check,
            "value": self.value,
        }


@dataclass
class Case:
    id: str = ""
    variant: str = ""
    version: object = None
    description: str = ""
    variables: dict = field(default_factory=dict)
    expect: dict = field(default_factory=dict)
    rubric: list = field(default_factory=list)
    source: str = ""


def _check_keys_in(mapping, where):
    return [key for key in mapping if key in CHECK_KEYS]


def parse_case(raw, source):
    if not isinstance(raw, dict):
        raise CaseError(f"{source}: each test case must be a mapping, got {type(raw).__name__}")
    unknown = sorted(set(raw) - _CASE_KEYS)
    if unknown:
        raise CaseError(f"{source}: unknown case keys {unknown} (allowed: {sorted(_CASE_KEYS)})")
    case_id = raw.get("id")
    if not case_id or not isinstance(case_id, str):
        raise CaseError(f"{source}: every case needs a string 'id'")
    variant = raw.get("variant")
    if not variant or not isinstance(variant, str):
        raise CaseError(f"{source}: case '{case_id}' needs a 'variant' name")
    case = Case(
        id=case_id,
        variant=variant,
        version=raw.get("version"),
        description=str(raw.get("description") or ""),
        source=source,
    )
    variables = raw.get("variables") or {}
    if not isinstance(variables, dict):
        raise CaseError(f"{source}: case '{case_id}' 'variables' must be a mapping")
    case.variables = {str(key): value for key, value in variables.items()}

    expect = raw.get("expect") or {}
    if isinstance(expect, list):
        expect = {"rubric": expect}
    if isinstance(expect, str):
        raise CaseError(
            f"{source}: case '{case_id}' 'expect' must be a mapping of checks or a list of rubric items"
        )
    if not isinstance(expect, dict):
        raise CaseError(f"{source}: case '{case_id}' 'expect' must be a mapping")
    known = _EXACT_EXPECT_KEYS
    unsupported = sorted(set(expect) - known)
    if unsupported:
        raise CaseError(
            f"{source}: case '{case_id}' has unsupported expect keys {unsupported} "
            f"(supported: {sorted(known)})"
        )
    case.expect = expect
    rubric = expect.get("rubric") or []
    if not isinstance(rubric, list):
        raise CaseError(f"{source}: case '{case_id}' 'expect.rubric' must be a list")
    case.rubric = [parse_rubric_item(item, f"{source}:{case_id}", index) for index, item in enumerate(rubric)]
    return case


def parse_rubric_item(raw, source, index):
    if not isinstance(raw, dict):
        raise CaseError(f"{source}: rubric item #{index} must be a mapping")
    item_id = raw.get("id")
    if not item_id or not isinstance(item_id, str):
        raise CaseError(f"{source}: rubric item #{index} needs a string 'id'")
    checks = _check_keys_in(raw, source)
    if len(checks) != 1:
        raise CaseError(
            f"{source}: rubric item '{item_id}' must define exactly one check "
            f"(found {checks or 'none'}; choose from {sorted(CHECK_KEYS)})"
        )
    check = checks[0]
    return RubricItem(
        id=item_id,
        description=str(raw.get("description") or ""),
        check=check,
        value=raw[check],
    )


def load_cases(case_files):
    cases = []
    seen = set()
    for case_file in case_files:
        path = Path(case_file)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise CaseError(f"Could not parse YAML in {path}: {exc}")
        if not data:
            continue
        if not isinstance(data, list):
            raise CaseError(f"{path}: test case file must contain a list of cases")
        for index, raw in enumerate(data):
            case = parse_case(raw, f"{path}#{index}")
            if case.id in seen:
                raise CaseError(f"Duplicate case id '{case.id}' ({path}#{index})")
            seen.add(case.id)
            cases.append(case)
    if not cases:
        raise CaseError("No test cases loaded; case files are empty")
    return cases
