import json
from datetime import datetime
from typing import Any

from models.semantic_result import SemanticResult, SemanticMode
from core.heuristics import (
    infer_deadline, infer_action,
    clean_text, detect_sensitive_info, enrich_attachment_metadata,
    metadata_only_summary, is_low_evidence_content, SENSITIVE_MATERIAL_PATTERNS
)
from core.indexer_scoring import infer_tags
from core.semantic_verifier import verify_semantic_result
from config.indexer_config import CATEGORY_KEYWORDS
from models.semantic_model import (
    derive_display_category, extract_evidence, infer_domain, infer_intent, infer_lifecycle,
    normalize_category, normalize_domain, normalize_intent
)

SEMANTIC_PIPELINE_VERSION = "semantic-router-v2"

def _get_base_fields(entry: dict[str, Any], guard: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": entry.get("title", ""),
        "content": entry.get("canonical", {}).get("clean_text", "") or entry.get("content", ""),
        "source_type": entry.get("source_type", "central_admin"),
        "attachments": entry.get("attachments", []),
        "published_at": entry.get("published_at"),
        "default_category": entry.get("category", "公告"),
    }

def apply_safety_overrides(semantic: SemanticResult, guard: dict[str, Any]) -> SemanticResult:
    title = semantic.content.split(" ")[0] if semantic.content else ""
    attachments = semantic.attachments
    
    scoring_text = f"{title} {semantic.content}"
    regex_sensitive, regex_sensitive_types = detect_sensitive_info(scoring_text, attachments)
    
    sensitive = semantic.sensitive or regex_sensitive
    sensitive_types = sorted(set(semantic.sensitive_types).union(regex_sensitive_types))
    actual_sensitive_types = set(regex_sensitive_types).union(
        item for item in sensitive_types if item not in SENSITIVE_MATERIAL_PATTERNS
    )
    material_only_types = set(sensitive_types).intersection(SENSITIVE_MATERIAL_PATTERNS)
    
    if sensitive and material_only_types and not actual_sensitive_types:
        sensitive = False
        semantic.risk_flags = sorted(set(semantic.risk_flags).union({"requires_sensitive_material"}))
        
    if is_low_evidence_content(semantic.content, attachments):
        semantic.review_required = True
        semantic.risk_flags = sorted(set(semantic.risk_flags).union({"low_evidence_content"}))
        if not semantic.deadline:
            semantic.action_required = False
            semantic.action_type = None
            semantic.action_summary = None
        semantic.summary = "该页面正文主要是附件列表，已保留标题和附件角色，请点击原文或附件确认具体流程。"
        
    if sensitive:
        semantic.risk_flags = sorted(set(semantic.risk_flags).union({"sensitive_personal_info"}))
        semantic.summary = metadata_only_summary()
        semantic.content = " ".join([title, *[str(item.get("name", "")) for item in attachments]])
        
    semantic.sensitive = sensitive
    semantic.sensitive_types = sensitive_types
    
    return semantic

def apply_display_overrides(semantic: SemanticResult) -> SemanticResult:
    # Handle display logic for category, tags, domain, intent
    original_category = semantic.category
    original_domain = semantic.domain
    original_intent = semantic.intent

    if not semantic.domain:
        semantic.domain = "news"
        if "domain" not in semantic.field_sources or semantic.field_sources["domain"] == "llm_missing":
            semantic.field_sources["domain"] = "system_default"

    if not semantic.intent:
        semantic.intent = "read"
        if "intent" not in semantic.field_sources or semantic.field_sources["intent"] == "llm_missing":
            semantic.field_sources["intent"] = "system_default"
            
    semantic.domain = normalize_domain(semantic.domain)
    semantic.intent = normalize_intent(semantic.intent)
    semantic.category = normalize_category(semantic.category)

    if semantic.category not in CATEGORY_KEYWORDS and semantic.category != "公告":
        semantic.category = "公告"
        semantic.field_sources["category"] = "display_mapping"

    # Try to derive display category
    derived_category = derive_display_category(semantic.domain, semantic.intent, semantic.category or "公告")
    if derived_category != semantic.category:
        semantic.category = derived_category
        semantic.field_sources["category"] = "display_mapping"

    if semantic.category not in semantic.tags:
        semantic.tags = [semantic.category, *semantic.tags]
        
    return semantic


