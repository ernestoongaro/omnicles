import argparse
import datetime
import hashlib
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


def _load_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _extract_by_path(payload: Any, path: Optional[str]) -> Optional[List[Any]]:
    if not path:
        return None
    current = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    if isinstance(current, list):
        return current
    return None


def _collect_content_issues(payload: Dict[str, Any]) -> List[Any]:
    issues: List[Any] = []
    content = payload.get("content")
    if not isinstance(content, list):
        return issues

    for document in content:
        if not isinstance(document, dict):
            continue
        doc_context = {
            "document_id": document.get("document_id"),
            "document_name": document.get("name"),
            "document_type": document.get("type"),
            "folder_name": document.get("folder", {}).get("name")
            if isinstance(document.get("folder"), dict)
            else None,
            "folder_path": document.get("folder", {}).get("path")
            if isinstance(document.get("folder"), dict)
            else None,
        }
        dashboard_issues = document.get("dashboard_filter_issues")
        if isinstance(dashboard_issues, list):
            for item in dashboard_issues:
                if isinstance(item, dict):
                    message = item.get("message")
                else:
                    message = item
                issues.append(
                    {
                        "message": message,
                        "raw_issue": item,
                        "issue_type": "dashboard_filter",
                        **doc_context,
                    }
                )

        queries = document.get("queries_and_issues")
        if not isinstance(queries, list):
            continue
        for query in queries:
            if not isinstance(query, dict):
                continue
            query_issues = query.get("issues")
            if isinstance(query_issues, list):
                for item in query_issues:
                    if isinstance(item, dict):
                        message = item.get("message")
                    else:
                        message = item
                    issues.append(
                        {
                            "message": message,
                            "raw_issue": item,
                            "issue_type": "query",
                            "query_name": query.get("query_name"),
                            "query_presentation_id": query.get(
                                "query_presentation_id"
                            ),
                            **doc_context,
                        }
                    )
    return issues


