import argparse
import sys
from pathlib import Path

from . import __version__
from . import report as report_mod
from . import diff as diff_mod
from .cases import load_cases
from .config import EndpointConfig, load_config
from .errors import ConfigError, PromptRegressionError
from .runner import ChatClient
from .scoring import CHECK_KEYS, evaluate_expect
from .templates import Variant

DEFAULT_CONFIG_NAME = "prompt-regression.yaml"
DEFAULT_SUITE = "suite"
_STATUS_ICON = {"pass": "PASS", "fail": "FAIL", "error": "ERROR"}


def build_parser():
    parser = argparse.ArgumentParser(
        prog="prompt-regression",
        description=(
            "Engineering-lite prompt regression harness: versioned prompt variants, fixed YAML "
            "test cases, any OpenAI-compatible endpoint (including Ollama), rubric/exact scoring, "
            "and git-friendly pass/fail reports."
        ),
    )
    parser.add_argument("--version", action="version", version=f"prompt-regression {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="send every case to the endpoint, score it, and save a report")
    run.add_argument(
        "config", nargs="?", default=DEFAULT_CONFIG_NAME, help=f"config file (default: {DEFAULT_CONFIG_NAME})"
    )
    run.add_argument("--variant", action="append", default=[], help="only run cases for this variant (repeatable)")
    run.add_argument("--cases", nargs="*", default=None, help="override the case files from the config")
    run.add_argument("--base-url", default=None, help="override endpoint.base_url")
    run.add_argument("--model", default=None, help="override endpoint.model")
    run.add_argument(
        "--api-key-env", default=None, help="override endpoint.api_key_env (name of an env var, never a key)"
    )
    run.add_argument("--timeout", type=int, default=None, help="override endpoint timeout in seconds")
    run.add_argument("--suite", default=None, help="suite name for the saved report (default: config file stem)")
    run.add_argument("--report-dir", default=None, help="override reports_dir")
    run.add_argument("--limit", type=int, default=None, help="only run the first N cases")
    run.add_argument("--no-save", action="store_true", help="do not write a report file")
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="render prompts and list checks without contacting the endpoint",
    )

    check = sub.add_parser("check", help="validate config, variants, templates, and cases (no endpoint call)")
    check.add_argument("config", nargs="?", default=DEFAULT_CONFIG_NAME)

    listing = sub.add_parser("list", help="list prompt variants and test cases")
    listing.add_argument("config", nargs="?", default=DEFAULT_CONFIG_NAME)

    diff = sub.add_parser("diff", help="compare rubric/exact results between two reports")
    diff.add_argument(
        "references",
        nargs="*",
        default=[],
        help="'latest' (prev vs newest), or two of: 'latest', 'prev', suite name, report .json path",
    )
    diff.add_argument(
        "--config",
        default=DEFAULT_CONFIG_NAME,
        help=f"config file, used to resolve 'prev'/'latest'/suite names (default: {DEFAULT_CONFIG_NAME})",
    )
    diff.add_argument("--out", default=None, help="write the diff to this file instead of stdout")
    diff.add_argument("--fail-on-regression", action="store_true", help="exit 1 if any check regressed")
    return parser


def load_variants(config):
    return {name: Variant(name, config.root / directory) for name, directory in config.variants.items()}


def filter_cases(cases, variant_filter, limit):
    matching = [case for case in cases if not variant_filter or case.variant in variant_filter]
    if limit is not None:
        matching = matching[:limit]
    if not matching:
        note = f" for variant(s) {sorted(variant_filter)}" if variant_filter else ""
        raise ConfigError(f"No test cases{note}")
    return matching


def resolve_case_files(config, override):
    if override is None:
        return config.case_files
    files = []
    for item in override:
        path = Path(item)
        if not path.is_file():
            path = config.root / path
        if not path.is_file():
            raise ConfigError(f"Case file not found: {item}")
        files.append(path)
    return files


