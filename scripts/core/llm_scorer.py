import json
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

import requests
from pydantic import BaseModel, Field, ValidationError, field_validator

from config.indexer_config import (
    DEEPSEEK_API_BASE,
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
    GEMINI_API_KEYS,
    REQUEST_TIMEOUT,
)
from models.semantic_model import SEARCH_DOMAINS, SEARCH_INTENTS, normalize_domain, normalize_intent
from core.llm_task_frame import task_frame_prompt_contract
from core.evidence_pack import build_evidence_pack

LLM_SCHEMA_VERSION = "hytask-taskframe-v2.2"
GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
LLM_MODEL_NAME = DEEPSEEK_MODEL

LLM_BATCH_MAX_DOCS = int(os.environ.get("LLM_BATCH_MAX_DOCS", "32"))
LLM_BATCH_MAX_CHARS = int(os.environ.get("LLM_BATCH_MAX_CHARS", "250000"))
LLM_BATCH_MAX_OUTPUT_TOKENS = int(os.environ.get("LLM_BATCH_MAX_OUTPUT_TOKENS", "60000"))
LLM_REQUEST_TIMEOUT = max(REQUEST_TIMEOUT, int(os.environ.get("LLM_REQUEST_TIMEOUT", "120")))

_last_gemini_call_time = 0.0
_GEMINI_MIN_INTERVAL = 1.5
_gemini_keys: List[str] = [k.strip() for k in GEMINI_API_KEYS.split(",") if k.strip()] if GEMINI_API_KEYS else []
_current_gemini_key_index = 0

SearchCategory = Literal["考试", "选课", "竞赛", "奖助", "就业", "讲座", "生活", "研究生", "学院", "项目", "资料", "公告"]
SearchDomain = Literal[
    "academic", "exam", "course", "degree", "scholarship", "employment", "competition",
    "project", "innovation_project", "international", "life", "library", "security", "logistics",
    "campus_network", "subsidy", "medical_insurance", "archive", "lecture",
    "research", "resource", "news", "policy"
]
SearchIntent = Literal[
    "apply", "register", "submit", "attend", "check_result", "publicity", "download",
    "read", "schedule", "alert", "pay", "contact", "export"
]


class AttachmentRole(BaseModel):
    name: str = ""
    role: str | None = None
    description: str | None = None
    sensitive: bool = False


