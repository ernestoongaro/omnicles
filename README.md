# Omni Content Validator CI

![Omni Content Validator](assets/logo.png)

CLI plus GitHub Actions support for running Omni Content Validator, keeping a history artifact, and surfacing new vs existing failures.

## Demo video

Watch the demo: https://screen.studio/share/OFqWgCI7

## CLI usage

Install locally with pipx:

```bash
pipx install -e .
```

Run:

```bash
omni-content-validator \
  --base-url https://ernesto.playground.exploreomni.dev \
  --model-id <MODEL_ID> \
  --api-key <API_KEY> \
  --branch-name <BRANCH_NAME>
```

Validate only labeled content:

```bash
omni-content-validator \
  --base-url https://ernesto.playground.exploreomni.dev \
  --model-id <MODEL_ID> \
  --api-key <API_KEY> \
  --labels Verified
```

Or use repeated label flags:

```bash
omni-content-validator \
  --base-url https://ernesto.playground.exploreomni.dev \
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

Supported config keys:

- `base_url`
- `model_id`
- `user_id`
- `branch_id`
- `branch_name`
- `labels`
- `include_personal_folders`
- `timeout`
- `fail_on_new_only`

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
- `OMNI_USER_ID`
- `OMNI_LABELS` (optional comma-separated label filter, for example `Verified,Sales`)
- `OMNI_INCLUDE_PERSONAL_FOLDERS`
- `OMNI_TIMEOUT` (optional request timeout in seconds)
- `OMNI_FAIL_ON_NEW_ONLY` (optional `true`/`false`)
- `OMNI_BRANCH_ID` (optional override if you already know the Omni branch UUID)
- `OMNI_BRANCH_NAME` (used to resolve the Omni branch UUID by name)

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

This repo includes live workflows for:

- `.github/workflows/actionlint.yml`
- `.github/workflows/release-please.yml`
- `.github/workflows/secret-scan.yml`

The content validator workflow is kept as an example in `.github/workflow-examples/content-validator.yml` so it does not run automatically in this repository. To enable it in your own repo, copy it to `.github/workflows/content-validator.yml`.

The content validator example is designed to run on pushes to `main`, pull requests, and manual dispatches. It downloads the latest history artifact from the default branch, runs the validator, uploads a new history artifact, creates a check run, and posts a PR comment for pull requests.

Recommended setup in your repo:

- Check in `.omni-content-validator.yml` with non-secret settings such as `base_url`, `model_id`, labels, and behavior flags.
- Configure `OMNI_API_KEY` as a GitHub Actions secret.
- Optionally set `OMNI_*` repo variables or secrets only when you want workflow-specific overrides on top of the checked-in config.

Supported GitHub env overrides:

- `OMNI_API_KEY` (secret)
- `OMNI_BASE_URL` (variable or secret)
- `OMNI_MODEL_ID` (variable or secret)
- `OMNI_USER_ID` (optional variable or secret)
- `OMNI_LABELS` (optional variable or secret, comma-separated)
- `OMNI_BRANCH_ID` (optional variable or secret)
- `OMNI_BRANCH_NAME` (optional variable or secret)
- `OMNI_TIMEOUT` (optional variable or secret)
- `OMNI_FAIL_ON_NEW_ONLY` (optional variable or secret)
- `OMNI_INCLUDE_PERSONAL_FOLDERS` (optional variable or secret)

### Testing the workflow

1. Copy `.github/workflow-examples/content-validator.yml` to `.github/workflows/content-validator.yml`.
2. Copy `.omni-content-validator.example.yml` to `.omni-content-validator.yml` and fill in your non-secret settings.
3. Add `OMNI_API_KEY` in GitHub repo settings, plus any optional override variables you want.
4. Push to `main` once (or run the workflow manually on `main`) to seed the history artifact.
5. Open a PR and confirm the check run plus PR comment show the validation results.

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
