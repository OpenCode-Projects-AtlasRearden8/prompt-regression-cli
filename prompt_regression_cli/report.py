import json
from datetime import datetime, timezone
from pathlib import Path

from .errors import ReportError

SCHEMA_VERSION = 1
_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"


def utc_stamp():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}.{datetime.now(timezone.utc).microsecond:06d}Z"


def utc_stamp_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def suite_slug(suite):
    slug = "".join(character if character.isalnum() or character in "-_" else "-" for character in str(suite))
    return slug.strip("-") or "suite"


def report_basename(suite, stamp=None):
    return f"{suite_slug(suite)}-{stamp or utc_stamp()}"


def save_report(reports_dir, report, basename):
    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / (basename + ".json")
    counter = 2
    while json_path.exists():
        json_path = directory / f"{basename}-{counter}.json"
        counter += 1
    md_path = json_path.with_suffix(".md")
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def load_report(path):
    path = Path(path)
    if not path.is_file():
        raise ReportError(f"Report not found: {path}")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReportError(f"Could not parse report {path}: {exc}")
    if not isinstance(report, dict) or "schema" not in report or "cases" not in report:
        raise ReportError(f"{path} does not look like a prompt-regression report")
    return report


def load_reports(reports_dir, suite=None):
    directory = Path(reports_dir)
    if not directory.is_dir():
        raise ReportError(f"Reports directory not found: {directory}")
    reports = []
    for json_path in sorted(directory.glob("*.json")):
        try:
            report = load_report(json_path)
        except ReportError:
            continue
        if suite is None or report.get("suite") == suite:
            reports.append((json_path, report))
    reports.sort(key=lambda entry: (entry[1].get("created_utc", ""), entry[0].name))
    return reports


def previous_and_report(report_path):
    report_path = Path(report_path)
    report = load_report(report_path)
    suite = report.get("suite")
    reports = [
        (path, loaded)
        for path, loaded in load_reports(report_path.parent, suite)
        if path.resolve() != report_path.resolve()
    ]
    if not reports:
        raise ReportError(
            f"No earlier report for suite '{suite}' next to {report_path}; cannot diff a single report"
        )
    return reports[-1], (report_path, report)


def latest_and_previous(reports_dir, suite):
    reports = load_reports(reports_dir, suite)
    if not reports:
        suites_found = sorted({loaded.get("suite") or "" for _, loaded in load_reports(reports_dir, None)})
        hint = f" (found suites: {suites_found})" if suites_found else ""
        raise ReportError(
            f"No saved reports for suite '{suite}' in {reports_dir}{hint}"
        )
    if len(reports) == 1:
        raise ReportError(
            f"Only one saved report for suite '{suite}' in {reports_dir}; run the suite again "
            "before diffing"
        )
    return reports[-2], reports[-1]


def build_report(suite, created_utc, endpoint, variant_versions, case_results):
    cases_passed = sum(1 for result in case_results if result["status"] == "pass")
    cases_failed = sum(1 for result in case_results if result["status"] == "fail")
    cases_errored = sum(1 for result in case_results if result["status"] == "error")
    checks_total = sum(len(result["exact"]) + len(result["rubric"]) for result in case_results)
    checks_passed = sum(
        item["passed"] for result in case_results for item in result["exact"] + result["rubric"]
    )
    return {
        "schema": SCHEMA_VERSION,
        "tool": "prompt-regression-cli",
        "suite": suite,
        "created_utc": created_utc,
        "endpoint": endpoint,
        "variant_versions": variant_versions,
        "cases": case_results,
        "summary": {
            "cases": len(case_results),
            "cases_passed": cases_passed,
            "cases_failed": cases_failed,
            "cases_errored": cases_errored,
            "checks_total": checks_total,
            "checks_passed": checks_passed,
            "status": "pass" if cases_failed == 0 and cases_errored == 0 else "fail",
        },
    }


