import re
from datetime import datetime
from typing import Any

from config.indexer_config import BEIJING_TZ

RESTRICTED_TEXT_PATTERNS = (
    "当前ip并非校内地址",
    "当前 ip 并非校内地址",
    "仅允许校内地址访问",
    "仅校内地址访问",
    "无权访问",
    "访问受限",
    "请登录",
    "登录后访问",
)

ACTION_KEYWORDS = ("报名", "申请", "申报", "提交", "报送", "填写", "缴费", "确认", "加入")

SENSITIVE_PATTERNS = (
    "个人信息",
    "考生名单",
    "获奖名单",
    "名单公示",
    "参赛队员",
    "学号",
)

SENSITIVE_MATERIAL_PATTERNS = ("身份证", "学生证", "营业执照")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def parse_date(text: str, now: datetime) -> str | None:
    patterns = [
        r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})",
        r"(20\d{2})(\d{2})(\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            year, month, day = match.groups()
            try:
                return datetime(int(year), int(month), int(day), tzinfo=BEIJING_TZ).date().isoformat()
            except ValueError:
                return None

    month_day = re.search(r"(?<!\d)(\d{1,2})[-/.月](\d{1,2})(?:日)?(?!\d)", text)
    if month_day:
        month, day = month_day.groups()
        try:
            candidate = datetime(now.year, int(month), int(day), tzinfo=BEIJING_TZ)
            if (candidate - now).days > 30:
                candidate = datetime(now.year - 1, int(month), int(day), tzinfo=BEIJING_TZ)
            return candidate.date().isoformat()
        except ValueError:
            return None

    return None


def is_expired(published_at: str | None, now: datetime) -> bool:
    if not published_at:
        return False
    try:
        pub_date = datetime.fromisoformat(published_at).date()
        return (now.date() - pub_date).days > 365
    except Exception:
        return False


def is_restricted_content(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.lower())
    return any(re.sub(r"\s+", "", pattern.lower()) in compact for pattern in RESTRICTED_TEXT_PATTERNS)


def parse_deadline_candidate(year: int, month: int, day: int, marker: str | None = None, hour: str | None = None, minute: str | None = None) -> str | None:
    try:
        parsed_hour = int(hour) if hour else 23
        parsed_minute = int(minute) if minute else 59
        if marker in {"下午", "晚上"} and parsed_hour < 12:
            parsed_hour += 12
        if marker == "中午" and not hour:
            parsed_hour = 12
            parsed_minute = 0
        value = datetime(year, month, day, parsed_hour, parsed_minute, tzinfo=BEIJING_TZ)
        return value.isoformat()
    except ValueError:
        return None


def infer_deadline(text: str, published_at: str | None, now: datetime) -> str | None:
    reference_year = now.year
    if published_at:
        try:
            reference_year = datetime.fromisoformat(published_at).year
        except ValueError:
            pass

    explicit_before = re.search(
        r"(?:截止|截止时间|报名截止|申报截止|于|请.*?于)\s*"
        r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
        r"(?:\s*(上午|下午|中午|晚上)?\s*(\d{1,2})\s*[:：点]\s*(\d{0,2})?)?\s*前",
        text,
    )
    if explicit_before:
        year, month, day, marker, hour, minute = explicit_before.groups()
        return parse_deadline_candidate(int(year), int(month), int(day), marker, hour, minute or None)

    full_range = re.search(
        r"(20\d{2})\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日"
        r"(?:\s*\d{1,2}\s*[:：点]\s*\d{0,2})?\s*(?:至|到|-|—)"
        r"\s*(?:(20\d{2})\s*年)?\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
        r"(?:\s*(上午|下午|中午|晚上)?\s*(\d{1,2})\s*[:：点]\s*(\d{0,2})?)?",
        text,
    )
    if full_range:
        start_year, end_year, month, day, marker, hour, minute = full_range.groups()
        return parse_deadline_candidate(int(end_year or start_year), int(month), int(day), marker, hour, minute or None)

    month_day_before = re.search(
        r"(?:截止|截止时间|报名截止|申报截止|于|请.*?于)\s*"
        r"(\d{1,2})\s*月\s*(\d{1,2})\s*日"
        r"(?:\s*(上午|下午|中午|晚上)?\s*(\d{1,2})\s*[:：点]\s*(\d{0,2})?)?\s*前",
        text,
    )
    if month_day_before:
        month, day, marker, hour, minute = month_day_before.groups()
        return parse_deadline_candidate(reference_year, int(month), int(day), marker, hour, minute or None)

    return None


