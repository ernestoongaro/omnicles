# Omni Content Validator CI

![Omni Content Validator](assets/logo.png)

CLI + GitHub Action to run Omni Content Validator on pull requests, keep a history artifact, and surface new vs existing failures.

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
- `--issues-path` to point at the array of issues in the JSON response (dot path). By default, the CLI looks for `issues` arrays or the `content[].queries_and_issues[].issues` and `content[].dashboard_filter_issues` arrays.
- `--fail-on-new-only` to fail only when new issues appear vs history.
- `--auth-header` and `--auth-scheme` to override auth header formatting (defaults to `Authorization: Bearer <token>`).

Environment variables:

- `OMNI_BASE_URL`
- `OMNI_MODEL_ID`
- `OMNI_API_KEY`
- `OMNI_USER_ID`
- `OMNI_ISSUES_PATH`
- `OMNI_BRANCH_ID` (optional override if you already know the Omni branch UUID)
- `OMNI_BRANCH_NAME` (used to resolve the Omni branch UUID by name)

Example local env setup:

```bash
export OMNI_BASE_URL="https://ernesto.playground.exploreomni.dev"
export OMNI_MODEL_ID="..."
export OMNI_API_KEY="..."
export OMNI_USER_ID="..." # optional
```

## GitHub Action

The workflow in `.github/workflows/content-validator.yml` runs on PRs, downloads the latest history artifact from the default branch, runs the validator, uploads a new history artifact, creates a check run, and posts a PR comment.

Configure these in GitHub:

- `OMNI_API_KEY` (secret)
- `OMNI_BASE_URL` (variable or secret)
- `OMNI_MODEL_ID` (variable or secret)
- `OMNI_USER_ID` (optional variable or secret)

### Testing the workflow

1. Add the secrets/variables above in GitHub repo settings.
2. Run the workflow once on the default branch (via the Actions tab or a small commit) to seed the history artifact.
3. Open a PR and confirm the check run + PR comment show the validation results.

## Limitations

The content validator endpoint currently validates all content and does not support filters. That means the PR report may include unrelated failures. The workflow keeps a history artifact and highlights which issues are new vs previously seen to reduce noise.
