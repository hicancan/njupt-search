import os
import json
import sys
import requests

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from config.indexer_config import GITHUB_SOURCE_CONFIG_PATH
from core.indexer_scoring import infer_category

# This script fetches high star njupt repos and appends them to config/github_search_sources.json
CONFIG_PATH = GITHUB_SOURCE_CONFIG_PATH
GITHUB_TOKEN = os.environ.get("NJUPT_SEARCH_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")

def fetch_top_njupt_repos():
    url = "https://api.github.com/search/repositories?q=njupt&sort=stars&order=desc&per_page=30"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "njupt-search-auto-updater"
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data.get("items", [])
    except Exception as e:
        print(f"Error fetching github repos: {e}")
        return []

def update_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
        
    existing_repos = {item["repo"].lower() for item in config.get("sources", [])}
    items = fetch_top_njupt_repos()
    
    new_sources = []
    for item in items:
        repo_full_name = item["full_name"]
        stars = item["stargazers_count"]
        description = item["description"] or repo_full_name
        
        if repo_full_name.lower() in existing_repos:
            continue
            
        if stars < 10: # Only repos with at least 10 stars
            continue
            
        # Add to config
        new_source = {
            "repo": repo_full_name,
            "label": description[:30] + ("..." if len(description) > 30 else ""),
            "category": infer_category(description),
            "audience": ["本科生", "研究生"],
            "include": ["README.md", "*.md"],
            "exclude": ["**/node_modules/**", "**/dist/**", "**/build/**", "**/.git/**"],
            "max_files": 5,
            "source_weight": 0.5,
            "enabled": True
        }
        new_sources.append(new_source)
        existing_repos.add(repo_full_name.lower())
        
    if new_sources:
        print(f"Adding {len(new_sources)} new repos to config.")
        config.setdefault("sources", []).extend(new_sources)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.write("\n")
    else:
        print("No new repos to add.")

if __name__ == "__main__":
    update_config()