def derive_semantic_fields_llm(entry: dict[str, Any], llm_result: dict[str, Any], guard: dict[str, Any], now: datetime) -> SemanticResult:
    base = _get_base_fields(entry, guard)
    title = base["title"]
    content = base["content"]

    val = llm_result.get("validated", llm_result)
    raw_presence = llm_result.get("raw_field_presence", {})
    
    domain = val.get("domain")
    intent = val.get("intent")
    category = val.get("category")
    
    tags = [clean_text(str(tag)) for tag in (val.get("tags") or []) if clean_text(str(tag))]
    summary = clean_text(str(val.get("student_summary") or content[:180]))
    
    attachments = enrich_attachment_metadata(base["attachments"], val.get("attachment_roles") or [])
    
    conf_raw = val.get("confidence")
    confidence = float(conf_raw if conf_raw is not None else 0.5)
    
    review_required_raw = val.get("review_required")
    review_required = bool(review_required_raw if review_required_raw is not None else False)
    
    sensitive_raw = val.get("sensitive")
    sensitive = bool(sensitive_raw if sensitive_raw is not None else False)
    
    # Strictly isolate LLM sources using raw_presence
    field_sources = {
        "category": "llm" if raw_presence.get("category") else "llm_missing",
        "domain": "llm" if raw_presence.get("domain") else "llm_missing",
        "intent": "llm" if raw_presence.get("intent") else "llm_missing",
        "deadline": "llm" if raw_presence.get("deadline") else "llm_missing",
        "action_required": "llm" if raw_presence.get("action_required") else "llm_missing",
        "action_summary": "llm" if raw_presence.get("action_summary") else "llm_missing",
        "required_materials": "llm" if raw_presence.get("required_materials") else "llm_missing",
        "summary": "llm" if raw_presence.get("student_summary") else "llm_missing",
        "evidence": "llm" if raw_presence.get("evidence") else "llm_missing",
        "sensitive": "llm" if raw_presence.get("sensitive") else "llm_missing",
        "review_required": "llm" if raw_presence.get("review_required") else "llm_missing",
        "task_frames": "llm_raw_task_frame" if val.get("task_frames") else "empty_not_applicable"
    }
    
    val_out = {**val, "raw_field_presence": raw_presence}
    
    return SemanticResult(
        semantic_mode="llm",
        field_sources=field_sources,
        category=category,
        domain=domain,
        intent=intent,
        lifecycle=infer_lifecycle(base["published_at"], val.get("deadline"), now),
        evidence=[clean_text(str(item))[:180] for item in (val.get("evidence") or []) if clean_text(str(item))] or [],
        confidence=confidence,
        deadline=val.get("deadline"),
        action_required=bool(val.get("action_required", False)),
        action_type=val.get("action_type"),
        action_summary=val.get("action_summary"),
        required_materials=[clean_text(str(item.get("name") if isinstance(item, dict) else item)) for item in (val.get("required_materials") or []) if clean_text(str(item.get("name") if isinstance(item, dict) else item))],
        sensitive=sensitive,
        sensitive_types=[clean_text(str(item)) for item in (val.get("sensitive_types") or []) if clean_text(str(item))],
        review_required=review_required,
        risk_flags=[clean_text(str(item)) for item in (val.get("risk_flags") or []) if clean_text(str(item))],
        content=content,
        summary=summary,
        attachments=attachments,
        tags=tags,
        llm=val_out,
        raw_field_presence=raw_presence
    )


