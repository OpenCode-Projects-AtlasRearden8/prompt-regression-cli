# prompt-regression-cli

Engineering-lite prompt regression harness for prompt builders, by **Asdale Dynamics, LLC**.

Store prompt variants as versioned template files, define fixed test cases in YAML, run them
against any OpenAI-compatible endpoint (Ollama included, config file only — no API keys in
files), score every output against rubrics or exact checks, and diff rubric results between
runs. You finish with a pass/fail report in plain Markdown and JSON that can live in git,
right next to the prompts it graded.

Think of it as "CI smoke tests for prompts": small, local-first, boring on purpose, and
explained like a friend would.

## What problem does this solve?

You tweak a prompt. It works better on Tuesday's message. It quietly breaks Thursday's.
`prompt-regression run` re-asks a fixed batch of test questions after every change and files
a report, so regressions get caught before your users catch them.

- **Prompt variants** live as versioned files: `prompts/support-reply/v1.md`, `v2.md`, ...
  The highest number is the latest. Templates use `{variables}` from the test case
  (write literal braces as `{{` and `}}`).
- **Test cases** are fixed YAML: which variant, which version, the variables to inject, and
  what a good answer must satisfy.
- **Scoring** is deterministic: exact string/regex/word-count checks plus named rubric
  items. No judge model, no flaky LLM-grades-LLM.
- **Reports** are Markdown + JSON pairs under `reports/`, meant to be committed.
- **Diffing** compares two runs and tells you which rubric items got fixed or regressed.

## Quick start (Ollama, zero keys)

```bash
pip install .

# start Ollama with any model you like
ollama run llama3.2    # or whatever the config file names

prompt-regression check    # validate config, templates, and cases (no model call)
prompt-regression list     # see variants, versions, and cases
prompt-regression run      # run the suite, save reports/
prompt-regression diff latest  # compare the two most recent runs
```

The bundled example config `prompt-regression.yaml` points at
`http://localhost:11434/v1` (Ollama's OpenAI-compatible endpoint).

Any other OpenAI-compatible server works too — just change `endpoint.base_url`
(LM Studio: `http://localhost:1234/v1`, llama.cpp server, vLLM, text-generation-webui...
even api.openai.com, though then set `api_key_env` so the key comes from the environment).

## Project layout

```
prompt-regression.yaml        suite config (endpoint, variants, case files, reports dir)
prompts/
  support-reply/
    v1.md                     early draft (kept on purpose)
    v2.md                     latest version
cases/
  support.yaml                fixed test cases
  release-notes.yaml
reports/                      pass/fail reports (commit them)
```

## Config file reference (`prompt-regression.yaml`)

```yaml
endpoint:
  base_url: http://localhost:11434/v1   # any OpenAI-compatible /v1 root
  model: llama3.2
  api_key_env: ""        # optional NAME of an env var holding a key; never put keys here
  timeout: 120
  temperature: 0.2

variants:
  support-reply: prompts/support-reply
  release-notes: prompts/release-notes

cases:
  - cases/support.yaml
  - cases/release-notes.yaml

reports_dir: reports      # default
```

## Test case reference

```yaml
- id: angry-broken-clip          # unique id
  variant: support-reply         # name from the config's variants mapping
  version: 2                     # optional; omit for the latest version
  description: Optional human note, shown in reports.
  variables:                     # injected into the template's {placeholders}
    customer_name: Jordan
    issue: the pen clip snapping off in the first week
    message: "..."
  expect:
    # exact checks (no id needed)
    max_words: 75
    not_contains: [refund, "you should have"]
    # named rubric items (id + description show up in reports and diffs)
    rubric:
      - id: apology
        description: Apologizes using the word "sorry"
        contains_all: sorry
      - id: sign-off
        ends_with: "- Pen & Pencil Co."
```

Available checks (usable as exact checks or inside rubric items):

| Check | Value | Passes when the output... |
|---|---|---|
| `equals` | string | equals it (trimmed) |
| `contains` | string or list | contains every listed substring |
| `contains_all` | string or list | contains every listed substring |
| `contains_any` | string or list | contains at least one substring |
| `not_contains` | string or list | contains none of the substrings |
| `regex` | string | matches the pattern with `re.search` |
| `starts_with` | string | starts with it (trimmed) |
| `ends_with` | string | ends with it (trimmed) |
| `min_words` | integer | has at least N words |
| `max_words` | integer | has at most N words |

A case passes only when **every** exact check and every rubric item passes.
`contains`-style checks are case-sensitive on purpose: ambiguity should be your choice,
not an accident.

## Commands

```bash
prompt-regression run [config]      # run cases, score, save reports/<suite>-<timestamp>.json+.md
  --variant support-reply           # only cases for one variant (repeatable)
  --cases cases/support.yaml        # override case files
  --base-url http://127.0.0.1:8000/v1 --model qwen2.5:3b   # endpoint overrides
  --suite support-reply-v2          # name the run for diffing
  --dry-run                         # render prompts + list checks, call nothing
  --no-save                         # skip the report files

prompt-regression check [config]    # validate everything; no endpoint call; exit 2 on problems
prompt-regression list [config]     # show variants, versions, and cases

prompt-regression diff latest                   # prev vs new for this config's suite
prompt-regression diff <suite>                  # prev vs newest of that suite
prompt-regression diff reports/a.json reports/b.json     # explicit pairs
prompt-regression diff --fail-on-regression     # exit 1 if any rubric item went pass -> fail
```

Diff output highlights every rubric item whose pass state changed between runs, plus cases
that were added or removed — the human-readable changelog for your prompt behavior.

Exit codes: `0` everything passed, `1` failures (or a regression with `--fail-on-regression`),
`2` config/template/case errors. Wired straight into CI.

## A/B testing two versions

Pin versions in two case files (or use `version: 1` / `version: 2` fields), run each with
its own `--suite`, then diff the two report files:

```bash
prompt-regression run --suite support-v1   # case file where version: 1 is pinned
prompt-regression run --suite support-v2   # case file on the latest version
prompt-regression diff reports/support-v2-*.json reports/support-v1-*.json --fail-on-regression
```

## Keeping reports in git

Every run writes `<suite>-<UTC timestamp>.json` and `.md` next to your prompts. The JSON is
the machine-readable source of truth for `diff` and CI; the Markdown is what you read in a
pull request. Both are small, diff-friendly, and meant to be committed.

## Running against the mock (no model installed)

The pytest suite includes a tiny OpenAI-compatible mock server, so you can verify the whole
pipeline offline:

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
python -m prompt_regression_cli --help
python -m prompt_regression_cli check
```

## Development

```bash
pip install -e ".[dev]"
python -m pytest tests/
```

- Python 3.9+ (developed on 3.13), only runtime dependency is PyYAML.
- No telemetry, no accounts, no API keys stored anywhere; prompts and reports stay on disk.

## Ideas that are deliberately out of scope

LLM-as-judge scoring, embeddings similarity, prompt auto-tuning, cloud dashboards.
If you need those, you need a bigger tool. This one just says pass or fail.

## Credits and license

Built and maintained by [Asdale Dynamics, LLC](https://dylanasdale.github.io) — plain-English
AI education, books, and practical tools. Part of the toolchain behind *The Massive AI Manual*.

MIT licensed; see [LICENSE](LICENSE). Copyright (c) 2026 Asdale Dynamics, LLC.
