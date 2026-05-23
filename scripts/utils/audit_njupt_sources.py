import json
import os
import re
import sys
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from config.indexer_config import CAMPUS_SOURCE_CONFIG_PATH, HEADERS, REQUEST_TIMEOUT

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


OFFICIAL_INDEX_URLS = (
    "https://www.njupt.edu.cn/jxjg/list.htm",
    "https://www.njupt.edu.cn/17352/list.htm",
    "https://www.njupt.edu.cn/kyjg/list.htm",
    "https://www.njupt.edu.cn/17354/list.htm",
)

EXCLUDED_DOMAINS = {
    "i.njupt.edu.cn",
    "mail.njupt.edu.cn",
    "campus.njupt.edu.cn",
}


def fetch_html(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, verify=False)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def configured_domains() -> set[str]:
    with open(CAMPUS_SOURCE_CONFIG_PATH, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    domains: set[str] = set()
    for source in payload.get("sources", []):
        if isinstance(source, dict) and source.get("enabled", True):
            domain = urlparse(str(source.get("base_url", ""))).netloc.lower()
            if domain:
                domains.add(domain)
    return domains


def discover_domains() -> dict[str, list[str]]:
    discovered: dict[str, list[str]] = {}
    for index_url in OFFICIAL_INDEX_URLS:
        soup = BeautifulSoup(fetch_html(index_url), "html.parser")
        for anchor in soup.find_all("a"):
            href = anchor.get("href")
            text = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True)).strip()
            if not href:
                continue
            absolute_url = urljoin(index_url, href)
            domain = urlparse(absolute_url).netloc.lower()
            if not domain.endswith("njupt.edu.cn") or domain in EXCLUDED_DOMAINS:
                continue
            discovered.setdefault(domain, [])
            if text and text not in discovered[domain]:
                discovered[domain].append(text)
    return discovered


def main() -> None:
    configured = configured_domains()
    discovered = discover_domains()
    missing = {
        domain: names[:3]
        for domain, names in discovered.items()
        if domain not in configured
    }
    report = {
        "official_index_urls": OFFICIAL_INDEX_URLS,
        "configured_domains": sorted(configured),
        "discovered_domains": sorted(discovered),
        "missing_domains": missing,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
