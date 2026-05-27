from __future__ import annotations

import json
import base64
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[4]
PUBLIC_ROOT = BASE_DIR / "apps" / "web" / "public"
PUBLIC_INDEX_DIR = PUBLIC_ROOT / "generated" / "collections" / "njupt-public"

FIELD_WEIGHTS = {
    "t": 120.0,
    "a": 95.0,
    "e": 95.0,
    "y": 95.0,
    "s": 60.0,
    "n": 55.0,
    "g": 45.0,
    "m": 16.0,
    "c": 10.0,
}

DEFAULT_MAX_SHARD_LOADS = 32
FULL_SCAN_FIELDS = ["title", "section", "nav_path", "summary", "content", "attachments", "url"]


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return re.sub(r"\s+", "", text)


def filter_token_hash_int(text: str, seed: int) -> int:
    value = (2166136261 ^ seed) & 0xFFFFFFFF
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 16777619) & 0xFFFFFFFF
    return value


def tokens_for_query(query: str, aliases: dict[str, Any]) -> list[str]:
    candidates = [query]
    normalized_query = normalize_text(query)
    for key, payload in aliases.items():
        terms = [key]
        if isinstance(payload, dict) and isinstance(payload.get("aliases"), list):
            terms.extend(str(item) for item in payload["aliases"])
        if any(normalize_text(term) and normalize_text(term) in normalized_query for term in terms):
            candidates.extend(terms)
    tokens: set[str] = set()
    for candidate in candidates:
        text = normalize_text(candidate)
        if len(text) >= 2:
            tokens.add(text)
        for match in re.finditer(r"[\u4e00-\u9fff]{2,}|[a-z0-9][a-z0-9._-]{1,}", text):
            part = match.group(0)
            if re.fullmatch(r"[\u4e00-\u9fff]+", part):
                for size in range(2, min(5, len(part)) + 1):
                    for index in range(0, len(part) - size + 1):
                        tokens.add(part[index : index + size])
            else:
                tokens.add(part)
    return sorted(tokens, key=len, reverse=True)


def load_index() -> dict[str, Any]:
    manifest = read_json(PUBLIC_INDEX_DIR / "manifest.json")
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}

    def artifact(name: str) -> Any:
        entry = artifacts.get(name)
        if not isinstance(entry, dict) or not entry.get("path"):
            raise FileNotFoundError(f"manifest.artifacts.{name}.path is missing")
        return read_json(PUBLIC_ROOT / str(entry["path"]))

    return {
        "manifest": manifest,
        "doc_meta": artifact("doc_meta_light"),
        "light_inverted": artifact("light_inverted_index"),
        "body_inverted": None,
        "shard_filter": None,
        "aliases": artifact("query_aliases"),
    }


def load_body_index(index: dict[str, Any]) -> dict[str, Any]:
    if index.get("body_inverted") is not None:
        return index["body_inverted"]
    manifest = index["manifest"]
    entry = manifest["artifacts"]["body_inverted_index"]
    index["body_inverted"] = read_json(PUBLIC_ROOT / str(entry["path"]))
    return index["body_inverted"]


def load_shard_filter(index: dict[str, Any]) -> dict[str, Any]:
    if index.get("shard_filter") is not None:
        return index["shard_filter"]
    manifest = index["manifest"]
    entry = manifest["artifacts"]["shard_filter"]
    index["shard_filter"] = read_json(PUBLIC_ROOT / str(entry["path"]))
    return index["shard_filter"]


def shard_path_for_meta(manifest: dict[str, Any], meta: dict[str, Any]) -> str:
    shard = meta.get("shard") if isinstance(meta.get("shard"), dict) else {}
    path = str(shard.get("path") or "")
    if path:
        return path
    shard_id = str(shard.get("shard_id") or "")
    for item in ((manifest.get("sitegraph") or {}).get("full_shards") or []):
        if isinstance(item, dict) and item.get("shard_id") == shard_id:
            return str(item.get("path") or "")
    return ""


def load_shards_for_indices(
    manifest: dict[str, Any],
    doc_meta: list[dict[str, Any]],
    indices: set[int],
) -> tuple[dict[int, dict[str, Any]], set[str]]:
    docs_by_index: dict[int, dict[str, Any]] = {}
    wanted_paths: set[str] = set()
    for index in indices:
        if index < 0 or index >= len(doc_meta):
            continue
        path = shard_path_for_meta(manifest, doc_meta[index])
        if path:
            wanted_paths.add(path)
    for path in wanted_paths:
        payload = read_json(PUBLIC_ROOT / path)
        for doc in payload:
            docs_by_index[int(doc["doc_index"])] = doc
    return docs_by_index, wanted_paths


