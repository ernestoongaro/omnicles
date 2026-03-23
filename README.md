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

Optional flags:

- `--user-id` to act on behalf of a user for org API keys.
- `--branch-name` to resolve and validate against an Omni branch with the same name.
- `--branch-id` to validate against a specific Omni branch UUID.
- `--include-personal-folders` to include personal folders in the validation search.
- `--issues-path` to point at the array of issues in the JSON response (dot path). By default, the CLI looks for `issues` arrays or the `content[].queries_and_issues[].issues` and `content[].dashboard_filter_issues` arrays.
- `--fail-on-new-only` to fail only when new issues appear vs history.
- `--auth-header` and `--auth-scheme` to override auth header formatting (defaults to `Authorization: Bearer <token>`).

Environment variables:

- `OMNI_BASE_URL`
- `OMNI_MODEL_ID`
- `OMNI_API_KEY`
- `OMNI_USER_ID`
- `OMNI_INCLUDE_PERSONAL_FOLDERS`
- `OMNI_ISSUES_PATH`
- `OMNI_BRANCH_ID` (optional override if you already know the Omni branch UUID)
- `OMNI_BRANCH_NAME` (used to resolve the Omni branch UUID by name)

Example local env setup:

```bash
export OMNI_BASE_URL="https://ernesto.playground.exploreomni.dev"
export OMNI_MODEL_ID="..."
export OMNI_API_KEY="..."
export OMNI_USER_ID="..." # optional
export OMNI_INCLUDE_PERSONAL_FOLDERS="true" # optional
```

## GitHub Actions

This repo includes live workflows for:

- `.github/workflows/actionlint.yml`
- `.github/workflows/release-please.yml`

The content validator workflow is kept as an example in `.github/workflow-examples/content-validator.yml` so it does not run automatically in this repository. To enable it in your own repo, copy it to `.github/workflows/content-validator.yml`.

The content validator example is designed to run on pull requests and manual dispatches. It downloads the latest history artifact from the default branch, runs the validator, uploads a new history artifact, creates a check run, and posts a PR comment for pull requests.

Configure these in GitHub:

- `OMNI_API_KEY` (secret)
- `OMNI_BASE_URL` (variable or secret)
- `OMNI_MODEL_ID` (variable or secret)
- `OMNI_USER_ID` (optional variable or secret)
- `OMNI_INCLUDE_PERSONAL_FOLDERS` (optional variable or secret)

### Testing the workflow

1. Copy `.github/workflow-examples/content-validator.yml` to `.github/workflows/content-validator.yml`.
2. Add the secrets/variables above in GitHub repo settings.
3. Run the workflow manually on your default branch once to seed the history artifact.
4. Open a PR and confirm the check run plus PR comment show the validation results.

## Releases

Releases are managed in this repo by `.github/workflows/release-please.yml`.

- Merge changes into `main` with conventional commit messages such as `feat:`, `fix:`, or `chore:` so Release Please can infer the next version and changelog entries.
- Set `RELEASE_PLEASE_TOKEN` to a GitHub PAT if you want other workflows to run on release PRs. If that secret is not configured, the workflow falls back to the default GitHub token.

## Limitations

The content validator endpoint currently validates all content and does not support filters. That means the PR report may include unrelated failures. The example workflow keeps a history artifact and highlights which issues are new vs previously seen to reduce noise.

## Disclaimer

This project is community-built and not an official Omni release. Use it at your own risk and review the code before running it in production.
