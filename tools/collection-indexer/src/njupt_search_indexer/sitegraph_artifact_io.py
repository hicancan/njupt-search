from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def write_json(path: Path, payload: Any, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        if compact:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")


def json_bytes(payload: Any, *, compact: bool = True) -> bytes:
    if compact:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    return text.encode("utf-8")


def write_hashed_json(
    public_root: Path,
    directory: Path,
    logical_name: str,
    payload: Any,
    *,
    compact: bool = True,
) -> dict[str, Any]:
    data = json_bytes(payload, compact=compact)
    digest = hashlib.sha256(data).hexdigest()
    filename = f"{logical_name}.{digest[:16]}.json"
    path = directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {
        "path": str(path.relative_to(public_root)).replace("\\", "/"),
        "sha256": digest,
        "bytes": len(data),
    }


def artifact_entry(
    artifact: dict[str, Any],
    *,
    role: str,
    count: int | None = None,
    load: str = "on_demand",
) -> dict[str, Any]:
    entry = {
        "path": artifact["path"],
        "sha256": artifact["sha256"],
        "bytes": artifact["bytes"],
        "role": role,
        "load": load,
    }
    if count is not None:
        entry["count"] = count
    return entry
