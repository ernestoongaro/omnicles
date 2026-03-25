import argparse
import contextlib
import io
import os
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


class ParseArgsTests(unittest.TestCase):
    @mock.patch.dict(os.environ, {"OMNI_LABELS": "Verified, Sales, Verified"})
    def test_parse_args_uses_env_labels_when_cli_missing(self):
        args = cli._parse_args([])
        self.assertEqual(args.labels, ["Verified", "Sales"])

    @mock.patch.dict(os.environ, {"OMNI_LABELS": "Ignored"})
    def test_parse_args_prefers_cli_labels_and_dedupes(self):
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


class LabelFilteringTests(unittest.TestCase):
    def test_fetch_content_identifiers_for_labels_paginates(self):
        args = argparse.Namespace(
            base_url="https://omni.example",
            api_key="secret",
            auth_header="Authorization",
            auth_scheme="Bearer",
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
            identifiers = cli._fetch_content_identifiers_for_labels(args)

        self.assertEqual(identifiers, {"doc-1", "doc-2", "doc-3"})
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

    def test_collect_content_issues_includes_document_identifier_and_labels(self):
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


class MainFlowTests(unittest.TestCase):
    @mock.patch.object(cli, "_write_json")
    @mock.patch.object(cli, "_fetch_content_identifiers_for_labels")
    @mock.patch.object(cli, "_fetch_validator_payload")
    @mock.patch.object(cli, "_load_json")
    def test_main_filters_results_and_resets_history_when_labels_change(
        self,
        load_json,
        fetch_validator_payload,
        fetch_content_identifiers_for_labels,
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
        fetch_content_identifiers_for_labels.return_value = {"dash-2"}
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
        self.assertIn("History labels changed", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
