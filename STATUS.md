# STATUS.md — prompt-regression-cli

Last updated: 2026-10-31. Built and verified by Asdale Dynamics, LLC's repo tooling.

## What was built

`prompt-regression-cli` — an engineering-lite prompt regression harness for prompt builders:

- **Versioned prompt variants**: each variant is a directory of `v1.md`, `v2.md`, ... files;
  the highest number is the latest. Templates take `{variables}` from test cases, and literal
  braces can be written as `{{`/`}}`.
- **Fixed YAML test cases**: each case pins a variant (and optionally an exact template
  version), injects variables, and declares expectations — deterministic exact checks
  (`equals`, `contains_all`, `not_contains`, `regex`, `max_words`, `starts_with`,
  `ends_with`, ...) plus named **rubric items** (id + description + one check) that show up
  in reports and diffs.
- **Any OpenAI-compatible endpoint**: config-file driven (`endpoint.base_url`, `model`),
  Ollama-friendly (`http://localhost:11434/v1`), no API keys stored in files — an optional
  `api_key_env` names an environment variable instead. Stdlib-only HTTP client; only runtime
  dependency is PyYAML.
- **Pass/fail reports in git**: every run writes a JSON (machine truth) + Markdown (human
  readable) pair under `reports/`; `run` exits 0/1/2 so CI can gate on it.
- **Diff between runs**: `prompt-regression diff` compares two reports and flags every
  rubric/exact check that regressed or got fixed, including cases added/removed, plus a
  `--fail-on-regression` CI mode.
- **Commands**: `run` (also `--dry-run`, `--limit`, `--variant`, endpoint overrides,
  `--suite`, `--no-save`), `check` (validate everything with no endpoint call), `list`,
  `diff`, `--help`/`--version`.

Package layout:

```
prompt_regression_cli/{cli,config,cases,templates,scoring,runner,report,diff,errors}.py
prompts/{support-reply,release-notes}/v1.md,v2.md       example variants
cases/{support,release-notes}.yaml                     example test cases
prompt-regression.yaml                                 example suite config
reports/                                               example run pair + example-diff.md
tests/                                                 pytest suite with mock endpoints
```

## How to run it

```bash
pip install .            # or: pip install -e ".[dev]"

prompt-regression check                  # validate the suite, no endpoint needed
prompt-regression run                    # needs Ollama (or any OpenAI-compatible server)
prompt-regression run --dry-run          # render prompts + checks only
prompt-regression diff latest            # compare the two most recent runs
```

Point `prompt-regression.yaml` at your Ollama/LM Studio/vLLM base_url and model, then:

```bash
prompt-regression run --suite my-suite
prompt-regression diff latest --fail-on-regression
```

The Python API/CLI can also be driven from code: `from prompt_regression_cli.cli import main`.

## Verification results (2026-10-31)

- `python3 -m pytest tests/ -q` → **92 passed**, including end-to-end runs against a mock
  OpenAI-compatible server (threaded local HTTP server): successful completions, malformed
  responses, HTTP 500, connection-refused with an Ollama hint, and full run→report→diff
  flows. Exit-code behavior (0 pass / 1 fail / 2 config error) is covered.
- `prompt-regression check` → valid: 2 variants (v1, v2 each), 3 cases, 15 checks,
  endpoint not contacted.
- `prompt-regression run --dry-run` → renders all 3 prompts and lists all checks.
- Live pipeline demo against the in-process mock server: two `example` runs saved to
  `reports/` (run 1: 3/3 cases; run 2: a degraded reply for one case → 2/3) and
  `reports/example-diff.md` flags exactly the two regressed rubric items. These files are
  committed as sample artifacts.
- Editable install verified: `pip install -e . --no-build-isolation`; console script
  `prompt-regression` and `python3 -m prompt_regression_cli` both work.

## Known gaps / deliberate non-goals

- No LLM-as-judge or embedding-similarity scoring — scoring is deterministic string checks
  by design (flaky judge models are out of scope).
- No retries/backoff on endpoint errors (a failed call marks the case errored; rerun to retry).
- Diffing assumes case ids remain comparable between runs; renamed ids show as removed/added.
- Report timestamps are second-resolution in Markdown headers; JSON filenames carry
  microsecond precision to avoid collisions.
- No `prompt-regression init` scaffolder yet; copy the bundled example layout instead.
- Ollama specifically must have its OpenAI-compatible endpoint enabled (it is by default on
  port 11434); `/api/generate`-style native endpoints are not supported.
- Windows console colors/encoding are untested; output is plain text and UTF-8.

## License and credits

MIT — Copyright (c) 2026 Asdale Dynamics, LLC (see `LICENSE`). Built as part of the
Asdale Dynamics, LLC open-source prompt tooling for *The Massive AI Manual*
(dylanasdale.github.io). No secrets, API keys, or personal data are stored in this repo;
keys, when needed, come from environment variables via `api_key_env`.
