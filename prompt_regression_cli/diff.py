REGRESSED = "regressed"
FIXED = "fixed"
UNCHANGED = "unchanged"


def diff_case(old_case, new_case):
    changes = []
    old_rubric = {item.get("id") or item.get("check"): item for item in old_case.get("rubric", [])}
    new_rubric = {item.get("id") or item.get("check"): item for item in new_case.get("rubric", [])}
    for item_id, new_item in new_rubric.items():
        old_item = old_rubric.get(item_id)
        if old_item is None:
            changes.append(
                {
                    "case": new_case["id"],
                    "kind": "rubric",
                    "id": item_id,
                    "description": new_item.get("description", ""),
                    "old": None,
                    "new": new_item,
                    "status": "added",
                }
            )
            continue
        if old_item.get("passed") != new_item.get("passed"):
            status = REGRESSED if new_item.get("passed") is False else FIXED
            changes.append(
                {
                    "case": new_case["id"],
                    "kind": "rubric",
                    "id": item_id,
                    "description": new_item.get("description", ""),
                    "old": old_item,
                    "new": new_item,
                    "status": status,
                }
            )
    for item_id, old_item in old_rubric.items():
        if item_id not in new_rubric:
            changes.append(
                {
                    "case": new_case["id"],
                    "kind": "rubric",
                    "id": item_id,
                    "description": old_item.get("description", ""),
                    "old": old_item,
                    "new": None,
                    "status": "removed",
                }
            )
    old_exact = {item.get("check"): item for item in old_case.get("exact", [])}
    new_exact = {item.get("check"): item for item in new_case.get("exact", [])}
    for check, new_item in new_exact.items():
        old_item = old_exact.get(check)
        if old_item is None:
            changes.append(
                {
                    "case": new_case["id"],
                    "kind": "exact",
                    "id": check,
                    "description": "",
                    "old": None,
                    "new": new_item,
                    "status": "added",
                }
            )
            continue
        if old_item.get("passed") != new_item.get("passed"):
            status = REGRESSED if new_item.get("passed") is False else FIXED
            changes.append(
                {
                    "case": new_case["id"],
                    "kind": "exact",
                    "id": check,
                    "description": "",
                    "old": old_item,
                    "new": new_item,
                    "status": status,
                }
            )
    for check, old_item in old_exact.items():
        if check not in new_exact:
            changes.append(
                {
                    "case": new_case["id"],
                    "kind": "exact",
                    "id": check,
                    "description": "",
                    "old": old_item,
                    "new": None,
                    "status": "removed",
                }
            )
    return changes


def diff_reports(old_report, new_report):
    old_cases = {case["id"]: case for case in old_report.get("cases", [])}
    new_cases = {case["id"]: case for case in new_report.get("cases", [])}
    changes = []
    added_cases = sorted(set(new_cases) - set(old_cases))
    removed_cases = sorted(set(old_cases) - set(new_cases))
    for case_id in sorted(set(old_cases) & set(new_cases)):
        changes.extend(diff_case(old_cases[case_id], new_cases[case_id]))
    fixed = sum(1 for change in changes if change["status"] == FIXED)
    regressed = sum(1 for change in changes if change["status"] == REGRESSED)
    unchanged = _unchanged_count(
        old_cases, new_cases, [change for change in changes if change["kind"] == "rubric"]
    )
    return {
        "old_suite": old_report.get("suite"),
        "new_suite": new_report.get("suite"),
        "old_created": old_report.get("created_utc"),
        "new_created": new_report.get("created_utc"),
        "old_versions": old_report.get("variant_versions") or {},
        "new_versions": new_report.get("variant_versions") or {},
        "old_summary": old_report.get("summary") or {},
        "new_summary": new_report.get("summary") or {},
        "changes": changes,
        "added_cases": added_cases,
        "removed_cases": removed_cases,
        "total": {"fixed": fixed, "regressed": regressed, "unchanged": unchanged},
    }


def _unchanged_count(old_cases, new_cases, rubric_changes):
    count = 0
    changed = {(change["case"], change["id"]) for change in rubric_changes}
    for case_id in set(old_cases) & set(new_cases):
        for item in new_cases[case_id].get("rubric", []):
            key = (case_id, item.get("id") or item.get("check"))
            if key not in changed:
                count += 1
    return count


def _state(item):
    if item is None:
        return "-"
    return "pass" if item.get("passed") else "FAIL"


def _detail(item):
    if item is None:
        return "-"
    return str(item.get("detail", ""))


def render_diff_markdown(diff, old_path=None, new_path=None):
    lines = []
    lines.append("# Prompt regression diff")
    lines.append("")
    lines.append(f"- Old: {diff['old_suite']} run {diff['old_created']}")
    lines.append(f"- New: {diff['new_suite']} run {diff['new_created']}")
    if old_path and new_path:
        lines.append(f"- Files: {old_path} -> {new_path}")
    old_versions = ", ".join(f"{name}@{version}" for name, version in sorted(diff["old_versions"].items())) or "-"
    new_versions = ", ".join(f"{name}@{version}" for name, version in sorted(diff["new_versions"].items())) or "-"
    lines.append(f"- Versions: {old_versions} -> {new_versions}")
    old_summary = diff["old_summary"]
    new_summary = diff["new_summary"]
    lines.append(
        f"- Cases: {old_summary.get('cases_passed', '?')}/{old_summary.get('cases', '?')} -> "
        f"{new_summary.get('cases_passed', '?')}/{new_summary.get('cases', '?')} passing"
    )
    total = diff["total"]
    lines.append(f"- Rubric/exact changes: {total['fixed']} fixed, {total['regressed']} regressed")
    for case_id in diff["added_cases"]:
        lines.append(f"- Case added: {case_id}")
    for case_id in diff["removed_cases"]:
        lines.append(f"- Case removed: {case_id}")
    lines.append("")
    if not diff["changes"]:
        lines.append("No rubric or exact-check results changed between these runs.")
        lines.append("")
    for change in diff["changes"]:
        icon = {"regressed": "**REGRESSED**", "fixed": "**fixed**", "added": "**added**", "removed": "**removed**"}[
            change["status"]
        ]
        heading = f"{change['case']} / {change['kind']}:{change['id']}"
        lines.append(f"## {icon} {heading}")
        lines.append("")
        lines.append(
            f"{_state(change['old'])} -> {_state(change['new'])}"
        )
        if change["description"]:
            lines.append("")
            lines.append(change["description"])
        lines.append("")
        lines.append(f"- old detail: {_detail(change['old'])}")
        lines.append(f"- new detail: {_detail(change['new'])}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
