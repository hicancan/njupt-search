from config.indexer_config import CATEGORY_KEYWORDS, POSITIVE_KEYWORDS

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
