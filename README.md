# Omni Content Validator CI

> [!IMPORTANT]
> **This project is archived and no longer maintained.** It has been superseded by
> [**OmniFlow**](https://github.com/exploreomni/OmniFlow) — an open-source, security-first
> CI/CD validation and deployment companion for the Omni semantic layer.
> Please use OmniFlow for new projects. This repository remains available as a read-only reference.

![Omni Content Validator](assets/logo.png)

CLI plus GitHub Actions support for running two Omni validators, keeping history artifacts, and surfacing new vs existing failures on every PR:

- **`omni-content-validator`** — validates dashboard queries and filter configurations.
- **`omni-model-validator`** — validates the semantic model YAML (views, topics, joins, fields). This is the most important check to run on model-editing PRs.

## Demo video

Watch the demo: https://screen.studio/share/OFqWgCI7

## CLI usage

Install locally with pipx:

```bash
pipx install git+https://github.com/ernestoongaro/omnicles.git
```

Or in editable mode from a local clone:

```bash
pipx install -e .
```

### omni-model-validator

Validates the Omni semantic model — views, topics, joins, and fields — against the YAML. Best run on every PR that touches model files.

```bash
omni-model-validator \
  --base-url https://your-org.omniapp.co \
  --model-id <MODEL_ID> \
  --api-key <API_KEY> \
  --branch-name <BRANCH_NAME>
```

By default the validator exits with code `1` if any issues exist (errors or warnings). Use `--errors-only` to treat warnings as informational only:

```bash
omni-model-validator \
  --base-url https://your-org.omniapp.co \
  --model-id <MODEL_ID> \
  --api-key <API_KEY> \
  --errors-only
```

Optional flags:

- `--branch-name` to resolve and validate against an Omni branch by name.
- `--branch-id` to validate against a specific Omni branch UUID.
- `--errors-only` to ignore warnings and only fail on errors.
- `--fail-on-new-only` to fail only when new issues appear vs history.

### omni-content-validator

Validates dashboard queries and filter configurations across your Omni content.

```bash
omni-content-validator \
  --base-url https://your-org.omniapp.co \
  --model-id <MODEL_ID> \
  --api-key <API_KEY> \
  --branch-name <BRANCH_NAME>
```

Validate only labeled content:

```bash
omni-content-validator \
  --base-url https://your-org.omniapp.co \
  --model-id <MODEL_ID> \
  --api-key <API_KEY> \
  --labels Verified
```

Or use repeated label flags:

```bash
omni-content-validator \
  --base-url https://your-org.omniapp.co \
  --model-id <MODEL_ID> \
  --api-key <API_KEY> \
  --label Verified \
  --label Sales
```

Optional flags:

- `--user-id` to act on behalf of a user for org API keys.
- `--branch-name` to resolve and validate against an Omni branch with the same name.
- `--branch-id` to validate against a specific Omni branch UUID.
- `--labels` to filter validation results by one or more Omni labels (comma-separated, for example `--labels Verified,Sales`).
- `--label` as a repeatable form of the same filter (for example `--label Verified --label Sales`).
- `--include-personal-folders` to include personal folders in the validation search.
- `--fail-on-new-only` to fail only when new issues appear vs history.

If `.omni-content-validator.yml` exists in the current working directory, the CLI auto-loads it.

## Config File

Copy `.omni-content-validator.example.yml` to `.omni-content-validator.yml` and keep non-secret defaults there.

Both `omni-model-validator` and `omni-content-validator` read from the same config file.

Supported config keys:

- `base_url`
- `model_id`
- `user_id`
- `branch_id`
- `branch_name`
- `labels` _(content validator only)_
- `include_personal_folders` _(content validator only)_
- `timeout`
- `fail_on_new_only`
- `errors_only` _(model validator only)_

Secrets such as the API key are intentionally not supported in the config file. Keep those in environment variables or GitHub Actions secrets.

Resolution order:

1. CLI flags
2. `OMNI_*` environment variables
3. `.omni-content-validator.yml`
4. built-in defaults

Supported environment overrides:

- `OMNI_BASE_URL`
- `OMNI_MODEL_ID`
- `OMNI_API_KEY`
- `OMNI_BRANCH_ID` (optional, if you already know the Omni branch UUID)
- `OMNI_BRANCH_NAME` (used to resolve the Omni branch UUID by name)
- `OMNI_TIMEOUT` (optional request timeout in seconds)
- `OMNI_FAIL_ON_NEW_ONLY` (optional `true`/`false`)
- `OMNI_ERRORS_ONLY` (optional `true`/`false`, model validator only)
- `OMNI_USER_ID` (optional, content validator only)
- `OMNI_LABELS` (optional comma-separated label filter, content validator only, e.g. `Verified,Sales`)
- `OMNI_INCLUDE_PERSONAL_FOLDERS` (optional, content validator only)

Minimal local setup with a checked-in config file:

```bash
export OMNI_API_KEY="..."
omni-content-validator
```

Ad hoc env-only setup still works:

```bash
export OMNI_BASE_URL="https://ernesto.playground.exploreomni.dev"
export OMNI_MODEL_ID="..."
export OMNI_API_KEY="..."
export OMNI_USER_ID="..." # optional
export OMNI_LABELS="Verified,Sales" # optional
export OMNI_INCLUDE_PERSONAL_FOLDERS="true" # optional
export OMNI_FAIL_ON_NEW_ONLY="true" # optional
omni-content-validator
```

## Secret Safety

This repo now has two guardrails against accidentally committing keys:

- A local `pre-commit` hook using the official `gitleaks` hook.
- A GitHub Actions backstop in `.github/workflows/secret-scan.yml` that scans every push and pull request.

Set up the local hook once per clone:

```bash
python3 -m pip install pre-commit
pre-commit install
```

Run it manually across the repo at any time:

```bash
pre-commit run --all-files
```

Operationally, secrets should still live in environment variables or GitHub Actions secrets, never in tracked files. `.env` files and `.omni-content-validator/` artifacts are already ignored in `.gitignore`. `.omni-content-validator.yml` is intended to be checked in, so keep secrets out of it.

For server-side blocking before a push lands, enable GitHub Secret Scanning and Push Protection in the repository settings. That setting is outside the repo, so it is not something this codebase can enforce by itself.

## GitHub Actions

This repo ships reusable composite actions so your workflow stays minimal:

### Model validator (recommended for model PRs)

```yaml
# .github/workflows/model-validator.yml
name: Model Validator
on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

permissions:
  actions: read
  checks: write
  contents: read
  pull-requests: write

jobs:
  validate-model:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: ernestoongaro/omnicles/.github/actions/model-validator@main
        with:
          api-key: ${{ secrets.OMNI_API_KEY }}
```

The action automatically detects the PR branch via `github.head_ref`. Optional inputs:

| Input | Default | Description |
|---|---|---|
| `api-key` | _(required)_ | Omni API key secret |
| `branch-name` | `${{ github.head_ref }}` | Omni branch to validate |
| `fail-on-new-only` | `false` | Only fail on new issues vs history |
| `errors-only` | `false` | Ignore warnings; only fail on errors |
| `history-artifact-name` | `model-validator-history` | Artifact name for history persistence |
| `python-version` | `3.11` | Python version |

Outputs available for downstream steps: `total-issues`, `new-issues`, `error-count`, `warning-count`.

### Content validator

Copy `.github/workflow-examples/content-validator.yml` to `.github/workflows/content-validator.yml` in your repo.

### Recommended setup

1. Copy `.omni-content-validator.example.yml` to `.omni-content-validator.yml` and fill in non-secret settings (`base_url`, `model_id`, and any flags).
2. Add `OMNI_API_KEY` as a GitHub Actions secret.
3. Push to `main` once (or trigger the workflow manually) to seed the history artifact.
4. Open a PR — the action posts a comment with new, existing, and resolved issues.

This repo includes live workflows for its own CI:

- `.github/workflows/actionlint.yml`
- `.github/workflows/release-please.yml`
- `.github/workflows/secret-scan.yml`

## Releases

Releases are managed in this repo by `.github/workflows/release-please.yml`.

- Merge changes into `main` with conventional commit messages such as `feat:`, `fix:`, or `chore:` so Release Please can infer the next version and changelog entries.
- Set `RELEASE_PLEASE_TOKEN` to a GitHub PAT if you want other workflows to run on release PRs. If that secret is not configured, the workflow falls back to the default GitHub token.

## Limitations

The content validator endpoint currently validates all content and does not support filters server-side.

This CLI also fetches content metadata from `/api/v1/content` to enrich issue records with document ownership information. Reports now include `document_owner` when Omni returns an owner object for the matched content.

When you pass `--labels` or `OMNI_LABELS`, the same content API lookup is reused to filter the validator payload locally before extracting issues. That keeps reports and history scoped to the labeled subset, but Omni still validates the full model underneath.

Without label filtering, the PR report may include unrelated failures. The example workflow keeps a history artifact and highlights which issues are new vs previously seen to reduce noise.

## Disclaimer

This project is community-built and not an official Omni release. Use it at your own risk and review the code before running it in production.