def derive_semantic_fields_heuristic(entry: dict[str, Any], guard: dict[str, Any], now: datetime, mode: SemanticMode = "heuristic") -> SemanticResult:
    base = _get_base_fields(entry, guard)
    title = base["title"]
    content = base["content"]
    scoring_text = f"{title} {content}"
    
    from update_search_index import infer_category
    rule_category = base["default_category"] if base["default_category"] in CATEGORY_KEYWORDS else infer_category(scoring_text)
    
    fallback_action_required, fallback_action_type, fallback_action_summary = infer_action(scoring_text)
    fallback_deadline = infer_deadline(scoring_text, base["published_at"], now)
    fallback_domain = infer_domain(scoring_text, rule_category, base["source_type"])
    fallback_intent = infer_intent(scoring_text, fallback_action_required, len(base["attachments"]))
    fallback_evidence = extract_evidence(
        scoring_text,
        [fallback_action_type or "", fallback_deadline or "", rule_category, title],
    )
    
    category = derive_display_category(fallback_domain, fallback_intent, rule_category)
    attachments = enrich_attachment_metadata(base["attachments"], [])
    
    field_sources = {k: "heuristic" for k in ["category", "domain", "intent", "deadline", "action_required", "action_summary", "summary", "evidence", "sensitive"]}
    field_sources["review_required"] = "system_default" if mode == "heuristic" else "heuristic_degraded"
    field_sources["task_frames"] = "heuristic_rule_frame"
    
    return SemanticResult(
        semantic_mode=mode,
        field_sources=field_sources,
        category=category,
        domain=fallback_domain,
        intent=fallback_intent,
        lifecycle=infer_lifecycle(base["published_at"], fallback_deadline, now),
        evidence=fallback_evidence[:4],
        confidence=0.35 if mode == "heuristic" else 0.2,
        deadline=fallback_deadline,
        action_required=fallback_action_required,
        action_type=fallback_action_type,
        action_summary=fallback_action_summary,
        required_materials=[],
        sensitive=False,
        sensitive_types=[],
        review_required=True,
        risk_flags=["heuristic_semantic"] if mode == "heuristic" else ["llm_failed_heuristic_fallback"],
        content=content,
        summary=content[:180],
        attachments=attachments,
        tags=infer_tags(scoring_text, category),
        llm={"used": False}
    )


def derive_semantic_fields_guarded(entry: dict[str, Any], guard: dict[str, Any], now: datetime) -> SemanticResult:
    base = _get_base_fields(entry, guard)
    scoring_text = f"{base['title']} {base['content']}"
    category = base["default_category"] if base["default_category"] in CATEGORY_KEYWORDS else "公告"
    domain = infer_domain(scoring_text, category, base["source_type"])
    field_sources = {k: "rule_guard" for k in ["category", "domain", "intent", "deadline", "action_required", "action_summary", "summary", "evidence", "sensitive", "review_required"]}
    field_sources["task_frames"] = "guarded_metadata_empty"
    
    return SemanticResult(
        semantic_mode="guarded_metadata",
        field_sources=field_sources,
        category=category,
        domain=domain,
        intent="read",
        lifecycle="active",
        evidence=[],
        confidence=1.0,
        deadline=None,
        action_required=False,
        action_type=None,
        action_summary=None,
        required_materials=[],
        sensitive=guard.get("sensitive", False),
        sensitive_types=guard.get("sensitive_types", []),
        review_required=True,
        risk_flags=guard.get("risk_flags", []),
        content=base["content"],
        summary="该页面访问受限或内容不足，请点击原文在允许的网络环境下查看。",
        attachments=base["attachments"],
        tags=[base["default_category"]],
        llm={"used": False}
    )

def route_semantic_pipeline(entry: dict[str, Any], llm_result: dict[str, Any] | None, guard: dict[str, Any], run_config: dict[str, Any], now: datetime) -> SemanticResult:
    if guard.get("restricted") or guard.get("sensitive") or guard.get("low_evidence") or guard.get("administrative_noise") or not guard.get("allow_llm", True):
        result = derive_semantic_fields_guarded(entry, guard, now)
    elif run_config.get("no_llm"):
        result = derive_semantic_fields_heuristic(entry, guard, now, mode="heuristic")
    elif llm_result and not llm_result.get("llm_failure"):
        result = derive_semantic_fields_llm(entry, llm_result, guard, now)
    else:
        # LLM was supposed to run but failed or didn't return a result
        result = derive_semantic_fields_heuristic(entry, guard, now, mode="heuristic_degraded")
        if llm_result and "llm_failure" in llm_result:
            result.llm_failure = llm_result["llm_failure"]
            
    result = apply_display_overrides(apply_safety_overrides(result, guard))
    return verify_semantic_result(
        result,
        title=str(entry.get("title", "")),
        source_text=str(entry.get("content") or entry.get("canonical", {}).get("clean_text", "")),
        attachments=list(entry.get("attachments", [])),
        guard=guard,
    )
