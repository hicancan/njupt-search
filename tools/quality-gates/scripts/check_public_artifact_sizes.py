from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
PUBLIC_ROOT = ROOT / "apps" / "web" / "public"
COLLECTION_DIR = PUBLIC_ROOT / "generated" / "collections" / "njupt-public"

SIZE_BUDGETS = {
    "first_screen_total_bytes": 16_000_000,
    "body_index_bytes": 19_000_000,
    "full_shard_count": 650,
    "max_full_shard_bytes": 512 * 1024,
    "avg_full_shard_bytes": 96 * 1024,
}


def fail(message: str) -> None:
    print(f"[check_public_artifact_sizes] {message}", file=sys.stderr)
    raise SystemExit(1)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    manifest = read_json(COLLECTION_DIR / "manifest.json")
    size_entry = (manifest.get("artifacts") or {}).get("size_report") or {}
    size_path = PUBLIC_ROOT / str(size_entry.get("path") or "")
    if not size_path.exists():
        fail(f"size_report artifact is missing: {size_path}")
    size_report = read_json(size_path)

    for field, budget in SIZE_BUDGETS.items():
        actual = size_report.get(field)
        if actual is None:
            fail(f"size_report missing {field}")
        if float(actual) > budget:
            fail(f"{field}={actual} exceeds budget {budget}")
    print("[check_public_artifact_sizes] ok")


if __name__ == "__main__":
    main()
