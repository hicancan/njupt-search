import re


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+\-.#]*|[0-9]+|[\u4e00-\u9fff]{1,4}")


def tokenize_text(text: str) -> list[str]:
    normalized = str(text or "").lower()
    tokens = TOKEN_RE.findall(normalized)
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        if re.fullmatch(r"[\u4e00-\u9fff]{3,4}", token):
            expanded.extend(token[index:index + 2] for index in range(len(token) - 1))
    return [token for token in expanded if token.strip()]
