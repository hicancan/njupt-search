from __future__ import annotations

import base64
import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from njupt_search_indexer.sitegraph_binary_index import unpack_impact_index, unpack_impact_terms


BASE_DIR = Path(__file__).resolve().parents[4]
PUBLIC_ROOT = BASE_DIR / "apps" / "web" / "public"
PUBLIC_INDEX_DIR = PUBLIC_ROOT / "generated" / "collections" / "njupt-public"
SEARCH_INTENT_CONFIG = json.loads(
    (BASE_DIR / "packages" / "search-core" / "src" / "intent" / "queryIntentProfiles.json").read_text(encoding="utf-8")
)

FIELD_WEIGHTS = {key: float(value) for key, value in SEARCH_INTENT_CONFIG["field_weights"].items()}
DEFAULT_MAX_SHARD_LOADS = 32
ONE_MIB = 1024 * 1024
FIRST_TRUSTED_MAX_UNCACHED_BYTES = 5 * ONE_MIB
FIRST_TRUSTED_HYDRATION_RESERVE_BYTES = int(1.5 * ONE_MIB)
TOP_RESULTS_MAX_UNCACHED_BYTES = 10 * ONE_MIB
TOP_RESULTS_HYDRATION_RESERVE_BYTES = int(2.25 * ONE_MIB)
MIN_FIRST_TRUSTED_LOCAL_INDEXES = 6
MIN_TOP_RESULTS_LOCAL_INDEXES = 12
LIGHT_SEARCH_FIELDS = ["title", "section", "nav_path", "tags", "attachments", "external", "system"]
BODY_SEARCH_FIELDS = [*LIGHT_SEARCH_FIELDS, "summary", "content"]
FULL_SCAN_FIELDS = ["title", "section", "nav_path", "summary", "content", "attachments", "url"]


def new_cache_stats() -> dict[str, Any]:
    return {
        "scope": "memory_content_hash",
        "artifact_hits": 0,
        "artifact_misses": 0,
        "cached_bytes": 0,
        "uncached_bytes": 0,
        "cacheable_bytes": 0,
        "memory_hits": 0,
        "persistent_hits": 0,
        "network_misses": 0,
    }


def reset_cache_stats(index: dict[str, Any]) -> None:
    index["cache_stats"] = new_cache_stats()


def record_cache(index: dict[str, Any], hit: bool, bytes_count: int) -> None:
    stats = index.setdefault("cache_stats", new_cache_stats())
    safe_bytes = max(0, int(bytes_count or 0))
    stats["cacheable_bytes"] += safe_bytes
    if hit:
        stats["artifact_hits"] += 1
        stats["cached_bytes"] += safe_bytes
        stats["memory_hits"] = int(stats.get("memory_hits") or 0) + 1
    else:
        stats["artifact_misses"] += 1
        stats["uncached_bytes"] += safe_bytes
        stats["network_misses"] = int(stats.get("network_misses") or 0) + 1


def cache_snapshot(index: dict[str, Any]) -> dict[str, Any]:
    return dict(index.get("cache_stats") or new_cache_stats())


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return re.sub(r"\s+", "", text)


def tokens_for_query(query: str, aliases: dict[str, Any]) -> list[str]:
    candidates = expand_query_phrases(query, aliases)
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


def expand_query_phrases(query: str, aliases: dict[str, Any]) -> list[str]:
    candidates = [query]
    normalized_query = normalize_text(query)
    for key, payload in aliases.items():
        terms = [key]
        if isinstance(payload, dict) and isinstance(payload.get("aliases"), list):
            terms.extend(str(item) for item in payload["aliases"])
        if any(normalize_text(term) and normalize_text(term) in normalized_query for term in terms):
            candidates.extend(terms)
    return sorted({normalize_text(item) for item in candidates if len(normalize_text(item)) >= 2}, key=len, reverse=True)


def artifact_payload(manifest: dict[str, Any], name: str) -> Any:
    entry = manifest.get("artifacts", {}).get(name)
    if not isinstance(entry, dict) or not entry.get("path"):
        raise FileNotFoundError(f"manifest.artifacts.{name}.path is missing")
    return read_json(PUBLIC_ROOT / str(entry["path"]))


def load_index() -> dict[str, Any]:
    manifest = read_json(PUBLIC_INDEX_DIR / "manifest.json")
    return {
        "manifest": manifest,
        "source_registry": artifact_payload(manifest, "source_registry"),
        "global_query_directory": artifact_payload(manifest, "global_query_directory"),
        "aliases": artifact_payload(manifest, "query_aliases"),
        "source_manifest_cache": {},
        "local_light_cache": {},
        "local_body_cache": {},
        "shard_filter_cache": {},
        "proof_catalog_cache": {},
        "full_shard_cache": {},
        "cache_stats": new_cache_stats(),
    }


def source_entries_by_id(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["source_id"]): item
        for item in index["source_registry"]["sources"]
    }


def load_source_manifest(index: dict[str, Any], source_id: str) -> dict[str, Any] | None:
    cache = index["source_manifest_cache"]
    if source_id in cache:
        entry = source_entries_by_id(index).get(source_id)
        record_cache(index, True, int((entry or {}).get("artifact_manifest", {}).get("bytes") or 0))
        return cache[source_id]
    entry = source_entries_by_id(index).get(source_id)
    if not entry:
        return None
    path = PUBLIC_ROOT / str(entry["artifact_manifest"]["path"])
    payload = read_json(path)
    cache[source_id] = payload
    record_cache(index, False, int(entry["artifact_manifest"].get("bytes") or 0))
    return payload