def text_blob(document: dict[str, Any], *fields: str) -> str:
    values: list[str] = []
    for field in fields:
        value = document.get(field)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value is not None:
            values.append(str(value))
    return normalize_text(" ".join(values))


def freshness_score(document: dict[str, Any]) -> float:
    if document.get("facet") not in {"notice_article", "exam", "news"}:
        return 0.0
    raw = document.get("published_at")
    if not raw:
        return 0.0
    try:
        published = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    days = max(0.0, (datetime.now(timezone.utc) - published).total_seconds() / 86400)
    return max(0.0, 600.0 - min(days, 3650.0) / 3650.0 * 600.0)


def date_sort_value(raw: Any) -> float:
    if not raw:
        return 0.0
    try:
        published = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return published.timestamp()


def rank_document(document: dict[str, Any], query: str, terms: list[str], light_score: float) -> dict[str, Any]:
    normalized_query = normalize_text(query)
    title = text_blob(document, "title")
    section = text_blob(document, "section", "nav_path_text")
    summary = text_blob(document, "summary")
    content = text_blob(document, "content")
    tags = text_blob(document, "tags")
    url = text_blob(document, "url")
    external = title + text_blob(document, "url") if document.get("record_type") == "external" else ""
    attachment = normalize_text(" ".join(
        " ".join(str(attachment.get(field) or "") for field in ("name", "extension", "section", "parent_url"))
        for attachment in document.get("attachments") or []
    ))

    score = light_score
    reasons: list[str] = []
    if normalized_query and title == normalized_query:
        score += 5000
        reasons.append("标题精确")
    elif normalized_query and normalized_query in title:
        score += 520
        reasons.append("标题包含")
    if normalized_query and normalized_query in attachment:
        score += 360
        reasons.append("附件名命中")
    if normalized_query and normalized_query in external:
        score += 360
        reasons.append("外部系统/外链命中")
    if normalized_query and normalized_query in url:
        score += 220
        reasons.append("URL 命中")
    if normalized_query and normalized_query in section:
        score += 180
        reasons.append("栏目路径命中")
    if normalized_query and normalized_query in content:
        score += 120
        reasons.append("正文命中")
    if normalized_query and normalized_query in tags:
        score += 80
        reasons.append("标签命中")

    matched_terms = []
    for term in terms[:12]:
        if term in title:
            score += 80
            matched_terms.append(term)
        elif term in attachment:
            score += 70
            matched_terms.append(term)
        elif term in external:
            score += 65
            matched_terms.append(term)
        elif term in url:
            score += 55
            matched_terms.append(term)
        elif term in section:
            score += 45
            matched_terms.append(term)
        elif term in summary or term in content:
            score += 12
            matched_terms.append(term)
    if matched_terms:
        reasons.append("词项: " + "、".join(sorted(set(matched_terms), key=len, reverse=True)[:6]))

    if document.get("facet") == "system" and any(term in normalized_query for term in ("系统", "jwxt", "教务")):
        score += 1500
        reasons.append("系统入口")
    if document.get("facet") == "download" and any(term in normalized_query for term in ("附件", "下载", "xlsx", "xls", "表格")):
        score += 120
        reasons.append("下载资源")
    if document.get("facet") == "policy" and any(term in normalized_query for term in ("规章", "制度", "管理办法", "政策")):
        score += 900
        reasons.append("政策制度")
    if document.get("facet") == "workflow" and any(term in normalized_query for term in ("办事流程", "办理", "申请流程", "流程")):
        score += 900
        reasons.append("办事流程")
    if document.get("facet") == "exam" and any(term in normalized_query for term in ("考试", "期末", "慕课", "mooc")):
        score += 650
        reasons.append("考试相关")
    score += freshness_score(document)

    ranked = dict(document)
    ranked["score"] = round(score, 4)
    ranked["score_reason"] = "；".join(reasons or ["倒排候选"])
    return ranked


def apply_postings(scores: dict[int, float], inverted_tokens: dict[str, Any], terms: list[str]) -> None:
    for term in terms:
        postings = inverted_tokens.get(term)
        if not isinstance(postings, dict):
            continue
        for field, ids in postings.items():
            weight = FIELD_WEIGHTS.get(field, 8.0)
            for doc_index in ids:
                scores[int(doc_index)] = scores.get(int(doc_index), 0.0) + weight + min(len(term), 8)


