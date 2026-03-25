import argparse
import datetime
import hashlib
import json
import os
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

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


def _extract_label_names(record: Dict[str, Any]) -> Optional[List[str]]:
    labels = record.get("labels")
    if not isinstance(labels, list):
        return None

    names = []
    for item in labels:
        if isinstance(item, dict):
            value = item.get("name")
        else:
            value = item
        if isinstance(value, str) and value.strip():
            names.append(value.strip())

    if not names:
        return None
    return names


def _extract_owner(record: Dict[str, Any]) -> Optional[Dict[str, str]]:
    owner = record.get("owner")
    if not isinstance(owner, dict):
        return None

    normalized_owner = {}
    owner_id = owner.get("id")
    if isinstance(owner_id, str) and owner_id.strip():
        normalized_owner["id"] = owner_id.strip()

    owner_name = owner.get("name")
    if isinstance(owner_name, str) and owner_name.strip():
        normalized_owner["name"] = owner_name.strip()

    if not normalized_owner:
        return None
    return normalized_owner


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
            "document_identifier": document.get("identifier"),
            "document_name": document.get("name"),
            "document_type": document.get("type"),
            "document_url": document.get("url")
            if isinstance(document.get("url"), str)
            else None,
            "folder_name": document.get("folder", {}).get("name")
            if isinstance(document.get("folder"), dict)
            else None,
            "folder_path": document.get("folder", {}).get("path")
            if isinstance(document.get("folder"), dict)
            else None,
            "document_labels": _extract_label_names(document),
            "document_owner": _extract_owner(document),
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
        return _collect_content_issues(payload)

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
            comparable_issue = issue
            if isinstance(issue, dict):
                comparable_issue = dict(issue)
                comparable_issue.pop("document_labels", None)
                comparable_issue.pop("document_owner", None)
            value = json.dumps(
                comparable_issue, sort_keys=True, separators=(",", ":")
            )
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