def load_local_light(index: dict[str, Any], ref: dict[str, Any], terms: list[str]) -> dict[str, Any]:
    path = light_index_cache_key(ref)
    artifact = light_index_artifact(ref)
    cache_key = local_light_query_cache_key(path, artifact, terms)
    cache = index["local_light_cache"]
    if cache_key in cache:
        record_cache(index, True, int(artifact.get("bytes") or 0))
        return cache[cache_key]
    if "meta" in artifact and "packed" in artifact:
        payload = read_json(PUBLIC_ROOT / str(artifact["meta"]["path"]))
        packed_terms = unpack_impact_terms((PUBLIC_ROOT / str(artifact["packed"]["path"])).read_bytes(), terms)
        payload["terms"] = packed_terms.get("terms") or {}
        cache[cache_key] = payload
    else:
        cache[cache_key] = read_json(PUBLIC_ROOT / str(artifact["path"]))
    record_cache(index, False, int(artifact.get("bytes") or 0))
    return cache[cache_key]


def local_light_query_cache_key(path: str, artifact: dict[str, Any], terms: list[str]) -> str:
    return path if "packed" not in artifact else f"{path}\0{chr(0).join(sorted(set(terms)))}"


def load_local_body(index: dict[str, Any], ref: dict[str, Any], terms: list[str]) -> dict[str, Any]:
    artifact = body_index_artifact(ref)
    path = str(artifact["path"])
    cache_key = local_body_cache_key(path, terms)
    cache = index["local_body_cache"]
    if cache_key in cache:
        record_cache(index, True, int(artifact.get("bytes") or 0))
        return cache[cache_key]
    cache[cache_key] = unpack_impact_terms((PUBLIC_ROOT / path).read_bytes(), terms) if path.endswith(".bin") else read_json(PUBLIC_ROOT / path)
    record_cache(index, False, int(artifact.get("bytes") or 0))
    return cache[cache_key]


def local_body_cache_key(path: str, terms: list[str]) -> str:
    return path if not path.endswith(".bin") else f"{path}\0{chr(0).join(sorted(set(terms)))}"


