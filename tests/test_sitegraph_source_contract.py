import json
from pathlib import Path

import pytest

from njupt_search_indexer.build_sitegraph_index import (
    load_collection_source_packages,
    validate_sitegraph_package,
)


COUNT_FIELDS = (
    "sections",
    "nav_nodes",
    "homepage_modules",
    "list_pages",
    "detail_pages",
    "low_content_detail_pages",
    "attachments",
    "external_links",
    "edges",
    "url_outcomes",
)


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_minimal_sitegraph_package(index_dir: Path, *, with_allowlist: bool) -> None:
    index_dir.mkdir(parents=True)
    write_json(index_dir / "site.json", {"site_id": "jwc", "domain": "jwc.njupt.edu.cn", "base_url": "https://jwc.njupt.edu.cn/"})
    write_json(index_dir / "sections.json", [])
    for filename in ("list_pages.jsonl", "detail_pages.jsonl", "attachments.jsonl", "external_links.jsonl", "edges.jsonl"):
        (index_dir / filename).write_text("", encoding="utf-8")

    manifest = {
        "site_id": "jwc",
        "quality": {
            "errors": 0,
            "all_discovered_urls_have_outcomes": True,
            "attachment_policy": "metadata_only",
            "external_link_policy": "record_only",
        },
        "totals": {field: 0 for field in COUNT_FIELDS},
        "errors": [],
        "url_outcomes": {
            "https://jwc.njupt.edu.cn/ShowArticle.aspx?id=1": {
                "target_type": "same_domain_page_unknown",
                "outcome": "inline_link_recorded",
            }
        },
    }
    manifest["totals"]["url_outcomes"] = 1
    write_json(index_dir / "manifest.json", manifest)

    if with_allowlist:
        write_json(
            index_dir / "unknown_url_allowlist.json",
            {
                "site_id": "jwc",
                "allowed_unknowns": [
                    {
                        "url_pattern": "^https://jwc\\.njupt\\.edu\\.cn/ShowArticle\\.aspx\\?",
                        "target_type": "same_domain_page_unknown",
                        "outcome": "inline_link_recorded",
                        "reason": "Legacy ASP article links are retained as inline references.",
                    }
                ],
            },
        )


def test_validate_sitegraph_package_rejects_unallowlisted_unknown_url_outcomes(tmp_path):
    index_dir = tmp_path / "jwc" / "index"
    write_minimal_sitegraph_package(index_dir, with_allowlist=False)

    with pytest.raises(ValueError, match="unknown URL outcomes"):
        validate_sitegraph_package(index_dir)


def test_validate_sitegraph_package_accepts_allowlisted_unknown_url_outcomes(tmp_path):
    index_dir = tmp_path / "jwc" / "index"
    write_minimal_sitegraph_package(index_dir, with_allowlist=True)

    package = validate_sitegraph_package(index_dir)

    assert package["manifest"]["site_id"] == "jwc"


def test_load_collection_source_packages_resolves_configured_sitegraph_repo(tmp_path, monkeypatch):
    sitegraph_repo = tmp_path / "sitegraph"
    config = tmp_path / "collection.json"
    write_json(
        config,
        {
            "collection_id": "njupt-public",
            "sitegraph_repo_env": "NJUPT_SITEGRAPH_REPO",
            "sitegraph_repo": "../unused",
            "source_packages": ["data/sites/jwc/index", "data/sites/xsc/index"],
        },
    )
    monkeypatch.setenv("NJUPT_SITEGRAPH_REPO", str(sitegraph_repo))

    assert load_collection_source_packages(config) == [
        (sitegraph_repo / "data/sites/jwc/index").resolve(),
        (sitegraph_repo / "data/sites/xsc/index").resolve(),
    ]