def _extract_issues(payload: Any, issues_path: Optional[str]) -> List[Any]:
    by_path = _extract_by_path(payload, issues_path)
    if by_path is not None:
        return by_path

    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in ("issues", "validation_issues", "errors"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    if "content" in payload:
        collected = _collect_content_issues(payload)
        if collected:
            return collected

    for key in ("content", "documents", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    return []


def _issue_identity(issue: Any) -> str:
    if isinstance(issue, str):
        value = issue
    else:
        try:
            value = json.dumps(issue, sort_keys=True, separators=(",", ":"))
        except TypeError:
            value = str(issue)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _issue_summary(issue: Any) -> str:
    if isinstance(issue, str):
        return issue
    if isinstance(issue, dict):
        message = issue.get("message")
        if message is not None and not isinstance(message, str):
            message = str(message)
        if isinstance(message, str) and message.strip():
            doc_name = issue.get("document_name")
            query_name = issue.get("query_name")
            prefix_parts = []
            if isinstance(doc_name, str) and doc_name.strip():
                prefix_parts.append(doc_name.strip())
            if isinstance(query_name, str) and query_name.strip():
                prefix_parts.append(query_name.strip())
            prefix = " / ".join(prefix_parts)
            return f"{prefix}: {message}" if prefix else message
        for key in ("title", "name", "path", "field"):
            value = issue.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return json.dumps(issue, sort_keys=True)
    return str(issue)


def _normalize_issues(issues: Iterable[Any]) -> List[Dict[str, Any]]:
    normalized = []
    for issue in issues:
        normalized.append(
            {
                "id": _issue_identity(issue),
                "summary": _issue_summary(issue),
                "raw": issue,
            }
        )
    return normalized


def _partition_issues(
    current: List[Dict[str, Any]],
    previous: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    previous_ids = {item["id"] for item in previous}
    current_ids = {item["id"] for item in current}

    new_items = [item for item in current if item["id"] not in previous_ids]
    existing_items = [item for item in current if item["id"] in previous_ids]
    resolved_items = [item for item in previous if item["id"] not in current_ids]

    return new_items, existing_items, resolved_items


def _build_headers(api_key: str, auth_header: str, auth_scheme: str) -> Dict[str, str]:
    if auth_scheme:
        token_value = f"{auth_scheme} {api_key}".strip()
    else:
        token_value = api_key
    return {auth_header: token_value}


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Omni content validator and track history",
    )
    parser.add_argument("--base-url", default=os.getenv("OMNI_BASE_URL"))
    parser.add_argument("--model-id", default=os.getenv("OMNI_MODEL_ID"))
    parser.add_argument("--api-key", default=os.getenv("OMNI_API_KEY"))
    parser.add_argument("--user-id", default=os.getenv("OMNI_USER_ID"))
    parser.add_argument("--branch-id", default=os.getenv("OMNI_BRANCH_ID"))
    parser.add_argument("--branch-name", default=os.getenv("OMNI_BRANCH_NAME"))
    parser.add_argument("--auth-header", default="Authorization")
    parser.add_argument("--auth-scheme", default="Bearer")
    parser.add_argument("--issues-path", default=os.getenv("OMNI_ISSUES_PATH"))
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--history-in", default=".omni-content-validator/history.json")
    parser.add_argument("--history-out", default=".omni-content-validator/history.json")
    parser.add_argument("--report-out", default=".omni-content-validator/report.json")
    parser.add_argument("--raw-response-out", default=None)
    parser.add_argument(
        "--fail-on-new-only",
        action="store_true",
        help="Only fail when there are new issues compared to history",
    )
    return parser.parse_args(argv)


def _validate_args(args: argparse.Namespace) -> None:
    missing = []
    if not args.base_url:
        missing.append("--base-url or OMNI_BASE_URL")
    if not args.model_id:
        missing.append("--model-id or OMNI_MODEL_ID")
    if not args.api_key:
        missing.append("--api-key or OMNI_API_KEY")
    if missing:
        raise SystemExit(f"Missing required values: {', '.join(missing)}")


def _fetch_validator_payload(args: argparse.Namespace) -> Any:
    url = f"{args.base_url.rstrip('/')}/api/v1/models/{args.model_id}/content-validator"
    headers = _build_headers(args.api_key, args.auth_header, args.auth_scheme)
    params = {}
    if args.user_id:
        params["userId"] = args.user_id
    if args.branch_id:
        params["branch_id"] = args.branch_id

    response = requests.get(url, headers=headers, params=params, timeout=args.timeout)
    if not response.ok:
        raise SystemExit(f"Content validator failed: {response.status_code} {response.text}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise SystemExit(f"Content validator did not return JSON: {exc}") from exc

    return payload


def _resolve_branch_id(args: argparse.Namespace) -> Optional[str]:
    if args.branch_id:
        return args.branch_id
    if not args.branch_name:
        return None

    headers = _build_headers(args.api_key, args.auth_header, args.auth_scheme)
    cursor = None
    while True:
        params = {}
        if cursor:
            params["cursor"] = cursor
        url = f"{args.base_url.rstrip('/')}/api/v1/models"
        response = requests.get(url, headers=headers, params=params, timeout=args.timeout)
        if not response.ok:
            raise SystemExit(
                f"Branch lookup failed: {response.status_code} {response.text}"
            )
        payload = response.json()
        for record in payload.get("records", []):
            if record.get("modelKind") != "BRANCH":
                continue
            if record.get("baseModelId") != args.model_id:
                continue
            if record.get("name") != args.branch_name:
                continue
            return record.get("id")

        cursor = payload.get("pageInfo", {}).get("nextCursor")
        if not cursor:
            return None


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    _validate_args(args)

    resolved_branch_id = _resolve_branch_id(args)
    if resolved_branch_id:
        args.branch_id = resolved_branch_id
        if args.branch_name:
            print(f"Resolved branch '{args.branch_name}' to id {resolved_branch_id}")
        else:
            print(f"Using branch id {resolved_branch_id}")
    elif args.branch_name:
        print(f"No matching Omni branch found for '{args.branch_name}', using default")

    payload = _fetch_validator_payload(args)
    if args.raw_response_out:
        _write_json(args.raw_response_out, {"payload": payload})

    issues = _extract_issues(payload, args.issues_path)
    normalized = _normalize_issues(issues)

    previous_payload = _load_json(args.history_in) or {}
    previous_issues = previous_payload.get("issues", [])

    new_items, existing_items, resolved_items = _partition_issues(
        normalized, previous_issues
    )

    report = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "base_url": args.base_url,
        "model_id": args.model_id,
        "total_issues": len(normalized),
        "new_issues": len(new_items),
        "existing_issues": len(existing_items),
        "resolved_issues": len(resolved_items),
        "issues": normalized,
        "new_issue_samples": new_items[:20],
        "existing_issue_samples": existing_items[:20],
        "resolved_issue_samples": resolved_items[:20],
    }

    _write_json(args.report_out, report)
    _write_json(
        args.history_out,
        {
            "generated_at": report["generated_at"],
            "base_url": args.base_url,
            "model_id": args.model_id,
            "issues": normalized,
        },
    )

    print(
        "Content validator results: "
        f"total={report['total_issues']} "
        f"new={report['new_issues']} "
        f"existing={report['existing_issues']} "
        f"resolved={report['resolved_issues']}"
    )

    if args.fail_on_new_only:
        return 1 if report["new_issues"] > 0 else 0
    return 1 if report["total_issues"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