def select_local_refs_within_budget(
    refs: list[dict[str, Any]],
    byte_budget: int,
    byte_size,
    minimum_refs: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    selected_bytes = 0
    for ref in refs:
        size = int(byte_size(ref))
        need_minimum_coverage = len(selected) < minimum_refs
        if not need_minimum_coverage and selected and selected_bytes + size > byte_budget:
            continue
        selected.append(ref)
        selected_bytes += size
    return selected or refs[:1]


def unique_local_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in refs:
        index_id = str(ref.get("index_id") or "")
        if index_id in seen:
            continue
        seen.add(index_id)
        selected.append(ref)
    return selected


def body_index_artifact(ref: dict[str, Any]) -> dict[str, Any]:
    packed = ref.get("body_index_packed")
    if isinstance(packed, dict) and packed.get("path"):
        return packed
    fallback = ref.get("body_index")
    if isinstance(fallback, dict) and fallback.get("path"):
        return fallback
    raise ValueError(f"local index missing body artifacts: {ref.get('index_id')}")


def light_index_artifact(ref: dict[str, Any]) -> dict[str, Any]:
    meta = ref.get("light_index_meta")
    packed = ref.get("light_index_packed")
    if isinstance(meta, dict) and meta.get("path") and isinstance(packed, dict) and packed.get("path"):
        return {
            "bytes": int(meta.get("bytes") or 0) + int(packed.get("bytes") or 0),
            "meta": meta,
            "packed": packed,
            "path": light_index_cache_key(ref),
        }
    fallback = ref.get("light_index")
    if isinstance(fallback, dict) and fallback.get("path"):
        return fallback
    raise KeyError(f"local index missing light artifacts: {ref.get('index_id')}")


def light_index_cache_key(ref: dict[str, Any]) -> str:
    meta = ref.get("light_index_meta")
    packed = ref.get("light_index_packed")
    if isinstance(meta, dict) and meta.get("path") and isinstance(packed, dict) and packed.get("path"):
        return f"{meta['path']}|{packed['path']}"
    fallback = ref.get("light_index")
    if isinstance(fallback, dict) and fallback.get("path"):
        return str(fallback["path"])
    raise KeyError(f"local index missing light artifacts: {ref.get('index_id')}")


def load_shard_filter(index: dict[str, Any], source_manifest: dict[str, Any]) -> dict[str, Any]:
    path = str(source_manifest["artifacts"]["shard_filter"]["path"])
    cache = index["shard_filter_cache"]
    bytes_count = int(source_manifest["artifacts"]["shard_filter"].get("bytes") or 0)
    if path in cache:
        record_cache(index, True, bytes_count)
        return cache[path]
    cache[path] = read_json(PUBLIC_ROOT / path)
    record_cache(index, False, bytes_count)
    return cache[path]


def load_proof_catalog(index: dict[str, Any], source_manifest: dict[str, Any]) -> dict[str, Any]:
    path = str(source_manifest["artifacts"]["proof_catalog"]["path"])
    cache = index["proof_catalog_cache"]
    bytes_count = int(source_manifest["artifacts"]["proof_catalog"].get("bytes") or 0)
    if path in cache:
        record_cache(index, True, bytes_count)
        return cache[path]
    cache[path] = read_json(PUBLIC_ROOT / path)
    record_cache(index, False, bytes_count)
    return cache[path]


def load_shard(index: dict[str, Any], path: str, bytes_count: int = 0) -> list[dict[str, Any]]:
    cache = index["full_shard_cache"]
    if path in cache:
        record_cache(index, True, bytes_count)
        return cache[path]
    payload = read_json(PUBLIC_ROOT / path)
    cache[path] = payload
    record_cache(index, False, bytes_count)
    return payload


def source_id_for(item: dict[str, Any]) -> str:
    if item.get("source_id"):
        return str(item["source_id"])
    provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
    if provenance.get("site_id"):
        return str(provenance["site_id"])
    return str(item.get("id") or "").split("-", 1)[0]


def includes_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(normalize_text(term) in text for term in terms)


def dynamic_system_authority_sources(text: str) -> list[str]:
    detection_config = SEARCH_INTENT_CONFIG["intent_detection"]
    for rule in detection_config["system_authority_rules"]:
        if includes_any(text, tuple(str(term) for term in rule["match_any"])):
            return [str(rule["source_id"])]
    return [str(source_id) for source_id in detection_config["system_default_authority_sources"]]


def detect_query_intent(query: str) -> dict[str, Any]:
    text = normalize_text(query)
    detection_config = SEARCH_INTENT_CONFIG["intent_detection"]
    for rule in detection_config["profiles"]:
        if not includes_any(text, tuple(str(term) for term in rule["match_any"])):
            continue
        raw_sources = rule["authority_sources"]
        authority_sources = (
            dynamic_system_authority_sources(text)
            if raw_sources == "dynamic_system"
            else [str(source_id) for source_id in raw_sources]
        )
        return {
            "intent": str(rule["intent"]),
            "authority_sources": authority_sources,
            "freshness_mode": str(rule["freshness_mode"]),
        }
    fallback = detection_config["fallback_profile"]
    return {
        "intent": str(fallback["intent"]),
        "authority_sources": [str(source_id) for source_id in fallback["authority_sources"]],
        "freshness_mode": str(fallback["freshness_mode"]),
    }


def route_for_terms(index: dict[str, Any], terms: list[str], intent: str) -> list[dict[str, Any]]:
    directory = index["global_query_directory"]
    routes: list[dict[str, Any]] = []
    seen: set[int] = set()
    for term in terms:
        route = directory.get("entries", {}).get(normalize_text(term))
        if isinstance(route, dict) and id(route) not in seen:
            seen.add(id(route))
            routes.append(route)
    intent_route = directory.get("intents", {}).get(intent)
    if isinstance(intent_route, dict) and id(intent_route) not in seen:
        routes.append(intent_route)
    return routes


def unique_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def build_plan(index: dict[str, Any], query: str, terms: list[str]) -> dict[str, Any]:
    profile = detect_query_intent(query)
    routes = route_for_terms(index, terms, profile["intent"])
    all_sources = [str(source["source_id"]) for source in index["source_registry"]["sources"]]
    route_sources = [str(source) for route in routes for source in route.get("likely_sources", [])]
    local_index_ids = [str(item) for route in routes for item in route.get("local_index_ids", [])]
    result_types = [str(item) for route in routes for item in route.get("expected_result_types", [])]
    route_decisions = [
        {
            "term": str(route.get("term") or profile["intent"]),
            "local_index_count": len(route.get("local_index_ids") or []),
            "expected_cost_bytes": int(route.get("expected_cost_bytes") or 0),
            "expected_utility_per_kb": float(route.get("expected_utility_per_kb") or 0.0),
            "likely_sources": [str(source) for source in route.get("likely_sources", [])],
            "likely_facets": [str(facet) for facet in route.get("likely_facets", [])],
        }
        for route in routes
    ]
    return {
        "normalized_query": normalize_text(query),
        "aliases": expand_query_phrases(query, index["aliases"]),
        "intent": profile["intent"],
        "authority_sources": profile["authority_sources"],
        "expected_result_types": unique_ordered(result_types),
        "source_ids": [source_id for source_id in unique_ordered([*profile["authority_sources"], *route_sources, *all_sources]) if source_id in all_sources],
        "local_index_ids": unique_ordered(local_index_ids),
        "verification_source_ids": all_sources,
        "declared_completion_scope": "global",
        "estimated_cost_bytes": sum(int(route["expected_cost_bytes"]) for route in route_decisions),
        "estimated_utility_per_kb": round(sum(float(route["expected_utility_per_kb"]) for route in route_decisions), 6),
        "route_decisions": route_decisions,
    }


def select_local_refs(index: dict[str, Any], plan: dict[str, Any], terms: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    source_manifests = [
        source_manifest
        for source_id in plan["source_ids"]
        if (source_manifest := load_source_manifest(index, source_id)) is not None
    ]
    planned_ids = set(plan["local_index_ids"])
    planned_order = {str(index_id): order for order, index_id in enumerate(plan["local_index_ids"])}
    refs = [ref for manifest in source_manifests for ref in manifest["local_indexes"]]

    route_facets = {facet for route in plan["route_decisions"] for facet in route["likely_facets"]}
    route_sources = {source for route in plan["route_decisions"] for source in route["likely_sources"]}

    def year_score(year: Any) -> float:
        try:
            return max(0.2, min(1.2, (float(year) - 2015) / 10))
        except (TypeError, ValueError):
            return 0.2

    def expected_uncached_bytes(ref: dict[str, Any]) -> int:
        light_artifact = light_index_artifact(ref)
        light_path = local_light_query_cache_key(str(light_artifact["path"]), light_artifact, terms)
        body_artifact = body_index_artifact(ref)
        body_path = local_body_cache_key(str(body_artifact["path"]), terms)
        light_bytes = 0 if light_path in index["local_light_cache"] else int(light_artifact["bytes"])
        body_bytes = 0 if body_path in index["local_body_cache"] else int(body_artifact["bytes"])
        return light_bytes + body_bytes

    def cache_state(ref: dict[str, Any]) -> str:
        light_artifact = light_index_artifact(ref)
        light_cached = local_light_query_cache_key(str(light_artifact["path"]), light_artifact, terms) in index["local_light_cache"]
        body_cached = local_body_cache_key(str(body_index_artifact(ref)["path"]), terms) in index["local_body_cache"]
        if light_cached and body_cached:
            return "warm"
        if light_cached or body_cached:
            return "partial"
        return "cold"

    def utility(ref: dict[str, Any]) -> float:
        scope = ref.get("scope") or {}
        routed = 4.0 if str(ref["index_id"]) in planned_ids else 1.0
        source_prior = 2.0 if str(scope.get("source_id")) in {*route_sources, *plan["authority_sources"]} else 1.0
        facet_prior = 1.5 if str(scope.get("facet")) in route_facets else 1.0
        cost_kb = max(1.0, expected_uncached_bytes(ref) / 1024)
        return round(routed * source_prior * facet_prior * year_score(scope.get("year")) * math.log2(int(ref.get("doc_count") or 0) + 2) / cost_kb, 6)

    if planned_ids:
        routed_refs = [ref for ref in refs if ref["index_id"] in planned_ids]
        if routed_refs:
            refs = sorted(
                routed_refs,
                key=lambda ref: (
                    -utility(ref),
                    planned_order.get(str(ref["index_id"]), 999_999),
                    -int(ref.get("doc_count") or 0),
                    str(ref["index_id"]),
                ),
            )[:48]
        else:
            refs = sorted(
                refs,
                key=lambda ref: (
                    -utility(ref),
                    -int(str(ref["scope"].get("year", "0")).replace("undated", "0") or 0),
                    -int(ref.get("doc_count") or 0),
                    str(ref["index_id"]),
                ),
            )[:48]
    else:
        refs = sorted(
            refs,
            key=lambda ref: (
                -utility(ref),
                -int(str(ref["scope"].get("year", "0")).replace("undated", "0") or 0),
                -int(ref.get("doc_count") or 0),
                str(ref["index_id"]),
            ),
        )[:48]
    source_manifest_bytes = sum(
        int(source_entries_by_id(index)[manifest["source_id"]]["artifact_manifest"]["bytes"])
        for manifest in source_manifests
    )
    plan["selected_local_indexes"] = [
        {
            "index_id": str(ref["index_id"]),
            "expected_bytes": int(light_index_artifact(ref)["bytes"]) + int(body_index_artifact(ref)["bytes"]),
            "expected_uncached_bytes": expected_uncached_bytes(ref),
            "cache_state": cache_state(ref),
            "utility_score": utility(ref),
            "source_id": str((ref.get("scope") or {}).get("source_id")),
            "facet": str((ref.get("scope") or {}).get("facet")),
            "year": str((ref.get("scope") or {}).get("year")),
        }
        for ref in refs
    ]
    plan["estimated_cost_bytes"] = int(plan["estimated_cost_bytes"]) + sum(item["expected_uncached_bytes"] for item in plan["selected_local_indexes"])
    return source_manifests, refs, source_manifest_bytes


def local_shard_maps(refs: list[dict[str, Any]], source_manifests: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, int]]:
    shard_path_by_id: dict[str, str] = {}
    shard_bytes_by_path: dict[str, int] = {}
    for ref in refs:
        for shard in ref.get("shards") or []:
            shard_path_by_id[str(shard["shard_id"])] = str(shard["path"])
            shard_bytes_by_path[str(shard["path"])] = int(shard.get("bytes") or 0)
    for source_manifest in source_manifests:
        for shard in source_manifest.get("full_shards") or []:
            shard_path_by_id[str(shard["shard_id"])] = str(shard["path"])
            shard_bytes_by_path[str(shard["path"])] = int(shard.get("bytes") or 0)
    return shard_path_by_id, shard_bytes_by_path


def proof_catalog_shards(index: dict[str, Any], source_manifests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    shards: list[dict[str, Any]] = []
    for source_manifest in source_manifests:
        catalog = load_proof_catalog(index, source_manifest)
        for shard in catalog.get("shards") or []:
            scope = shard.get("scope") or {}
            shards.append(
                {
                    "shard_id": str(shard["shard_id"]),
                    "source_id": str(shard["source_id"]),
                    "path": str(shard["path"]),
                    "bytes": int(shard["bytes"]),
                    "count": int(shard["document_count"]),
                    "facet_range": [str(item) for item in scope.get("facets") or []],
                    "record_type_range": [str(item) for item in scope.get("record_types") or []],
                    "section_range": [str(item) for item in scope.get("sections") or []],
                    "year_range": [str(item) for item in scope.get("years") or []],
                    "hash_bucket": str(scope.get("hash_bucket") or ""),
                }
            )
    if shards:
        return shards
    return [
        shard
        for source_manifest in source_manifests
        for shard in source_manifest.get("full_shards") or []
    ]


def text_blob(document: dict[str, Any], *fields: str) -> str:
    values: list[str] = []
    for field in fields:
        value = document.get(field)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value is not None:
            values.append(str(value))
    return normalize_text(" ".join(values))


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


def ranking_date_sort_value(document: dict[str, Any]) -> float:
    return date_sort_value(document.get("published_at")) or date_sort_value(document.get("version_date"))


def age_days(timestamp: float) -> float:
    return max(0.0, (datetime.now(timezone.utc).timestamp() - timestamp) / 86400)


def decayed_freshness(timestamp: float, max_score: float, horizon_days: float) -> float:
    if not timestamp:
        return 0.0
    return max(0.0, max_score - min(age_days(timestamp), horizon_days) / horizon_days * max_score)


def intent_freshness_score(document: dict[str, Any], mode: str) -> float:
    config = SEARCH_INTENT_CONFIG["ranking"]["freshness"].get(mode)
    if not isinstance(config, dict):
        return 0.0
    if mode == "official_entry":
        return float(config.get("system_facet_score") or 0.0) if document.get("facet") == "system" else 0.0
    timestamp = (
        date_sort_value(document.get("version_date")) or date_sort_value(document.get("published_at"))
        if mode == "form_version"
        else date_sort_value(document.get("published_at")) or date_sort_value(document.get("version_date"))
    )
    return decayed_freshness(
        timestamp,
        float(config.get("max_score") or 0.0),
        float(config.get("horizon_days") or 3650.0),
    )


def stale_penalty(document: dict[str, Any], mode: str) -> float:
    config = SEARCH_INTENT_CONFIG["ranking"]["stale_penalty"]
    if mode not in set(str(item) for item in config["modes"]):
        return 0.0
    value = date_sort_value(document.get("published_at")) or date_sort_value(document.get("version_date"))
    if not value:
        return 0.0
    days = age_days(value)
    for threshold in config["thresholds"]:
        threshold_modes = threshold.get("modes")
        if isinstance(threshold_modes, list) and mode not in set(str(item) for item in threshold_modes):
            continue
        if days > float(threshold["older_than_days"]):
            return float(threshold["score"])
    return 0.0


def is_short_landing_page(document: dict[str, Any], normalized_query: str, title: str) -> bool:
    return (
        title == normalized_query
        and document.get("facet") in {"workflow", "news", "notice_article"}
        and not date_sort_value(document.get("published_at"))
        and len(normalize_text(document.get("content"))) < 220
    )


def rank_document(document: dict[str, Any], query: str, terms: list[str], light_score: float) -> dict[str, Any]:
    profile = detect_query_intent(query)
    normalized_query = normalize_text(query)
    title = text_blob(document, "title")
    canonical_title = text_blob(document, "canonical_title")
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

    text_weights = SEARCH_INTENT_CONFIG["ranking"]["text_match"]
    term_weights = SEARCH_INTENT_CONFIG["ranking"]["term_match"]
    authority_weights = SEARCH_INTENT_CONFIG["ranking"]["authority"]
    score = light_score
    reasons: list[str] = []
    if normalized_query and (title == normalized_query or canonical_title == normalized_query):
        score += float(text_weights["system_title_exact"] if document.get("facet") == "system" else text_weights["title_exact"])
        reasons.append("标题精确")
    elif normalized_query and (normalized_query in title or normalized_query in canonical_title):
        score += float(text_weights["title_contains"])
        reasons.append("标题包含")
        if len(normalized_query) >= int(text_weights["long_query_min_length"]):
            score += float(text_weights["long_query_title_contains_extra"])
            reasons.append("标题短语命中")
    if normalized_query and normalized_query in attachment:
        score += float(text_weights["attachment_contains"])
        reasons.append("附件名命中")
    if normalized_query and normalized_query in external:
        score += float(text_weights["external_contains"])
        reasons.append("外部系统/外链命中")
    if normalized_query and normalized_query in url:
        score += float(text_weights["url_contains"])
        reasons.append("URL 命中")
    if normalized_query and normalized_query in section:
        score += float(text_weights["section_contains"])
        reasons.append("栏目路径命中")
    if normalized_query and normalized_query in content:
        score += float(text_weights["content_contains"])
        reasons.append("正文命中")
    if normalized_query and normalized_query in tags:
        score += float(text_weights["tags_contains"])
        reasons.append("标签命中")

    matched_terms = []
    for term in terms[:12]:
        if term in title or term in canonical_title:
            score += float(term_weights["title"])
            matched_terms.append(term)
        elif term in attachment:
            score += float(term_weights["attachment"])
            matched_terms.append(term)
        elif term in external:
            score += float(term_weights["external"])
            matched_terms.append(term)
        elif term in url:
            score += float(term_weights["url"])
            matched_terms.append(term)
        elif term in section:
            score += float(term_weights["section"])
            matched_terms.append(term)
        elif term in summary or term in content:
            score += float(term_weights["summary_or_content"])
            matched_terms.append(term)
    if matched_terms:
        reasons.append("词项: " + "、".join(sorted(set(matched_terms), key=len, reverse=True)[:6]))

    source_id = source_id_for(document)
    if source_id in profile["authority_sources"]:
        score += float(authority_weights["broad_source_boost"] if profile["intent"] == "broad_exploratory" else authority_weights["focused_source_boost"])
        reasons.append("权威来源")
    elif len(profile["authority_sources"]) == 1 and profile["intent"] != "broad_exploratory":
        score -= float(authority_weights["single_source_miss_penalty"])

    for boost in SEARCH_INTENT_CONFIG["ranking"]["facet_boosts"]:
        if document.get("facet") == boost["facet"] and profile["intent"] in set(str(item) for item in boost["intents"]):
            score += float(boost["score"])
            reasons.append(str(boost["reason"]))
    if normalize_text(document.get("task_kind")) == normalize_text(profile["intent"]):
        score += float(SEARCH_INTENT_CONFIG["ranking"]["task_kind_match"])
        reasons.append("任务匹配")

    freshness = intent_freshness_score(document, str(profile["freshness_mode"]))
    if freshness > 0:
        score += freshness
        freshness_config = SEARCH_INTENT_CONFIG["ranking"]["freshness"].get(str(profile["freshness_mode"]), {})
        reasons.append(str(freshness_config.get("reason") or "时间较新"))
    penalty = stale_penalty(document, str(profile["freshness_mode"]))
    if penalty > 0:
        score -= penalty
        reasons.append("历史内容降权")
    if profile["intent"] == "academic_policy" and is_short_landing_page(document, normalized_query, title):
        score -= float(SEARCH_INTENT_CONFIG["ranking"]["short_landing_page_penalty"])
        reasons.append("短入口降权")
    if profile["intent"] == "form_download" and document.get("record_type") == "external":
        score -= float(SEARCH_INTENT_CONFIG["ranking"]["form_download_external_penalty"])
        reasons.append("外链非下载降权")
    if profile["intent"] == "scholarship_aid" and "学业困难" in title and "家庭经济困难" not in title:
        score -= float(SEARCH_INTENT_CONFIG["ranking"]["scholarship_non_financial_hardship_penalty"])
        reasons.append("非资助困难降权")

    ranked = dict(document)
    ranked["score"] = round(score, 4)
    ranked["score_reason"] = "；".join(reasons or ["局部索引候选"])
    return ranked


def apply_impact_index(
    scores: dict[int, float],
    impact_terms: dict[str, Any],
    terms: list[str],
    retrieval: dict[str, Any],
    target_candidates: int,
) -> None:
    blocks: list[dict[str, Any]] = []
    for term in terms:
        term_payload = impact_terms.get(term)
        if not isinstance(term_payload, dict):
            continue
        for field, doc_ids in term_payload.items():
            impact = float(FIELD_WEIGHTS.get(field, 8.0) + min(len(term), 8))
            ids = [int(doc_id) for doc_id in doc_ids]
            for offset in range(0, len(ids), 32):
                blocks.append({"key": f"{term}\0{field}", "impact": impact, "ids": ids[offset: offset + 32]})
    blocks.sort(key=lambda item: (-float(item["impact"]), str(item["key"])))
    suffix = [0.0 for _ in range(len(blocks) + 1)]
    seen: set[str] = set()
    total = 0.0
    for index in range(len(blocks) - 1, -1, -1):
        key = str(blocks[index]["key"])
        if key not in seen:
            seen.add(key)
            total += float(blocks[index]["impact"])
        suffix[index] = total

    def threshold() -> float:
        if len(scores) < target_candidates:
            return float("-inf")
        return sorted(scores.values(), reverse=True)[target_candidates - 1]

    retrieval["dynamic_pruning"] = True
    for index, block in enumerate(blocks):
        current_threshold = threshold()
        if math.isfinite(current_threshold):
            retrieval["competitive_threshold"] = current_threshold
        max_possible = float(block["impact"]) + suffix[index + 1]
        has_known = any(doc_id in scores for doc_id in block["ids"])
        if not has_known and len(scores) >= target_candidates and max_possible <= current_threshold:
            retrieval["impact_blocks_pruned"] += 1
            retrieval["postings_pruned"] += len(block["ids"])
            continue
        retrieval["impact_blocks_visited"] += 1
        for doc_index in block["ids"]:
            retrieval["postings_visited"] += 1
            scores[int(doc_index)] = scores.get(int(doc_index), 0.0) + float(block["impact"])


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


def full_scan_matches(document: dict[str, Any], match_phrases: list[str]) -> bool:
    blob = full_scan_blob(document)
    return any(phrase in blob for phrase in match_phrases)


def filter_token_hash_int(text: str, seed: int) -> int:
    value = (2166136261 ^ seed) & 0xFFFFFFFF
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 16777619) & 0xFFFFFFFF
    return value


def shard_filter_phrase_tokens(phrase: str) -> list[str]:
    text = normalize_text(phrase)
    if not text:
        return []
    tokens: set[str] = set()
    matches = list(re.finditer(r"[\u4e00-\u9fff]{2,}|[a-z0-9][a-z0-9._-]{1,}", text))
    if not matches and len(text) >= 2:
        tokens.add(text)
    for match in matches:
        part = match.group(0)
        if re.fullmatch(r"[\u4e00-\u9fff]+", part):
            if len(part) <= 16:
                tokens.add(part)
            for size in range(2, min(5, len(part)) + 1):
                for index in range(0, len(part) - size + 1):
                    tokens.add(part[index : index + size])
        else:
            tokens.add(part)
    return sorted(tokens, key=len, reverse=True)


def shard_filter_proves_no_match(shard_id: str, shard_filter: dict[str, Any], match_phrases: list[str]) -> bool:
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

    phrases = [tokens for phrase in match_phrases if (tokens := shard_filter_phrase_tokens(phrase))]
    if not phrases:
        return False
    return all(any(not may_contain(token) for token in tokens) for tokens in phrases)


def sorted_ranked(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        results,
        key=lambda item: (
            -float(item.get("score") or 0),
            -ranking_date_sort_value(item),
            str(item.get("id") or ""),
        ),
    )


def first_screen_bytes(index: dict[str, Any]) -> int:
    artifacts = index["manifest"]["artifacts"]
    manifest_bytes = (PUBLIC_INDEX_DIR / "manifest.json").stat().st_size
    return manifest_bytes + sum(int(artifacts[name]["bytes"]) for name in ("source_registry", "global_query_directory", "query_aliases"))


def coverage(
    index: dict[str, Any],
    *,
    phase: str,
    fields: list[str],
    proved_no_match_shards: int,
    scanned_shards: int,
    searched_documents: int,
    total_shards: int,
    total_documents: int,
    loaded_paths: set[str],
    local_index_bytes: int,
    hydrated_shard_bytes: int,
    filter_bytes: int,
    used_body_index: bool,
    exhaustive_complete: bool,
    excluded_by_filter_shards: int = 0,
    failed_shards: int = 0,
) -> dict[str, Any]:
    first_bytes = first_screen_bytes(index)
    pending_shards = 0 if exhaustive_complete else max(0, total_shards - scanned_shards - proved_no_match_shards - excluded_by_filter_shards - failed_shards)
    ledger_complete = pending_shards == 0 and failed_shards == 0
    cache = cache_snapshot(index)
    return {
        "phase": phase,
        "coverage_state": phase,
        "scope": "global",
        "searched_fields": fields,
        "proved_no_match_shards": proved_no_match_shards,
        "scanned_shards": scanned_shards,
        "excluded_by_filter_shards": excluded_by_filter_shards,
        "excluded_by_declared_scope_shards": 0,
        "pending_shards": pending_shards,
        "failed_shards": failed_shards,
        "total_shards": total_shards,
        "searched_documents": searched_documents,
        "total_documents": total_documents,
        "loaded_bytes": first_bytes + local_index_bytes + hydrated_shard_bytes + filter_bytes,
        "uncached_loaded_bytes": cache["uncached_bytes"],
        "cached_artifact_bytes": cache["cached_bytes"],
        "first_screen_bytes": first_bytes,
        "local_index_bytes": local_index_bytes,
        "hydrated_shard_bytes": hydrated_shard_bytes,
        "used_body_index": used_body_index,
        "exhaustive_complete": exhaustive_complete and ledger_complete,
        "proof_ledger": {
            "total_shards": total_shards,
            "pending_shards": pending_shards,
            "scanned_shards": scanned_shards,
            "proved_no_match_shards": proved_no_match_shards,
            "excluded_by_filter_shards": excluded_by_filter_shards,
            "excluded_by_declared_scope_shards": 0,
            "failed_shards": failed_shards,
            "complete": ledger_complete,
        },
        "cache": cache,
    }


def shard_path_for_meta(meta: dict[str, Any], shard_path_by_id: dict[str, str]) -> str:
    shard = meta.get("shard") if isinstance(meta.get("shard"), dict) else {}
    return str(shard.get("path") or shard_path_by_id.get(str(shard.get("shard_id") or ""), ""))


def recall_documents_with_stats(
    query: str,
    *,
    limit: int = 20,
    candidate_limit: int = 160,
    max_shard_loads: int = DEFAULT_MAX_SHARD_LOADS,
    index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    index = index if index is not None else load_index()
    reset_cache_stats(index)
    started_at = datetime.now(timezone.utc)
    started_perf = math.nan
    try:
        import time

        started_perf = time.perf_counter()
    except Exception:
        started_perf = math.nan
    terms = tokens_for_query(query, index["aliases"])
    match_phrases = expand_query_phrases(query, index["aliases"])
    plan = build_plan(index, query, terms)
    source_manifests, local_refs, source_manifest_bytes = select_local_refs(index, plan, terms)
    shard_path_by_id, shard_bytes_by_path = local_shard_maps(local_refs, source_manifests)
    first_local_budget = max(
        0,
        FIRST_TRUSTED_MAX_UNCACHED_BYTES
        - first_screen_bytes(index)
        - source_manifest_bytes
        - FIRST_TRUSTED_HYDRATION_RESERVE_BYTES,
    )
    first_phase_refs = select_local_refs_within_budget(
        local_refs,
        first_local_budget,
        lambda ref: int(light_index_artifact(ref)["bytes"]),
        MIN_FIRST_TRUSTED_LOCAL_INDEXES,
    )
    top_local_budget = max(
        0,
        TOP_RESULTS_MAX_UNCACHED_BYTES
        - first_screen_bytes(index)
        - source_manifest_bytes
        - TOP_RESULTS_HYDRATION_RESERVE_BYTES,
    )
    top_phase_refs = unique_local_refs(
        [
            *first_phase_refs,
            *select_local_refs_within_budget(
                local_refs,
                top_local_budget,
                lambda ref: int(light_index_artifact(ref)["bytes"]) + int(body_index_artifact(ref)["bytes"]),
                MIN_TOP_RESULTS_LOCAL_INDEXES,
            ),
        ]
    )
    plan["phase_local_index_ids"] = {
        "first_trusted_results": [str(ref["index_id"]) for ref in first_phase_refs],
        "top_results_hydrated": [str(ref["index_id"]) for ref in top_phase_refs],
        "proof_complete": [str(ref["index_id"]) for ref in local_refs],
    }

    docs_by_index: dict[int, dict[str, Any]] = {}
    scores: dict[int, float] = {}
    retrieval = {
        "dynamic_pruning": False,
        "impact_blocks_visited": 0,
        "impact_blocks_pruned": 0,
        "postings_visited": 0,
        "postings_pruned": 0,
        "competitive_threshold": 0.0,
    }
    local_index_bytes = source_manifest_bytes
    loaded_local_index_ids: set[str] = set()
    for ref in first_phase_refs:
        local_index = load_local_light(index, ref, terms)
        local_index_bytes += int(light_index_artifact(ref)["bytes"])
        loaded_local_index_ids.add(str(ref["index_id"]))
        for document in local_index.get("documents", []):
            docs_by_index[int(document["doc_index"])] = document
        apply_impact_index(scores, local_index.get("terms", {}), terms, retrieval, candidate_limit)

    normalized_query = normalize_text(query)
    local_meta_fallbacks = 0
    if len(scores) < 8:
        for meta in docs_by_index.values():
            haystack = text_blob(meta, "title", "section", "nav_path_text")
            if normalized_query and normalized_query in haystack:
                index_id = int(meta["doc_index"])
                scores[index_id] = scores.get(index_id, 0.0) + 90.0
                local_meta_fallbacks += 1

    def select_candidates(limit_count: int, shard_limit: int) -> tuple[list[int], set[str]]:
        selected: list[int] = []
        paths: set[str] = set()
        for doc_index, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit_count]:
            meta = docs_by_index.get(doc_index)
            if not meta:
                continue
            path = shard_path_for_meta(meta, shard_path_by_id)
            is_new_shard = bool(path) and path not in paths
            if is_new_shard and len(paths) >= shard_limit:
                continue
            selected.append(doc_index)
            if is_new_shard:
                paths.add(path)
        return selected, paths

    def load_shards_for_paths(paths: set[str]) -> dict[int, dict[str, Any]]:
        docs: dict[int, dict[str, Any]] = {}
        for path in paths:
            for document in load_shard(index, path, shard_bytes_by_path.get(path, 0)):
                docs[int(document["doc_index"])] = document
        return docs

    quick_indices, quick_paths = select_candidates(min(candidate_limit, 48), min(max_shard_loads, 8))
    loaded_paths = set(quick_paths)
    quick_docs = load_shards_for_paths(quick_paths)
    quick_ranked = sorted_ranked([
        rank_document(quick_docs[doc_index], query, terms, scores.get(doc_index, 0.0))
        for doc_index in quick_indices
        if doc_index in quick_docs and full_scan_matches(quick_docs[doc_index], match_phrases)
    ])
    quick_hydrated_shard_bytes = sum(shard_bytes_by_path.get(path, 0) for path in loaded_paths)
    phase_timings_ms: dict[str, float] = {}
    if math.isfinite(started_perf):
        import time

        phase_timings_ms["first_trusted_results"] = round((time.perf_counter() - started_perf) * 1000, 3)
    first_trusted_coverage = coverage(
        index,
        phase="first_trusted_results",
        fields=LIGHT_SEARCH_FIELDS,
        proved_no_match_shards=0,
        scanned_shards=len(loaded_paths),
        searched_documents=len(quick_docs),
        total_shards=int(index["manifest"]["progressive_search"]["total_shards"]),
        total_documents=int(index["manifest"]["progressive_search"]["total_documents"]),
        loaded_paths=loaded_paths,
        local_index_bytes=local_index_bytes,
        hydrated_shard_bytes=quick_hydrated_shard_bytes,
        filter_bytes=0,
        used_body_index=False,
        exhaustive_complete=False,
    )

    used_body_index = False
    for ref in top_phase_refs:
        if str(ref["index_id"]) not in loaded_local_index_ids:
            local_index = load_local_light(index, ref, terms)
            local_index_bytes += int(light_index_artifact(ref)["bytes"])
            loaded_local_index_ids.add(str(ref["index_id"]))
            for document in local_index.get("documents", []):
                docs_by_index[int(document["doc_index"])] = document
            apply_impact_index(scores, local_index.get("terms", {}), terms, retrieval, candidate_limit)
        body_artifact = body_index_artifact(ref)
        body_index = load_local_body(index, ref, terms)
        local_index_bytes += int(body_artifact.get("bytes") or 0)
        apply_impact_index(scores, body_index.get("terms", {}), terms, retrieval, candidate_limit)
        used_body_index = True

    selected_candidate_indices, candidate_paths = select_candidates(candidate_limit, min(max_shard_loads, 18))
    new_candidate_paths = candidate_paths - loaded_paths
    loaded_paths |= candidate_paths
    full_docs = {**quick_docs, **load_shards_for_paths(new_candidate_paths)}
    ranked_by_id: dict[str, dict[str, Any]] = {
        str(item["id"]): item
        for item in quick_ranked
    }
    for doc_index in selected_candidate_indices:
        if doc_index not in full_docs or not full_scan_matches(full_docs[doc_index], match_phrases):
            continue
        item = rank_document(full_docs[doc_index], query, terms, scores.get(doc_index, 0.0))
        existing = ranked_by_id.get(str(item["id"]))
        if existing is None or float(item["score"]) > float(existing.get("score") or 0):
            ranked_by_id[str(item["id"])] = item
    top_hydrated_shard_bytes = sum(shard_bytes_by_path.get(path, 0) for path in loaded_paths)
    if math.isfinite(started_perf):
        import time

        phase_timings_ms["top_results_hydrated"] = round((time.perf_counter() - started_perf) * 1000, 3)
    top_results_coverage = coverage(
        index,
        phase="top_results_hydrated",
        fields=BODY_SEARCH_FIELDS,
        proved_no_match_shards=0,
        scanned_shards=len(loaded_paths),
        searched_documents=len(full_docs),
        total_shards=int(index["manifest"]["progressive_search"]["total_shards"]),
        total_documents=int(index["manifest"]["progressive_search"]["total_documents"]),
        loaded_paths=loaded_paths,
        local_index_bytes=local_index_bytes,
        hydrated_shard_bytes=top_hydrated_shard_bytes,
        filter_bytes=0,
        used_body_index=used_body_index,
        exhaustive_complete=False,
    )

    verification_manifests = [
        source_manifest
        for source in index["source_registry"]["sources"]
        if (source_manifest := load_source_manifest(index, str(source["source_id"]))) is not None
    ]
    in_scope_shards = proof_catalog_shards(index, verification_manifests)
    shard_filters = {
        str(source_manifest["source_id"]): load_shard_filter(index, source_manifest)
        for source_manifest in verification_manifests
    }
    filter_bytes = sum(
        int(source_manifest["artifacts"]["proof_catalog"]["bytes"]) + int(source_manifest["artifacts"]["shard_filter"]["bytes"])
        for source_manifest in verification_manifests
    )
    proved_no_match_shards = 0
    scanned_shards = 0
    searched_documents = 0
    verified_matches = 0
    for shard in in_scope_shards:
        shard_id = str(shard["shard_id"])
        source_id = str(shard.get("source_id") or "")
        if shard_filter_proves_no_match(shard_id, shard_filters.get(source_id, {}), match_phrases):
            proved_no_match_shards += 1
            continue
        path = str(shard["path"])
        loaded_paths.add(path)
        shard_bytes_by_path[path] = int(shard["bytes"])
        scanned_shards += 1
        for document in load_shard(index, path, int(shard["bytes"])):
            searched_documents += 1
            doc_index = int(document["doc_index"])
            if full_scan_matches(document, match_phrases):
                verified_matches += 1
                item = rank_document(document, query, terms, scores.get(doc_index, 24.0))
                existing = ranked_by_id.get(str(item["id"]))
                if existing is None or float(item["score"]) > float(existing.get("score") or 0):
                    ranked_by_id[str(item["id"])] = item

    ranked = sorted_ranked(list(ranked_by_id.values()))
    hydrated_shard_bytes = sum(shard_bytes_by_path.get(path, 0) for path in loaded_paths)
    final_coverage = coverage(
        index,
        phase="global_exhaustive_complete",
        fields=FULL_SCAN_FIELDS,
        proved_no_match_shards=proved_no_match_shards,
        scanned_shards=scanned_shards,
        searched_documents=searched_documents,
        total_shards=len(in_scope_shards),
        total_documents=sum(int(shard["count"]) for shard in in_scope_shards),
        loaded_paths=loaded_paths,
        local_index_bytes=local_index_bytes,
        hydrated_shard_bytes=hydrated_shard_bytes,
        filter_bytes=filter_bytes,
        used_body_index=used_body_index,
        exhaustive_complete=True,
    )
    if math.isfinite(started_perf):
        import time

        phase_timings_ms["proof_complete"] = round((time.perf_counter() - started_perf) * 1000, 3)
    return {
        "results": ranked[:limit],
        "stats": {
            "started_at": started_at.isoformat(),
            "used_body_index": used_body_index,
            "loaded_shard_count": len(loaded_paths),
            "loaded_shard_paths": sorted(loaded_paths),
            "loaded_local_index_count": len(loaded_local_index_ids),
            "loaded_local_index_ids": sorted(loaded_local_index_ids),
            "local_index_bytes": local_index_bytes,
            "hydrated_shard_bytes": hydrated_shard_bytes,
            "uncached_loaded_bytes": final_coverage["uncached_loaded_bytes"],
            "cached_artifact_bytes": final_coverage["cached_artifact_bytes"],
            "cache": final_coverage["cache"],
            "candidate_count": len(selected_candidate_indices),
            "quick_result_count": len(quick_ranked),
            "quick_results": quick_ranked[:limit],
            "candidate_shard_count": len(candidate_paths),
            "phase_coverages": {
                "first_trusted_results": first_trusted_coverage,
                "top_results_hydrated": top_results_coverage,
                "proof_complete": final_coverage,
            },
            "phase_timings_ms": phase_timings_ms,
            "coverage": final_coverage,
            "proved_no_match_shards": proved_no_match_shards,
            "scanned_shards": scanned_shards,
            "verified_full_scan_matches": verified_matches,
            "local_meta_fallback_documents": local_meta_fallbacks,
            "exhaustive_complete": True,
            "plan": plan,
            "retrieval": retrieval,
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