def infer_action(text: str) -> tuple[bool, str | None, str | None]:
    for keyword in ACTION_KEYWORDS:
        if keyword in text:
            sentence_match = re.search(r"[^。；;.!！?？]{0,80}" + re.escape(keyword) + r"[^。；;.!！?？]{0,120}", text)
            summary = clean_text(sentence_match.group(0)) if sentence_match else None
            return True, keyword, summary
    return False, None, None


def infer_attachment_role(name: str) -> tuple[str | None, bool]:
    if any(keyword in name for keyword in ("申请表", "申报表", "报名表")):
        return "申请表", False
    if "汇总表" in name:
        return "汇总表", False
    if any(keyword in name for keyword in ("名单", "考生", "获奖")):
        return "名单", True
    if any(keyword in name for keyword in ("简章", "简介", "说明", "项目介绍")):
        return "项目说明", False
    if "通知" in name:
        return "通知正文", False
    if "流程" in name:
        return "流程说明", False
    return None, False


def enrich_attachment_metadata(
    attachments: list[dict[str, Any]],
    llm_roles: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    normalized_roles = [item for item in (llm_roles or []) if isinstance(item, dict)]
    role_by_name = {
        clean_text(str(item.get("name", ""))): item
        for item in normalized_roles
        if clean_text(str(item.get("name", "")))
    }
    unnamed_roles = [item for item in normalized_roles if not clean_text(str(item.get("name", "")))]
    enriched: list[dict[str, Any]] = []
    for index, attachment in enumerate(attachments):
        name = clean_text(str(attachment.get("name", "")))
        inferred_role, inferred_sensitive = infer_attachment_role(name)
        llm_role = role_by_name.get(name) or (unnamed_roles[index] if index < len(unnamed_roles) else {})
        role = clean_text(str(llm_role.get("role") or inferred_role or "")) or None
        description = clean_text(str(llm_role.get("description") or "")) or None
        sensitive = bool(llm_role.get("sensitive", False)) or inferred_sensitive
        enriched.append({
            **attachment,
            "role": role,
            "description": description,
            "sensitive": sensitive,
        })
    return enriched


def detect_sensitive_info(text: str, attachments: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    sensitive_types: set[str] = set()
    combined = " ".join([text, *[str(item.get("name", "")) for item in attachments]])
    for pattern in SENSITIVE_PATTERNS:
        if pattern in combined:
            sensitive_types.add(pattern)
    if re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)", combined):
        sensitive_types.add("手机号")
    if re.search(r"(?<!\d)\d{17}[\dXx](?!\d)", combined):
        sensitive_types.add("身份证")
    if any(item.get("sensitive") for item in attachments):
        sensitive_types.add("敏感附件")
    return bool(sensitive_types), sorted(sensitive_types)


def is_low_evidence_content(content: str, attachments: list[dict[str, Any]]) -> bool:
    if not attachments:
        return False
    remaining = content
    for attachment in attachments:
        name = str(attachment.get("name", ""))
        if name:
            remaining = remaining.replace(name, " ")
    remaining = re.sub(r"附件\s*\d*[：:、]?", " ", remaining)
    remaining = clean_text(remaining)
    return len(remaining) < 40


def metadata_only_summary() -> str:
    return "该通知可能包含名单、学号或联系方式等个人信息，已按元数据索引；请查看原文确认详情。"
