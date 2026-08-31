import argparse
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from omni_content_validator import cli


class FakeResponse:
    def __init__(self, payload, ok=True, status_code=200, text="OK"):
        self._payload = payload
        self.ok = ok
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


@contextlib.contextmanager
def temporary_workdir():
    original_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        try:
            yield tmpdir
        finally:
            os.chdir(original_cwd)


class ParseArgsTests(unittest.TestCase):
    def write_config(self, directory, content):
        path = os.path.join(directory, ".omni-content-validator.yml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content.lstrip())

    @mock.patch.dict(os.environ, {"OMNI_API_KEY": "secret"}, clear=True)
    def test_parse_args_uses_config_file_defaults(self):
        with temporary_workdir() as tmpdir:
            self.write_config(
                tmpdir,
                """
base_url: https://omni.example
model_id: model-1
branch_name: feature-branch
labels:
  - Verified
  - Sales
include_personal_folders: true
timeout: 45
fail_on_new_only: true
""",
            )

            args = cli._parse_args([])

        self.assertEqual(args.base_url, "https://omni.example")
        self.assertEqual(args.model_id, "model-1")
        self.assertEqual(args.api_key, "secret")
        self.assertEqual(args.branch_name, "feature-branch")
        self.assertEqual(args.labels, ["Verified", "Sales"])
        self.assertTrue(args.include_personal_folders)
        self.assertEqual(args.timeout, 45)
        self.assertTrue(args.fail_on_new_only)

    @mock.patch.dict(
        os.environ,
        {
            "OMNI_API_KEY": "secret",
            "OMNI_LABELS": "Sales,EMEA",
            "OMNI_TIMEOUT": "90",
            "OMNI_FAIL_ON_NEW_ONLY": "true",
        },
        clear=True,
    )
    def test_parse_args_prefers_env_over_config(self):
        with temporary_workdir() as tmpdir:
            self.write_config(
                tmpdir,
                """
base_url: https://omni.example
model_id: model-1
labels:
  - Verified
timeout: 45
fail_on_new_only: false
""",
            )

            args = cli._parse_args([])

        self.assertEqual(args.labels, ["Sales", "EMEA"])
        self.assertEqual(args.timeout, 90)
        self.assertTrue(args.fail_on_new_only)

    @mock.patch.dict(
        os.environ,
        {
            "OMNI_API_KEY": "secret",
            "OMNI_LABELS": "Sales",
            "OMNI_TIMEOUT": "90",
        },
        clear=True,
    )
    def test_parse_args_prefers_cli_over_env_and_config(self):
        with temporary_workdir() as tmpdir:
            self.write_config(
                tmpdir,
                """
base_url: https://omni.example
model_id: model-1
labels:
  - Verified
timeout: 45
""",
            )

            args = cli._parse_args(
                [
                    "--label",
                    "Finance",
                    "--label",
                    "Sales",
                    "--timeout",
                    "15",
                ]
            )

        self.assertEqual(args.labels, ["Finance", "Sales"])
        self.assertEqual(args.timeout, 15)

    @mock.patch.dict(
        os.environ,
        {
            "OMNI_API_KEY": "secret",
            "GITHUB_HEAD_REF": "feature/config-file",
        },
        clear=True,
    )
    def test_parse_args_expands_env_vars_in_config(self):
        with temporary_workdir() as tmpdir:
            self.write_config(
                tmpdir,
                """
base_url: https://omni.example
model_id: model-1
branch_name: ${GITHUB_HEAD_REF}
""",
            )

            args = cli._parse_args([])

        self.assertEqual(args.branch_name, "feature/config-file")

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_parse_args_rejects_unknown_config_keys(self):
        with temporary_workdir() as tmpdir:
            self.write_config(
                tmpdir,
                """
base_url: https://omni.example
model_id: model-1
unsupported_key: value
""",
            )

            with self.assertRaises(SystemExit) as exc:
                cli._parse_args([])

        self.assertIn("Unsupported keys", str(exc.exception))

    @mock.patch.dict(
        os.environ, {"OMNI_LABELS": "Verified, Sales, Verified"}, clear=True
    )
    def test_parse_args_uses_env_labels_when_cli_missing(self):
        with temporary_workdir():
            args = cli._parse_args([])
        self.assertEqual(args.labels, ["Verified", "Sales"])

    @mock.patch.dict(os.environ, {"OMNI_LABELS": "Ignored"}, clear=True)
    def test_parse_args_prefers_cli_labels_and_dedupes(self):
        with temporary_workdir():
            args = cli._parse_args(
                [
                    "--labels",
                    "Verified,Sales",
                    "--label",
                    "Sales",
                    "--label",
                    "Finance",
                ]
            )
        self.assertEqual(args.labels, ["Verified", "Sales", "Finance"])

    @mock.patch.dict(
        os.environ,
        {
            "OMNI_TIMEOUT": "90",
            "OMNI_FAIL_ON_NEW_ONLY": "true",
        },
        clear=True,
    )
    def test_parse_args_reads_env_backed_workflow_options(self):
        with temporary_workdir():
            args = cli._parse_args([])
        self.assertEqual(args.timeout, 90)
        self.assertTrue(args.fail_on_new_only)


class IssueIdentityTests(unittest.TestCase):
    def test_issue_identity_ignores_owner_and_labels_metadata(self):
        base_issue = {
            "message": "Broken field",
            "document_id": "1",
            "document_identifier": "dash-1",
            "document_name": "Revenue Dashboard",
            "issue_type": "query",
        }

        enriched_issue = {
            **base_issue,
            "document_labels": ["Verified"],
            "document_owner": {"id": "membership-1", "name": "Alice"},
        }

        self.assertEqual(
            cli._issue_identity(base_issue), cli._issue_identity(enriched_issue)
        )


class LabelFilteringTests(unittest.TestCase):
    def test_fetch_content_records_paginates(self):
        args = argparse.Namespace(
            base_url="https://omni.example",
            api_key="secret",
            labels=["Verified", "Sales"],
            user_id="user-1",
            branch_id="branch-1",
            include_personal_folders=True,
            timeout=30,
        )

        responses = [
            FakeResponse(
                {
                    "records": [{"identifier": "doc-1"}, {"identifier": "doc-2"}],
                    "pageInfo": {"nextCursor": "cursor-2"},
                }
            ),
            FakeResponse(
                {
                    "records": [{"identifier": "doc-2"}, {"identifier": "doc-3"}],
                    "pageInfo": {},
                }
            ),
        ]

        with mock.patch.object(cli.requests, "get", side_effect=responses) as get:
            records = cli._fetch_content_records(args)

        self.assertEqual(
            [record["identifier"] for record in records],
            ["doc-1", "doc-2", "doc-2", "doc-3"],
        )
        self.assertEqual(get.call_count, 2)
        self.assertEqual(
            get.call_args_list[0].args[0], "https://omni.example/api/v1/content"
        )
        self.assertEqual(
            get.call_args_list[0].kwargs["params"],
            {
                "include": "labels",
                "labels": "Verified,Sales",
                "userId": "user-1",
                "branch_id": "branch-1",
                "include_personal_folders": "true",
            },
        )
        self.assertEqual(
            get.call_args_list[1].kwargs["params"],
            {
                "include": "labels",
                "labels": "Verified,Sales",
                "cursor": "cursor-2",
                "userId": "user-1",
                "branch_id": "branch-1",
                "include_personal_folders": "true",
            },
        )

    def test_enrich_validator_payload_adds_owner_and_labels(self):
        payload = {
            "content": [
                {"identifier": "doc-1", "name": "Alpha"},
                {"identifier": "doc-2", "name": "Beta"},
            ]
        }
        content_records_by_identifier = {
            "doc-2": {
                "identifier": "doc-2",
                "owner": {"id": "membership-1", "name": "Alice"},
                "labels": [{"name": "Verified"}],
            }
        }

        enriched = cli._enrich_validator_payload(payload, content_records_by_identifier)

        self.assertEqual(
            enriched["content"][1]["owner"],
            {"id": "membership-1", "name": "Alice"},
        )
        self.assertEqual(enriched["content"][1]["labels"], [{"name": "Verified"}])
        self.assertNotIn("owner", payload["content"][1])

    def test_filter_validator_payload_filters_content_by_identifier(self):
        payload = {
            "content": [
                {"identifier": "doc-1", "name": "Alpha"},
                {"identifier": "doc-2", "name": "Beta"},
            ],
            "meta": {"page": 1},
        }

        filtered = cli._filter_validator_payload(payload, {"doc-2"})

        self.assertEqual(filtered["content"], [{"identifier": "doc-2", "name": "Beta"}])
        self.assertEqual(filtered["meta"], {"page": 1})
        self.assertEqual(len(payload["content"]), 2)

    def test_collect_content_issues_includes_document_identifier_labels_and_owner(self):
        payload = {
            "content": [
                {
                    "document_id": "1",
                    "identifier": "dash-1",
                    "name": "Revenue Dashboard",
                    "type": "dashboard",
                    "url": "https://omni.example/documents/1",
                    "folder": {"name": "Finance", "path": "/Finance"},
                    "labels": [{"name": "Verified"}],
                    "owner": {"id": "membership-1", "name": "Alice"},
                    "queries_and_issues": [
                        {
                            "query_name": "Revenue by Month",
                            "query_presentation_id": "query-1",
                            "issues": [{"message": "Broken field"}],
                        }
                    ],
                }
            ]
        }

        issues = cli._collect_content_issues(payload)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["document_identifier"], "dash-1")
        self.assertEqual(issues[0]["document_labels"], ["Verified"])
        self.assertEqual(
            issues[0]["document_owner"], {"id": "membership-1", "name": "Alice"}
        )


