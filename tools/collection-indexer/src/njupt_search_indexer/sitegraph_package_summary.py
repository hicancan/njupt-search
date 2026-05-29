from __future__ import annotations

from collections import Counter
from typing import Any

from .sitegraph_documents import site_display_name
from .sitegraph_source import COUNT_FIELDS, package_source_id
from .sitegraph_text import clean_text


def aggregate_counts(packages: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for package in packages:
        counts.update({field: int(package["actual_counts"].get(field, 0) or 0) for field in COUNT_FIELDS})
    return {field: int(counts.get(field, 0)) for field in COUNT_FIELDS}


def source_truth_counts(packages: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    return {package_source_id(package): dict(package["actual_counts"]) for package in packages}


def aggregate_quality(packages: list[dict[str, Any]]) -> dict[str, Any]:
    qualities = [
        package.get("manifest", {}).get("quality")
        for package in packages
        if isinstance(package.get("manifest", {}).get("quality"), dict)
    ]
    return {
        "all_discovered_urls_have_outcomes": all(item.get("all_discovered_urls_have_outcomes") is True for item in qualities),
        "errors": sum(int(item.get("errors", 0) or 0) for item in qualities),
        "attachment_policy": "metadata_only" if all(item.get("attachment_policy") == "metadata_only" for item in qualities) else "mixed",
        "external_link_policy": "record_only" if all(item.get("external_link_policy") == "record_only" for item in qualities) else "mixed",
        "sources": {
            package_source_id(package): package.get("manifest", {}).get("quality")
            for package in packages
        },
    }


def latest_upstream_generated_at(packages: list[dict[str, Any]]) -> str | None:
    values = [
        clean_text(package.get("manifest", {}).get("generated_at"))
        for package in packages
        if clean_text(package.get("manifest", {}).get("generated_at"))
    ]
    return max(values) if values else None


def source_entries(packages: list[dict[str, Any]], *, collection_id: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for package in packages:
        source_id = package_source_id(package)
        entries.append(
            {
                "source_id": source_id,
                "source_kind": "sitegraph",
                "artifact_root": f"generated/collections/{collection_id}/sitegraph",
                "upstream_generated_at": clean_text(package["manifest"].get("generated_at")) or None,
                "display_name": site_display_name(package["site"]),
                "truth_counts": dict(package["actual_counts"]),
                "quality": package["manifest"].get("quality"),
            }
        )
    return entries