def override_endpoint(base, args):
    endpoint = EndpointConfig(
        base_url=base.base_url,
        model=base.model,
        api_key_env=base.api_key_env,
        timeout=base.timeout,
        temperature=base.temperature,
    )
    if args is None:
        return endpoint
    if args.base_url:
        endpoint.base_url = str(args.base_url).rstrip("/")
    if args.model:
        endpoint.model = args.model
    if args.api_key_env:
        endpoint.api_key_env = args.api_key_env
    if args.timeout:
        endpoint.timeout = args.timeout
    return endpoint


def cmd_check(args):
    loaded = load_config(args.config)
    variants = load_variants(loaded)
    cases = load_cases(loaded.case_files)
    rendered = 0
    for case in cases:
        if case.variant not in variants:
            raise ConfigError(f"Case '{case.id}' uses unknown variant '{case.variant}'")
        variants[case.variant].render(case.version, case.variables)
        rendered += 1
        unknown = [key for key in case.expect if key != "rubric" and key not in CHECK_KEYS]
        if unknown:
            raise ConfigError(f"Case '{case.id}' has unsupported expect keys {unknown}")
    print(f"Config OK: {loaded.path}")
    for name, variant in variants.items():
        print(f"Variant {name}: {', '.join(variant.version_ids)} (latest v{variant.latest})")
    print(f"Cases OK: {len(cases)} case(s); rendered {rendered} prompt(s); endpoint not contacted")
    return 0


def cmd_list(args):
    loaded = load_config(args.config)
    variants = load_variants(loaded)
    cases = load_cases(loaded.case_files)
    for name, variant in variants.items():
        versions = ", ".join(
            f"v{number}{' (latest)' if number == variant.latest else ''}" for number in sorted(variant.versions)
        )
        print(f"variant {name}: {versions}")
        print(f"  directory: {variant.directory}")
    print()
    for case in cases:
        version = ""
        if case.variant in variants:
            version = f"@v{variants[case.variant].resolve(case.version)}"
        checks = len(case.expect) - (1 if "rubric" in case.expect else 0) + len(case.rubric)
        print(f"case {case.id}: {case.variant}{version} [{case.source}] ({checks} check(s))")
    return 0


def cmd_run(args):
    loaded = load_config(args.config)
    variants = load_variants(loaded)
    case_files = resolve_case_files(loaded, args.cases)
    cases = filter_cases(load_cases(case_files), set(args.variant), args.limit)
    endpoint = override_endpoint(loaded.endpoint, args)
    suite = args.suite or loaded.path.stem
    reports_dir = Path(args.report_dir) if args.report_dir else loaded.reports_dir

    plan = []
    for case in cases:
        if case.variant not in variants:
            raise ConfigError(f"Case '{case.id}' uses variant '{case.variant}' which is not in the config")
        variant = variants[case.variant]
        version = variant.resolve(case.version)
        prompt = variant.render(version, case.variables)
        plan.append((case, variant, version, prompt))

    if args.dry_run:
        for case, _variant, version, prompt in plan:
            print(f"--- {case.id} ({case.variant}@v{version}) ---")
            print(prompt)
            print("checks:")
            for key, value in case.expect.items():
                if key != "rubric":
                    print(f"  - {key}: {value}")
            for item in case.rubric:
                print(f"  - rubric:{item.id}: {item.check}={item.value!r}")
        print(
            f"[dry-run] {len(plan)} case(s) rendered; endpoint {endpoint.base_url} "
            f"(model: {endpoint.model}) not contacted"
        )
        return 0

    client = ChatClient(endpoint)
    print(f"Endpoint: {endpoint.base_url} (model: {endpoint.model})")
    results = []
    for case, _variant, version, prompt in plan:
        output = None
        error = None
        try:
            output = client.complete([{"role": "user", "content": prompt}])
        except PromptRegressionError as exc:
            error = str(exc)
        exact, rubric = evaluate_expect(case.expect, output, case.rubric) if error is None else ([], [])
        results.append(
            report_mod.build_case_result(case, case.variant, version, prompt, output, exact, rubric, error)
        )
        total = len(exact) + len(rubric)
        passed = sum(1 for item in exact + rubric if item.passed)
        score = f"{passed}/{total}" if total else "n/a"
        print(f"[{_STATUS_ICON[results[-1]['status']]}] {case.id} ({case.variant}@v{version}) score {score}")

    report = report_mod.build_report(
        suite=suite,
        created_utc=report_mod.utc_stamp_iso(),
        endpoint={"base_url": endpoint.base_url, "model": endpoint.model},
        variant_versions={case.variant: f"v{version}" for case, _v, version, _p in plan},
        case_results=results,
    )
    if not args.no_save:
        json_path, md_path = report_mod.save_report(reports_dir, report, report_mod.report_basename(suite))
        print(f"Report: {json_path} (+ .md; keep both in git)")
    summary = report["summary"]
    verdict = "PASS" if summary["status"] == "pass" else "FAIL"
    message = (
        f"{verdict}: {summary['cases_passed']}/{summary['cases']} cases, "
        f"{summary['checks_passed']}/{summary['checks_total']} checks"
    )
    if summary["cases_errored"]:
        message += f", {summary['cases_errored']} error(s)"
    print(message)
    return 0 if summary["status"] == "pass" else 1


