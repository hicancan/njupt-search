import re
from datetime import datetime
from indexer_config import CATEGORY_KEYWORDS, POSITIVE_KEYWORDS, NEGATIVE_KEYWORDS, MIN_STUDENT_SCORE, BEIJING_TZ

def calculate_freshness(published_at: str | None, now: datetime) -> float:
    if not published_at:
        return 0.45
    try:
        published = datetime.fromisoformat(published_at).replace(tzinfo=BEIJING_TZ)
    except ValueError:
        return 0.45

    days = (now - published).days
    if days < 0:
        return 0.92
    if days <= 3:
        return 1.0
    if days <= 7:
        return 0.92
    if days <= 30:
        return 0.78
    if days <= 180:
        return 0.58
    return 0.42

def infer_category(text: str) -> str:
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        scores[category] = sum(1 for keyword in keywords if keyword.lower() in text.lower())

    best_category = max(scores, key=scores.get)
    if scores[best_category] == 0:
        return "公告"
    return best_category

def infer_tags(text: str, category: str) -> list[str]:
    tags = [category]
    for keyword in POSITIVE_KEYWORDS:
        if keyword.lower() in text.lower() and keyword not in tags:
            tags.append(keyword)
    return tags[:8]

def calculate_student_score(text: str, source_weight: float) -> float:
    positive_hits = sum(1 for keyword in POSITIVE_KEYWORDS if keyword.lower() in text.lower())
    category_hits = sum(
        1
        for keywords in CATEGORY_KEYWORDS.values()
        for keyword in keywords
        if keyword.lower() in text.lower()
    )
    negative_hits = sum(1 for keyword in NEGATIVE_KEYWORDS if keyword.lower() in text.lower())
    score = (
        0.32
        + positive_hits * 0.08
        + min(category_hits, 5) * 0.045
        + source_weight * 0.18
        - negative_hits * 0.16
    )
    return round(max(0.05, min(1.0, score)), 4)

def is_student_facing_document(document: dict) -> bool:
    text = f"{document['title']} {document.get('content', '')}"
    category = document.get("category", "公告")
    negative_hits = sum(1 for keyword in NEGATIVE_KEYWORDS if keyword.lower() in text.lower())
    threshold_by_category = {
        "公告": 0.68, "资料": 0.62, "学院": 0.58,
        "讲座": 0.56, "生活": 0.54, "项目": 0.56,
    }

    if negative_hits > 0 and document["student_score"] < 0.74:
        return False

    threshold = threshold_by_category.get(str(category), MIN_STUDENT_SCORE)
    return document["student_score"] >= threshold

def calculate_importance_score(text: str, category: str, attachments_count: int, source_weight: float) -> float:
    category_bonus = {
        "考试": 0.18, "选课": 0.14, "竞赛": 0.13,
        "奖助": 0.13, "就业": 0.12, "生活": 0.1,
        "研究生": 0.1,
    }.get(category, 0.04)
    title_bonus = 0.1 if any(keyword in text for keyword in ("通知", "公示", "安排", "报名", "开放")) else 0
    attachment_bonus = min(0.08, attachments_count * 0.025)
    score = 0.48 + source_weight * 0.18 + category_bonus + title_bonus + attachment_bonus
    return round(max(0.05, min(1.0, score)), 4)