class MainFlowTests(unittest.TestCase):
    @mock.patch.object(cli, "_write_json")
    @mock.patch.object(cli, "_fetch_content_records")
    @mock.patch.object(cli, "_fetch_validator_payload")
    @mock.patch.object(cli, "_load_json")
    def test_main_filters_results_and_resets_history_when_labels_change(
        self,
        load_json,
        fetch_validator_payload,
        fetch_content_records,
        write_json,
    ):
        fetch_validator_payload.return_value = {
            "content": [
                {
                    "document_id": "1",
                    "identifier": "dash-1",
                    "name": "Unverified Dashboard",
                    "queries_and_issues": [
                        {"query_name": "Q1", "issues": [{"message": "Old issue"}]}
                    ],
                },
                {
                    "document_id": "2",
                    "identifier": "dash-2",
                    "name": "Verified Dashboard",
                    "queries_and_issues": [
                        {"query_name": "Q2", "issues": [{"message": "Current issue"}]}
                    ],
                },
            ]
        }
        fetch_content_records.return_value = [
            {
                "identifier": "dash-2",
                "owner": {"id": "membership-1", "name": "Alice"},
                "labels": [{"name": "Verified"}],
            }
        ]
        load_json.return_value = {
            "labels": [],
            "issues": [{"id": "stale", "summary": "stale", "raw": {}}],
        }

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = cli.main(
                [
                    "--base-url",
                    "https://omni.example",
                    "--model-id",
                    "model-1",
                    "--api-key",
                    "secret",
                    "--labels",
                    "Verified",
                ]
            )

        self.assertEqual(exit_code, 1)
        report = write_json.call_args_list[0].args[1]
        history = write_json.call_args_list[1].args[1]
        self.assertEqual(report["labels"], ["Verified"])
        self.assertEqual(report["total_issues"], 1)
        self.assertEqual(report["new_issues"], 1)
        self.assertEqual(report["existing_issues"], 0)
        self.assertEqual(report["resolved_issues"], 0)
        self.assertEqual(history["labels"], ["Verified"])
        self.assertEqual(
            report["issues"][0]["raw"]["document_owner"],
            {"id": "membership-1", "name": "Alice"},
        )
        self.assertEqual(report["issues"][0]["raw"]["document_labels"], ["Verified"])
        self.assertIn("History labels changed", stdout.getvalue())

    @mock.patch.object(cli, "_write_json")
    @mock.patch.object(cli, "_fetch_content_records")
    @mock.patch.object(cli, "_fetch_validator_payload")
    @mock.patch.object(cli, "_load_json")
    def test_main_enriches_owner_without_labels(
        self,
        load_json,
        fetch_validator_payload,
        fetch_content_records,
        write_json,
    ):
        fetch_validator_payload.return_value = {
            "content": [
                {
                    "document_id": "2",
                    "identifier": "dash-2",
                    "name": "Revenue Dashboard",
                    "queries_and_issues": [
                        {"query_name": "Q2", "issues": [{"message": "Current issue"}]}
                    ],
                }
            ]
        }
        fetch_content_records.return_value = [
            {
                "identifier": "dash-2",
                "owner": {"id": "membership-2", "name": "Bob"},
            }
        ]
        load_json.return_value = {"labels": [], "issues": []}

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = cli.main(
                [
                    "--base-url",
                    "https://omni.example",
                    "--model-id",
                    "model-1",
                    "--api-key",
                    "secret",
                ]
            )

        self.assertEqual(exit_code, 1)
        report = write_json.call_args_list[0].args[1]
        self.assertEqual(
            report["issues"][0]["raw"]["document_owner"],
            {"id": "membership-2", "name": "Bob"},
        )