class LLMRawResult(BaseModel):
    audience: list[str] | None = None
    category: SearchCategory | None = None
    domain: SearchDomain | None = None
    intent: SearchIntent | None = None
    sub_category: str | None = None
    tags: list[str] | None = None
    deadline: str | None = None
    deadline_missing_reason: str | None = None
    action_required: bool | None = None
    action_missing_reason: str | None = None
    action_type: str | None = None
    action_summary: str | None = None
    required_materials: list[str] | None = None
    materials_missing_reason: str | None = None
    location: str | None = None
    location_missing_reason: str | None = None
    student_summary: str | None = None
    semantic_queries: list[str] | None = None
    query_phrases: list[str] | None = None
    sensitive: bool | None = None
    sensitive_types: list[str] | None = None
    attachment_roles: list[AttachmentRole] | None = None
    task_frames: list[dict[str, Any]] | None = None
    field_confidence: dict[str, float] | None = None
    field_evidence: dict[str, list[str]] | None = None
    risk_flags: list[str] | None = None
    evidence: list[str] | None = None
    confidence: float | None = None
    review_required: bool | None = None

    @field_validator("tags", "audience", "required_materials", "sensitive_types", "risk_flags", "evidence", mode="before")
    @classmethod
    def _coerce_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @field_validator("sub_category", "action_type", "action_summary", mode="before")
    @classmethod
    def _blank_to_none(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("location", mode="before")
    @classmethod
    def _coerce_location(cls, value: Any) -> str | None:
        if not value:
            return None
        if isinstance(value, dict):
            parts = [str(v) for v in value.values() if v]
            return ", ".join(parts) if parts else None
        return str(value).strip() or None

    @field_validator("deadline", mode="before")
    @classmethod
    def _validate_deadline(cls, value: Any) -> str | None:
        if not value:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            datetime.fromisoformat(text)
            return text
        except ValueError:
            return None

    @field_validator("attachment_roles", mode="before")
    @classmethod
    def _coerce_attachment_roles(cls, value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            return [{"role": text}] if text else []
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list):
            roles: list[dict[str, Any]] = []
            for item in value:
                if isinstance(item, dict):
                    roles.append(item)
                    continue
                text = str(item).strip()
                if text:
                    roles.append({"role": text})
            return roles
        return []

    @field_validator("field_evidence", mode="before")
    @classmethod
    def _coerce_field_evidence(cls, value: Any) -> dict[str, list[str]]:
        if not value or not isinstance(value, dict):
            return {}
        result: dict[str, list[str]] = {}
        for key, raw_items in value.items():
            if not isinstance(raw_items, list):
                continue
            strings = []
            for item in raw_items:
                if isinstance(item, str):
                    strings.append(item)
                elif isinstance(item, dict) and "text" in item:
                    strings.append(str(item["text"]))
            result[key] = strings
        return result

    @field_validator("task_frames", mode="before")
    @classmethod
    def _coerce_task_frames(cls, value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    @field_validator("domain", mode="before")
    @classmethod
    def _coerce_domain(cls, value: Any) -> str | None:
        if not value: return None
        return normalize_domain(value)

    @field_validator("intent", mode="before")
    @classmethod
    def _coerce_intent(cls, value: Any) -> str | None:
        if not value: return None
        return normalize_intent(value)

    @field_validator("category", mode="before")
    @classmethod
    def _coerce_category(cls, value: Any) -> str | None:
        if not value:
            return None
        text = str(value).strip()
        allowed = {"考试", "选课", "竞赛", "奖助", "就业", "讲座", "生活", "研究生", "学院", "项目", "资料", "公告"}
        if text in allowed:
            return text
        return "公告"


class LLMValidatedResult(BaseModel):
    raw: LLMRawResult
    raw_field_presence: dict[str, bool]
    validated: dict[str, Any]

class BatchLLMItem(LLMRawResult):
    id: str

class BatchLLMResult(BaseModel):
    results: list[BatchLLMItem] = Field(default_factory=list)


def provider_chain(provider: str = "auto") -> list[str]:
    selected = (provider or "auto").lower()
    if selected == "deepseek":
        return ["deepseek"] if DEEPSEEK_API_KEY else []
    if selected == "gemini":
        return ["gemini"] if _gemini_keys else []
    chain: list[str] = []
    if DEEPSEEK_API_KEY:
        chain.append("deepseek")
    if _gemini_keys:
        chain.append("gemini")
    return chain


def llm_enabled(provider: str = "auto") -> bool:
    return bool(provider_chain(provider))


def active_provider_name(provider: str = "auto") -> str:
    chain = provider_chain(provider)
    return chain[0] if chain else "none"


def active_model_name(provider: str = "auto") -> str | None:
    active = active_provider_name(provider)
    if active == "deepseek":
        return DEEPSEEK_MODEL
    if active == "gemini":
        return GEMINI_MODEL_NAME
    return None


def _get_next_gemini_key() -> Optional[str]:
    global _current_gemini_key_index
    if not _gemini_keys:
        return None
    key = _gemini_keys[_current_gemini_key_index % len(_gemini_keys)]
    _current_gemini_key_index += 1
    return key


def redact_for_log(value: Any) -> str:
    text = str(value)
    secrets = [DEEPSEEK_API_KEY, *_gemini_keys]
    for secret in secrets:
        if secret:
            text = text.replace(secret, "<redacted-key>")
    text = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer <redacted-key>", text, flags=re.I)
    text = re.sub(r"key=[^&\s)]+", "key=<redacted-key>", text, flags=re.I)
    text = re.sub(r"sk-[A-Za-z0-9_\-]+", "<redacted-key>", text)
    text = re.sub(r"AIza[0-9A-Za-z_\-]+", "<redacted-key>", text)
    text = re.sub(r"https://[^\s'\"<>]+", "<url>", text)
    return text[:500]


def _strip_provider_meta(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if not key.startswith("__llm_")}


def _document_payload_size(document: dict[str, Any]) -> int:
    return len(json.dumps(document, ensure_ascii=False, default=str))


def split_llm_batches(
    documents: list[dict[str, Any]],
    *,
    max_docs: int = LLM_BATCH_MAX_DOCS,
    max_chars: int = LLM_BATCH_MAX_CHARS,
) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    max_docs = max(1, max_docs)
    max_chars = max(2000, max_chars)

    for document in documents:
        doc_chars = _document_payload_size(document)
        if current and (len(current) >= max_docs or current_chars + doc_chars > max_chars):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(document)
        current_chars += doc_chars

    if current:
        batches.append(current)
    return batches


def _build_batch_prompt(documents: list[dict[str, Any]], schema_version: str) -> str:
    compact_documents = []
    for document in documents:
        pack = build_evidence_pack(document)
        pack["id"] = document["id"]
        pack["doc_id"] = document.get("doc_id") or document["id"]
        compact_documents.append(pack)

    prompt_template = """
你是南京邮电大学学生信息清洗助手。你的任务是把多条公开网页转成可验证的学生事务结构化数据。

硬性要求：
1. 只输出合法 JSON object，不要 Markdown；顶层必须是 {"results": [...]}。
2. 每个 results[i].id 必须原样使用输入文档 id；不得新增、改写、遗漏 id。
3. 不要编造原文没有的信息；标题暗示但正文没有证据时，降低 confidence 并设置 review_required=true。
4. deadline 必须是严格的 ISO 8601 格式（如 "2026-05-01T23:59:00+08:00"）。如果原文只有模糊描述（如“每年5月”、“开学前”），请将其写入 student_summary 或 action_summary 中，并将 deadline 设为 null！
5. 若正文显示“仅校内地址访问 / 请登录 / 无权访问 / 当前 IP 非校内地址”，不得推断行动事项，设置 review_required=true。
6. 分类只能使用给定枚举。竞赛只用于真实比赛/赛事/获奖/校赛；海外访学、创业基金、科研训练、交流项目优先归“项目”；奖助只用于奖学金、助学金、资助、评优，不要因为普通“公示”就归奖助。
7. 若含姓名、学号、手机号、身份证、名单、考生名单、获奖名单、参赛队员等个人信息风险，sensitive=true 并说明 sensitive_types。
8. domain 和 intent 必须从给定英文枚举中选择；evidence 必须摘自原文，不得编造。
9. Rule Guard 优先于 LLM。若 rule_guard.allow_llm=false 或 restricted/sensitive/low_evidence=true，不得生成具体 task_frames。
10. 访问受限页面 summary 只能表达访问受限，不得推断正文任务；敏感页面不得展开敏感正文。

__TASK_FRAME_CONTRACT__

Schema 版本: __SCHEMA_VERSION__
category 枚举: 考试|选课|竞赛|奖助|就业|讲座|生活|研究生|学院|项目|资料|公告
domain 枚举: __DOMAIN_ENUM__
intent 枚举: __INTENT_ENUM__

每个 result 的 JSON 字段：
{
  "id": "输入文档 id",
  "audience": ["本科生", "研究生"],
  "category": "公告",
  "domain": "news",
  "intent": "read",
  "sub_category": null,
  "tags": ["标签1", "标签2"],
  "deadline": null,
  "deadline_missing_reason": "no_explicit_deadline|ambiguous|not_applicable",
  "action_required": false,
  "action_missing_reason": "read_only_notice|no_student_action|unclear",
  "action_type": null,
  "action_summary": null,
  "required_materials": [],
  "materials_missing_reason": "not_applicable|not_found|unclear",
  "location": null,
  "location_missing_reason": "not_applicable|not_found|unclear",
  "student_summary": "一两句话概括核心信息，纯学生视角",
  "semantic_queries": ["大创申报", "SRTP项目要求"],
  "query_phrases": ["大学生创新训练", "项目申报"],
  "sensitive": false,
  "sensitive_types": [],
  "attachment_roles": [],
  "task_frames": [],
  "field_confidence": {
    "domain": 0.9,
    "intent": 0.9,
    "deadline": 0.0,
    "action": 0.8,
    "materials": 0.7,
    "location": 0.0
  },
  "field_evidence": {
    "domain": [],
    "intent": [],
    "deadline": [],
    "action": [],
    "materials": [],
    "location": [],
    "audience": []
  },
  "risk_flags": [],
  "evidence": ["原文中支撑分类、截止时间或行动事项的短句"],
  "confidence": 0.86,
  "review_required": false
}

输入文档 JSON：
__INPUT_DOCUMENTS__
"""

    return prompt_template.replace(
        "__TASK_FRAME_CONTRACT__", task_frame_prompt_contract()
    ).replace(
        "__SCHEMA_VERSION__", schema_version
    ).replace(
        "__DOMAIN_ENUM__", "|".join(SEARCH_DOMAINS)
    ).replace(
        "__INTENT_ENUM__", "|".join(SEARCH_INTENTS)
    ).replace(
        "__INPUT_DOCUMENTS__", json.dumps({"documents": compact_documents}, ensure_ascii=False)
    )


def _parse_batch_response(text: str, expected_ids: set[str], provider: str, model: str) -> dict[str, dict[str, Any]]:
    raw_json = json.loads(text)
    validated = BatchLLMResult.model_validate(raw_json)
    results: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    
    raw_items_map = {}
    for r_item in raw_json.get("results", []):
        if "id" in r_item:
            raw_items_map[str(r_item["id"])] = r_item

    for item in validated.results:
        if item.id not in expected_ids or item.id in seen:
            continue
        seen.add(item.id)
        
        raw_item = raw_items_map.get(item.id, {})
        raw_field_presence = {k: (k in raw_item) for k in LLMRawResult.model_fields.keys()}
        
        payload = item.model_dump()
        item_id = str(payload.pop("id"))
        
        final_payload = {
            "raw": payload,
            "raw_field_presence": raw_field_presence,
            "validated": payload,
            "__llm_provider": provider,
            "__llm_model": model
        }
        
        results[item_id] = final_payload
    return results


def _call_deepseek(prompt: str, max_output_tokens: int) -> tuple[str, str, str]:
    response = requests.post(
        f"{DEEPSEEK_API_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": "你只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": max_output_tokens,
            "stream": False,
        },
        timeout=LLM_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    choice = data["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RuntimeError("DeepSeek response exceeded max_tokens")
    text_result = choice["message"]["content"]
    return str(text_result), "deepseek", DEEPSEEK_MODEL


def _call_gemini(prompt: str, max_output_tokens: int) -> tuple[str, str, str]:
    global _last_gemini_call_time
    now = time.time()
    elapsed = now - _last_gemini_call_time
    if elapsed < _GEMINI_MIN_INTERVAL:
        time.sleep(_GEMINI_MIN_INTERVAL - elapsed)
    _last_gemini_call_time = time.time()

    key = _get_next_gemini_key()
    if not key:
        raise RuntimeError("Gemini API key is not configured")

    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL_NAME}:generateContent?key={key}",
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
                "maxOutputTokens": max_output_tokens,
            },
        },
        timeout=LLM_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    text_result = data["candidates"][0]["content"]["parts"][0]["text"]
    return str(text_result), "gemini", GEMINI_MODEL_NAME