def build_case_result(case, variant, version, prompt, output, exact_results, rubric_results, error):
    status = "error"
    if error is None:
        all_passed = all(item.passed for item in exact_results + rubric_results)
        status = "pass" if all_passed else "fail"
    return {
        "id": case.id,
        "description": case.description,
        "variant": variant,
        "version": f"v{version}",
        "status": status,
        "error": error,
        "prompt": prompt,
        "output": output,
        "exact": [item.to_dict() for item in exact_results],
        "rubric": [item.to_dict() for item in rubric_results],
    }


def _pre(text):
    return "```\n" + str(text if text is not None else "") + "\n```"


def render_markdown(report):
    summary = report["summary"]
    endpoint = report.get("endpoint") or {}
    lines = []
    lines.append("# Prompt regression report")
    lines.append("")
    lines.append(f"- Run: {report.get('created_utc', '')}")
    lines.append(f"- Suite: {report.get('suite', '')}")
    lines.append(f"- Endpoint: {endpoint.get('base_url', '')} (model: {endpoint.get('model', '')})")
    versions = report.get("variant_versions") or {}
    if versions:
        rendered = ", ".join(f"{name}@{version}" for name, version in sorted(versions.items()))
        lines.append(f"- Prompt versions: {rendered}")
    result = "**PASS**" if summary["status"] == "pass" else "**FAIL**"
    lines.append(
        f"- Result: {result} ({summary['cases_passed']}/{summary['cases']} cases, "
        f"{summary['checks_passed']}/{summary['checks_total']} checks)"
    )
    lines.append("")
    lines.append("| Case | Variant | Score | Status |")
    lines.append("|---|---|---|---|")
    for case_result in report["cases"]:
        rubric_total = len(case_result["rubric"])
        exact_total = [item["passed"] for item in case_result["exact"]]
        score_total = len(exact_total) + rubric_total
        score_passed = sum(exact_total) + sum(1 for item in case_result["rubric"] if item["passed"])
        score = f"{score_passed}/{score_total}" if score_total else "n/a"
        icon = {"pass": "pass", "fail": "FAIL", "error": "ERROR"}[case_result["status"]]
        lines.append(
            f"| {case_result['id']} | {case_result['variant']}@{case_result['version']} | {score} | {icon} |"
        )
    for case_result in report["cases"]:
        lines.append("")
        lines.append(f"## {case_result['status']}: {case_result['id']}")
        if case_result["description"]:
            lines.append("")
            lines.append(case_result["description"])
        rubric = case_result["rubric"]
        exact = case_result["exact"]
        if rubric:
            lines.append("")
            lines.append("| Rubric item | Description | Check | Status | Detail |")
            lines.append("|---|---|---|---|---|")
            for item in rubric:
                status = "pass" if item["passed"] else "**FAIL**"
                lines.append(
                    f"| {item['id']} | {item['description']} | {item['check']} {_short_value(item['value'])} | {status} | {item['detail']} |"
                )
        if exact:
            lines.append("")
            lines.append("| Check | Value | Status | Detail |")
            lines.append("|---|---|---|---|")
            for item in exact:
                status = "pass" if item["passed"] else "**FAIL**"
                lines.append(
                    f"| {item['check']} | {_short_value(item['value'])} | {status} | {item['detail']} |"
                )
        error = case_result.get("error")
        if error:
            lines.append("")
            lines.append("Endpoint error:")
            lines.append("")
            lines.append(_pre(error))
        lines.append("")
        lines.append("Prompt:")
        lines.append("")
        lines.append(_pre(case_result["prompt"]))
        lines.append("")
        lines.append("Output:")
        lines.append("")
        lines.append(_pre(case_result["output"]))
    return "\n".join(lines).rstrip("\n") + "\n"


def _short_value(value, limit=120):
    if isinstance(value, list):
        value = ", ".join(str(item) for item in value)
    text = str(value).replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return "`" + text + "`" if text else ""