class ModelIssueTests(unittest.TestCase):
    def test_model_issue_summary_openapi_format(self):
        issue = {"message": "Field not found", "severity": "error", "view": "orders", "field": "total"}
        self.assertEqual(cli._model_issue_summary(issue), "orders.total: Field not found")

    def test_model_issue_summary_docs_format(self):
        issue = {"message": "No view found", "is_warning": False, "yaml_path": "blob_sales.topic"}
        self.assertEqual(cli._model_issue_summary(issue), "blob_sales.topic: No view found")

    def test_model_issue_summary_message_only(self):
        issue = {"message": "Something is wrong", "severity": "warning"}
        self.assertEqual(cli._model_issue_summary(issue), "Something is wrong")

    def test_issue_is_warning_openapi(self):
        self.assertTrue(cli._issue_is_warning({"severity": "warning"}))
        self.assertFalse(cli._issue_is_warning({"severity": "error"}))

    def test_issue_is_warning_docs_format(self):
        self.assertTrue(cli._issue_is_warning({"is_warning": True}))
        self.assertFalse(cli._issue_is_warning({"is_warning": False}))

    def test_issue_is_warning_defaults_false(self):
        self.assertFalse(cli._issue_is_warning({"message": "no severity field"}))


class ModelValidatorMainTests(unittest.TestCase):
    @mock.patch.object(cli, "_write_json")
    @mock.patch.object(cli, "_fetch_model_validate_payload")
    @mock.patch.object(cli, "_load_json")
    def test_main_model_reports_error_and_warning_counts(
        self, load_json, fetch_payload, write_json
    ):
        fetch_payload.return_value = {
            "valid": False,
            "issues": [
                {"message": "Bad view", "severity": "error", "view": "orders", "field": "total"},
                {"message": "Deprecated field", "severity": "warning", "view": "users", "field": "name"},
            ],
        }
        load_json.return_value = {"issues": []}

        exit_code = cli.main_model(
            [
                "--base-url", "https://omni.example",
                "--model-id", "model-1",
                "--api-key", "secret",
            ]
        )

        self.assertEqual(exit_code, 1)
        report = write_json.call_args_list[0].args[1]
        self.assertEqual(report["error_count"], 1)
        self.assertEqual(report["warning_count"], 1)
        self.assertEqual(report["total_issues"], 2)
        self.assertFalse(report["model_valid"])

    @mock.patch.object(cli, "_write_json")
    @mock.patch.object(cli, "_fetch_model_validate_payload")
    @mock.patch.object(cli, "_load_json")
    def test_main_model_errors_only_excludes_warnings(
        self, load_json, fetch_payload, write_json
    ):
        fetch_payload.return_value = {
            "valid": False,
            "issues": [
                {"message": "Bad view", "severity": "error", "view": "orders"},
                {"message": "Deprecated field", "severity": "warning", "view": "users"},
            ],
        }
        load_json.return_value = {"issues": []}

        exit_code = cli.main_model(
            [
                "--base-url", "https://omni.example",
                "--model-id", "model-1",
                "--api-key", "secret",
                "--errors-only",
            ]
        )

        self.assertEqual(exit_code, 1)
        report = write_json.call_args_list[0].args[1]
        self.assertEqual(report["total_issues"], 1)
        self.assertEqual(report["error_count"], 1)
        self.assertEqual(report["warning_count"], 1)
        self.assertTrue(report["errors_only"])

    @mock.patch.object(cli, "_write_json")
    @mock.patch.object(cli, "_fetch_model_validate_payload")
    @mock.patch.object(cli, "_load_json")
    def test_main_model_valid_returns_zero(
        self, load_json, fetch_payload, write_json
    ):
        fetch_payload.return_value = {"valid": True, "issues": []}
        load_json.return_value = {"issues": []}

        exit_code = cli.main_model(
            [
                "--base-url", "https://omni.example",
                "--model-id", "model-1",
                "--api-key", "secret",
            ]
        )

        self.assertEqual(exit_code, 0)
        report = write_json.call_args_list[0].args[1]
        self.assertTrue(report["model_valid"])
        self.assertEqual(report["total_issues"], 0)

    @mock.patch.object(cli, "_write_json")
    @mock.patch.object(cli, "_fetch_model_validate_payload")
    @mock.patch.object(cli, "_load_json")
    def test_main_model_tracks_new_and_resolved(
        self, load_json, fetch_payload, write_json
    ):
        current_issue = {"message": "Bad view", "severity": "error", "view": "orders"}
        fetch_payload.return_value = {"valid": False, "issues": [current_issue]}

        # Simulate a previously recorded issue that is now gone
        old_issue = {"message": "Old problem", "severity": "error", "view": "sales"}
        old_normalized = [
            {
                "id": cli._issue_identity(old_issue),
                "summary": cli._model_issue_summary(old_issue),
                "raw": old_issue,
            }
        ]
        load_json.return_value = {"issues": old_normalized}

        exit_code = cli.main_model(
            [
                "--base-url", "https://omni.example",
                "--model-id", "model-1",
                "--api-key", "secret",
            ]
        )

        self.assertEqual(exit_code, 1)
        report = write_json.call_args_list[0].args[1]
        self.assertEqual(report["new_issues"], 1)
        self.assertEqual(report["resolved_issues"], 1)
        self.assertEqual(report["existing_issues"], 0)


if __name__ == "__main__":
    unittest.main()