def full_scan_blob(document: dict[str, Any]) -> str:
    attachment_text = " ".join(
        " ".join(str(attachment.get(field) or "") for field in ("name", "extension", "url", "section", "parent_url"))
        for attachment in document.get("attachments") or []
    )
    return normalize_text(
        " ".join(
            [
                text_blob(document, "title"),
                text_blob(document, "section"),
                text_blob(document, "nav_path"),
                text_blob(document, "nav_path_text"),
                text_blob(document, "summary"),
                text_blob(document, "content"),
                text_blob(document, "url"),
                attachment_text,
            ]
        )
    )


def full_scan_matches(document: dict[str, Any], normalized_query: str, terms: list[str]) -> bool:
    blob = full_scan_blob(document)
    return bool((normalized_query and normalized_query in blob) or any(len(term) >= 2 and term in blob for term in terms))


def shard_filter_proves_no_match(shard_id: str, shard_filter: dict[str, Any], terms: list[str]) -> bool:
    payload = shard_filter.get(shard_id)
    if not isinstance(payload, dict) or payload.get("hash_algorithm") != "bloom-fnv1a32-utf8":
        return False
    bitset_base64 = str(payload.get("bitset_base64") or "")
    bit_count = int(payload.get("bit_count") or 0)
    hash_count = int(payload.get("hash_count") or 0)
    if not bitset_base64 or bit_count <= 0 or hash_count <= 0:
        return False
    data = base64.b64decode(bitset_base64)

    def may_contain(term: str) -> bool:
        for seed in range(hash_count):
            bit = filter_token_hash_int(term, seed) % bit_count
            if (data[bit // 8] & (1 << (bit % 8))) == 0:
                return False
        return True

    return all(not may_contain(term) for term in terms)


def sorted_ranked(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        results,
        key=lambda item: (
            -float(item.get("score") or 0),
            -date_sort_value(item.get("published_at")),
            str(item.get("id") or ""),
        ),
    )


def coverage(
    manifest: dict[str, Any],
    *,
    phase: str,
    fields: list[str],
    proved_no_match_shards: int,
    scanned_shards: int,
    searched_documents: int,
    loaded_paths: set[str],
    used_body_index: bool,
    exhaustive_complete: bool,
) -> dict[str, Any]:
    artifacts = manifest["artifacts"]
    loaded_bytes = sum(int(artifacts[name]["bytes"]) for name in ("doc_meta_light", "light_inverted_index", "query_aliases"))
    if used_body_index:
        loaded_bytes += int(artifacts["body_inverted_index"]["bytes"])
    shard_bytes = {str(item["path"]): int(item["bytes"]) for item in manifest["sitegraph"]["full_shards"]}
    loaded_bytes += sum(shard_bytes.get(path, 0) for path in loaded_paths)
    return {
        "phase": phase,
        "searched_fields": fields,
        "proved_no_match_shards": proved_no_match_shards,
        "scanned_shards": scanned_shards,
        "total_shards": int(manifest["progressive_search"]["total_shards"]),
        "searched_documents": searched_documents,
        "total_documents": int(manifest["progressive_search"]["total_documents"]),
        "loaded_bytes": loaded_bytes,
        "used_body_index": used_body_index,
        "exhaustive_complete": exhaustive_complete,
    }


def recall_documents_with_stats(
    query: str,
    *,
    limit: int = 20,
    candidate_limit: int = 160,
    max_shard_loads: int = DEFAULT_MAX_SHARD_LOADS,
) -> dict[str, Any]:
    index = load_index()
    manifest = index["manifest"]
    doc_meta = index["doc_meta"]
    terms = tokens_for_query(query, index["aliases"])
    scores: dict[int, float] = {}
    apply_postings(scores, index["light_inverted"]["tokens"], terms)

    normalized_query = normalize_text(query)
    used_body_index = False
    if len(scores) < 8:
        for meta in doc_meta:
            haystack = text_blob(meta, "title", "section", "nav_path_text")
            if normalized_query and normalized_query in haystack:
                index_id = int(meta["doc_index"])
                scores[index_id] = scores.get(index_id, 0.0) + 90.0

    def select_candidates(limit_count: int, shard_limit: int) -> tuple[list[int], set[str]]:
        selected: list[int] = []
        paths: set[str] = set()
        for doc_index, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit_count]:
            if doc_index < 0 or doc_index >= len(doc_meta):
                continue
            path = shard_path_for_meta(manifest, doc_meta[doc_index])
            is_new_shard = bool(path) and path not in paths
            if is_new_shard and len(paths) >= shard_limit:
                continue
            selected.append(doc_index)
            if is_new_shard:
                paths.add(path)
        return selected, paths

    quick_indices, quick_paths = select_candidates(min(candidate_limit, 48), min(max_shard_loads, 8))
    quick_docs, loaded_paths = load_shards_for_indices(manifest, doc_meta, set(quick_indices))
    quick_ranked = sorted_ranked([
        rank_document(quick_docs[doc_index], query, terms, scores.get(doc_index, 0.0))
        for doc_index in quick_indices
        if doc_index in quick_docs
    ])

    body_index = load_body_index(index)
    apply_postings(scores, body_index["tokens"], terms)
    used_body_index = True

    if len(scores) < 8:
        for meta in doc_meta:
            haystack = text_blob(meta, "title", "section", "nav_path_text")
            if normalized_query and normalized_query in haystack:
                index_id = int(meta["doc_index"])
                scores[index_id] = scores.get(index_id, 0.0) + 90.0

    selected_candidate_indices, candidate_paths = select_candidates(candidate_limit, max_shard_loads)
    full_docs, candidate_loaded_paths = load_shards_for_indices(manifest, doc_meta, set(selected_candidate_indices))
    loaded_paths |= candidate_loaded_paths
    ranked_by_id: dict[str, dict[str, Any]] = {
        str(item["id"]): item
        for item in quick_ranked
    }
    for doc_index in selected_candidate_indices:
        if doc_index < 0 or doc_index >= len(doc_meta):
            continue
        if doc_index not in full_docs:
            continue
        item = rank_document(full_docs[doc_index], query, terms, scores.get(doc_index, 0.0))
        existing = ranked_by_id.get(str(item["id"]))
        if existing is None or float(item["score"]) > float(existing.get("score") or 0):
            ranked_by_id[str(item["id"])] = item

    shard_filter = load_shard_filter(index)
    proved_no_match_shards = 0
    scanned_shards = 0
    searched_documents = 0
    for shard in manifest["sitegraph"]["full_shards"]:
        shard_id = str(shard["shard_id"])
        if shard_filter_proves_no_match(shard_id, shard_filter, terms):
            proved_no_match_shards += 1
            continue
        path = str(shard["path"])
        documents = read_json(PUBLIC_ROOT / path)
        loaded_paths.add(path)
        scanned_shards += 1
        for document in documents:
            searched_documents += 1
            doc_index = int(document["doc_index"])
            if full_scan_matches(document, normalized_query, terms):
                item = rank_document(document, query, terms, scores.get(doc_index, 24.0))
                existing = ranked_by_id.get(str(item["id"]))
                if existing is None or float(item["score"]) > float(existing.get("score") or 0):
                    ranked_by_id[str(item["id"])] = item

    ranked = sorted_ranked(list(ranked_by_id.values()))
    final_coverage = coverage(
        manifest,
        phase="exhaustive_complete",
        fields=FULL_SCAN_FIELDS,
        proved_no_match_shards=proved_no_match_shards,
        scanned_shards=scanned_shards,
        searched_documents=searched_documents,
        loaded_paths=loaded_paths,
        used_body_index=used_body_index,
        exhaustive_complete=True,
    )
    return {
        "results": ranked[:limit],
        "stats": {
            "used_body_index": used_body_index,
            "loaded_shard_count": len(loaded_paths),
            "loaded_shard_paths": sorted(loaded_paths),
            "candidate_count": len(selected_candidate_indices),
            "quick_result_count": len(quick_ranked),
            "quick_results": quick_ranked[:limit],
            "candidate_shard_count": len(candidate_paths),
            "coverage": final_coverage,
            "proved_no_match_shards": proved_no_match_shards,
            "scanned_shards": scanned_shards,
            "exhaustive_complete": True,
        },
    }


def recall_documents(
    query: str,
    *,
    limit: int = 20,
    candidate_limit: int = 120,
    max_shard_loads: int = DEFAULT_MAX_SHARD_LOADS,
) -> list[dict[str, Any]]:
    return recall_documents_with_stats(
        query,
        limit=limit,
        candidate_limit=candidate_limit,
        max_shard_loads=max_shard_loads,
    )["results"]