def _build_headers(api_key: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _env_flag(name: str) -> bool:
    value = os.getenv(name)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_csv_values(values: Iterable[Optional[str]]) -> List[str]:
    names = []
    for value in values:
        if not isinstance(value, str):
            continue
        for item in value.split(","):
            name = item.strip()
            if name:
                names.append(name)
    return list(dict.fromkeys(names))


def _normalize_history_labels(value: Any) -> List[str]:
    if isinstance(value, list):
        return _split_csv_values(value)
    if isinstance(value, str):
        return _split_csv_values([value])
    return []


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
    parser.add_argument("--issues-path", default=os.getenv("OMNI_ISSUES_PATH"))
    parser.add_argument(
        "--labels",
        action="append",
        default=[],
        help="Comma-separated label names to filter validation results by",
    )
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        help="Repeatable label name to filter validation results by",
    )
    parser.add_argument(
        "--include-personal-folders",
        action=argparse.BooleanOptionalAction,
        default=_env_flag("OMNI_INCLUDE_PERSONAL_FOLDERS"),
        help="Include personal folders in the validation search",
    )
    parser.add_argument("--timeout", type=int, default=int(os.getenv("OMNI_TIMEOUT", "60")))
    parser.add_argument("--history-in", default=".omni-content-validator/history.json")
    parser.add_argument("--history-out", default=".omni-content-validator/history.json")
    parser.add_argument("--report-out", default=".omni-content-validator/report.json")
    parser.add_argument("--raw-response-out", default=None)
    parser.add_argument(
        "--fail-on-new-only",
        action=argparse.BooleanOptionalAction,
        default=_env_flag("OMNI_FAIL_ON_NEW_ONLY"),
        help="Only fail when there are new issues compared to history",
    )
    args = parser.parse_args(argv)

    cli_labels = _split_csv_values([*args.labels, *args.label])
    env_labels = _split_csv_values([os.getenv("OMNI_LABELS")])
    args.labels = cli_labels or env_labels
    delattr(args, "label")
    return args


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
    headers = _build_headers(args.api_key)
    params = {}
    if args.user_id:
        params["userId"] = args.user_id
    if args.branch_id:
        params["branch_id"] = args.branch_id
    if args.include_personal_folders:
        params["include_personal_folders"] = "true"

    response = requests.get(url, headers=headers, params=params, timeout=args.timeout)
    if not response.ok:
        raise SystemExit(f"Content validator failed: {response.status_code} {response.text}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise SystemExit(f"Content validator did not return JSON: {exc}") from exc

    return payload


def _fetch_content_records(args: argparse.Namespace) -> List[Dict[str, Any]]:
    headers = _build_headers(args.api_key)
    url = f"{args.base_url.rstrip('/')}/api/v1/content"
    records: List[Dict[str, Any]] = []
    cursor = None

    while True:
        params = {}
        if args.labels:
            params["include"] = "labels"
            params["labels"] = ",".join(args.labels)
        if cursor:
            params["cursor"] = cursor
        if args.user_id:
            params["userId"] = args.user_id
        if args.branch_id:
            params["branch_id"] = args.branch_id
        if args.include_personal_folders:
            params["include_personal_folders"] = "true"

        response = requests.get(url, headers=headers, params=params, timeout=args.timeout)
        if not response.ok:
            raise SystemExit(
                f"Content lookup failed: {response.status_code} {response.text}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise SystemExit(f"Content lookup did not return JSON: {exc}") from exc

        page_records = payload.get("records", [])
        if isinstance(page_records, list):
            for record in page_records:
                if not isinstance(record, dict):
                    continue
                records.append(record)

        cursor = payload.get("pageInfo", {}).get("nextCursor")
        if not cursor:
            return records


def _index_content_records(
    records: Iterable[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    indexed_records = {}
    for record in records:
        identifier = record.get("identifier")
        if isinstance(identifier, str) and identifier.strip():
            indexed_records[identifier] = record
    return indexed_records


def _filter_validator_payload(
    payload: Any, allowed_identifiers: Set[str]
) -> Any:
    if not isinstance(payload, dict):
        return payload

    content = payload.get("content")
    if not isinstance(content, list):
        return payload

    filtered_payload = dict(payload)
    filtered_payload["content"] = [
        document
        for document in content
        if isinstance(document, dict)
        and isinstance(document.get("identifier"), str)
        and document.get("identifier") in allowed_identifiers
    ]
    return filtered_payload


def _enrich_validator_payload(
    payload: Any, content_records_by_identifier: Dict[str, Dict[str, Any]]
) -> Any:
    if not isinstance(payload, dict):
        return payload

    content = payload.get("content")
    if not isinstance(content, list):
        return payload

    enriched_payload = dict(payload)
    enriched_content = []
    for document in content:
        if not isinstance(document, dict):
            enriched_content.append(document)
            continue

        enriched_document = dict(document)
        identifier = enriched_document.get("identifier")
        content_record = None
        if isinstance(identifier, str):
            content_record = content_records_by_identifier.get(identifier)

        if isinstance(content_record, dict):
            owner = _extract_owner(content_record)
            if owner is not None and not isinstance(enriched_document.get("owner"), dict):
                enriched_document["owner"] = owner

            labels = content_record.get("labels")
            if isinstance(labels, list) and not isinstance(
                enriched_document.get("labels"), list
            ):
                enriched_document["labels"] = labels

        enriched_content.append(enriched_document)

    enriched_payload["content"] = enriched_content
    return enriched_payload


def _resolve_branch_id(args: argparse.Namespace) -> Optional[str]:
    if args.branch_id:
        return args.branch_id
    if not args.branch_name:
        return None

    headers = _build_headers(args.api_key)
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
    content_records_by_identifier = {}
    if isinstance(payload, dict) and isinstance(payload.get("content"), list):
        content_records = _fetch_content_records(args)
        content_records_by_identifier = _index_content_records(content_records)

        if args.labels:
            allowed_identifiers = set(content_records_by_identifier)
            payload = _filter_validator_payload(payload, allowed_identifiers)
            print(
                "Filtered validator payload by labels "
                f"{', '.join(args.labels)} "
                f"to {len(payload.get('content', [])) if isinstance(payload, dict) else 0} document(s)"
            )

        payload = _enrich_validator_payload(payload, content_records_by_identifier)
    if args.raw_response_out:
        _write_json(args.raw_response_out, {"payload": payload})

    issues = _extract_issues(payload, args.issues_path)
    normalized = _normalize_issues(issues)

    previous_payload = _load_json(args.history_in) or {}
    previous_labels = _normalize_history_labels(previous_payload.get("labels"))
    if previous_labels != args.labels:
        if previous_payload:
            print("History labels changed; ignoring previous issues for comparison")
        previous_issues = []
    else:
        previous_issues = previous_payload.get("issues", [])

    new_items, existing_items, resolved_items = _partition_issues(
        normalized, previous_issues
    )

    report = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "base_url": args.base_url,
        "model_id": args.model_id,
        "labels": args.labels,
        "include_personal_folders": args.include_personal_folders,
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
            "labels": args.labels,
            "include_personal_folders": args.include_personal_folders,
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