def analyze_documents_batch_with_llm(
    documents: list[dict[str, Any]],
    *,
    provider: str = "auto",
    enabled: bool = True,
    schema_version: str = LLM_SCHEMA_VERSION,
    max_output_tokens: int = LLM_BATCH_MAX_OUTPUT_TOKENS,
) -> dict[str, dict[str, Any]]:
    if not enabled or not documents:
        return {}

    prompt = _build_batch_prompt(documents, schema_version)
    expected_ids = {str(document["id"]) for document in documents}
    errors: list[str] = []

    for candidate_provider in provider_chain(provider):
        text_result = ""
        try:
            if candidate_provider == "deepseek":
                text_result, used_provider, used_model = _call_deepseek(prompt, max_output_tokens)
            elif candidate_provider == "gemini":
                text_result, used_provider, used_model = _call_gemini(prompt, max_output_tokens)
            else:
                continue
            return _parse_batch_response(text_result, expected_ids, used_provider, used_model)
        except (ValidationError, json.JSONDecodeError, KeyError, IndexError, requests.RequestException, RuntimeError, UnicodeError) as exc:
            print(f"LLM provider {candidate_provider} failed: {redact_for_log(exc)}", flush=True)
            errors.append(f"{candidate_provider}: {redact_for_log(exc)}")
            continue

    print(f"LLM batch extraction error: all providers failed: {errors}")
    return {}


def analyze_document_with_llm(
    title: str,
    content: str,
    source_domain: str,
    *,
    enabled: bool = True,
    schema_version: str = LLM_SCHEMA_VERSION,
    provider: str = "auto",
) -> Optional[Dict[str, Any]]:
    results = analyze_documents_batch_with_llm(
        [{
            "id": "single",
            "title": title,
            "source": "",
            "source_domain": source_domain,
            "published_at": None,
            "content": content,
            "attachments": [],
        }],
        provider=provider,
        enabled=enabled,
        schema_version=schema_version,
    )
    return results.get("single")


def public_llm_result(result: dict[str, Any]) -> dict[str, Any]:
    return _strip_provider_meta(result)