def _resolve_token(token, config):
    lowered = token.lower()
    if lowered == "latest":
        suite = config.path.stem
        return report_mod.load_reports(config.reports_dir, suite)[-1]
    if lowered == "prev":
        suite = config.path.stem
        reports = report_mod.load_reports(config.reports_dir, suite)
        if len(reports) < 2:
            raise ConfigError(
                f"Fewer than two saved reports for suite '{suite}' in {config.reports_dir}; cannot resolve 'prev'"
            )
        return reports[-2]
    if token.lower().endswith(".json") and Path(token).is_file():
        return None, report_mod.load_report(token)
    reports = report_mod.load_reports(config.reports_dir, token)
    if not reports:
        raise ConfigError(
            f"Cannot resolve reference '{token}': not a report file and no saved reports for suite '{token}' "
            f"in {config.reports_dir}"
        )
    return reports[-1]


def cmd_diff(args):
    references = list(args.references)
    loaded = load_config(args.config)
    if not references:
        references = ["latest"]
    if len(references) > 2:
        raise ConfigError("diff takes at most two report references")
    if len(references) == 1:
        token = references[0]
        if token.lower() == "prev":
            raise ConfigError(
                "Cannot diff 'prev' alone; use 'latest' (compares the two most recent runs) or give two references"
            )
        if token.lower() == "latest":
            suite = loaded.path.stem
            (old_path, old_report), (new_path, new_report) = report_mod.latest_and_previous(
                loaded.reports_dir, suite
            )
        elif token.lower().endswith(".json") and Path(token).is_file():
            (old_path, old_report), (new_path, new_report) = report_mod.previous_and_report(token)
        else:
            suite = token
            (old_path, old_report), (new_path, new_report) = report_mod.latest_and_previous(
                loaded.reports_dir, suite
            )
    else:
        old_entry = _resolve_token(references[0], loaded)
        new_entry = _resolve_token(references[1], loaded)
        old_path, old_report = old_entry
        new_path, new_report = new_entry

    result = diff_mod.diff_reports(old_report, new_report)
    text = diff_mod.render_diff_markdown(result, old_path=old_path, new_path=new_path)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Diff written to {args.out}")
    else:
        print(text, end="")
    if args.fail_on_regression and result["total"]["regressed"] > 0:
        return 1
    return 0


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {"run": cmd_run, "check": cmd_check, "list": cmd_list, "diff": cmd_diff}
    handler = handlers.get(args.command)
    if handler is None:
        parser.error(f"unknown command {args.command}")
    try:
        return handler(args)
    except PromptRegressionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
