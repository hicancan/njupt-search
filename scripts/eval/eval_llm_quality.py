import json
import sys
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = BASE_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_evaluation(documents_path: str, manifest_path: str, strict: bool = True):
    docs = load_json(documents_path)
    manifest = load_json(manifest_path)
    
    total = len(docs)
    if total == 0:
        print("No documents found.")
        return 0
        
    llm_docs = [d for d in docs if d.get("semantic_mode") == "llm"]
    llm_total = len(llm_docs)
    
    errors = []
    
    # Check 0: manifest global values
    from core.llm_scorer import LLM_SCHEMA_VERSION

    if manifest.get("llm_schema_version") != LLM_SCHEMA_VERSION:
        errors.append(f"llm_schema_version {manifest.get('llm_schema_version')} != {LLM_SCHEMA_VERSION}")

    llm_stats = manifest.get("llm_stats") if isinstance(manifest.get("llm_stats"), dict) else {}
    skipped_by_limit = int(llm_stats.get("llm_skipped_by_limit", 0) or 0)
    if skipped_by_limit > 0:
        errors.append(f"llm_skipped_by_limit is {skipped_by_limit} instead of 0")

    semantic_mode_counts = manifest.get("semantic_mode_counts", {})
    if sum(semantic_mode_counts.values()) != total:
        errors.append(f"semantic_mode_counts sum ({sum(semantic_mode_counts.values())}) != total_documents ({total})")

    core_sources = ["jwc", "xsc", "pg", "ygb", "youth", "cxcy", "job", "lib"]
    for source in manifest.get("sources", []):
        if source.get("id") in core_sources and source.get("status") == "error":
            errors.append(f"Core source {source.get('id')} has status=error")

    # Check 1: semantic_mode=llm 的 field_sources 不得出现 heuristic
    for d in llm_docs:
        for f, source in d.get("field_sources", {}).items():
            if source == "heuristic":
                errors.append(f"Doc {d['id']} has heuristic source for field {f} but is semantic_mode=llm")
                
    # Check 2: provenance is recorded
    for d in docs:
        if not d.get("semantic_pipeline_version"):
            errors.append(f"Doc {d['id']} missing semantic_pipeline_version")

    # Check 3: task_frame_source_mode_counts.unknown 必须为 0
    tf_unknown = manifest.get("task_frame_source_mode_counts", {}).get("unknown", 0)
    if tf_unknown > 0:
        errors.append(f"Manifest has {tf_unknown} unknown task frames")
        
    # Check 4: deadline 有值时必须有 raw_field_presence.deadline
    for d in llm_docs:
        if d.get("deadline") and not d.get("raw_field_presence", {}).get("deadline") and not d.get("llm", {}).get("raw_field_presence", {}).get("deadline"):
            errors.append(f"Doc {d['id']} has deadline but raw_field_presence.deadline is false")
            
    # Check 5: action_required=true 时必须有 action_summary 或 task_frames
    for d in llm_docs:
        if d.get("action_required"):
            if not d.get("action_summary") and not d.get("task_frames"):
                errors.append(f"Doc {d['id']} has action_required=true but no action_summary or task_frames")
                
    # Check 6: field_source_counts should not have 100% nulls
    field_counts = manifest.get("field_source_counts", {})
    for field in ["review_required", "task_frames"]:
        field_nulls = field_counts.get(field, {}).get("null", 0)
        if field_nulls == total and total > 0:
            errors.append(f"field_source_counts.{field}.null == total ({total})")
                
    # Check metrics
    heuristic_degraded_count = manifest.get("semantic_mode_counts", {}).get("heuristic_degraded", 0)
    
    max_degraded = max(3, int(total * 0.05))
    if heuristic_degraded_count > max_degraded:
        errors.append(f"heuristic_degraded_count ({heuristic_degraded_count}) exceeds threshold ({max_degraded})")
        
    llm_purity_rate = manifest.get("llm_purity_rate", 1.0)
    if llm_purity_rate < 0.99:
        errors.append(f"llm_purity_rate ({llm_purity_rate}) is below 0.99")
        
    print(f"Evaluated {llm_total} LLM documents out of {total} total.")
    if errors:
        print("❌ LLM Quality Gate Failed:")
        for e in errors[:20]:
            print(f"  - {e}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more errors.")
        if strict:
            return 1
    else:
        print("✅ LLM Quality Gate Passed!")
    
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--documents", default="public/index/documents.json")
    parser.add_argument("--manifest", default="public/index/manifest.json")
    parser.add_argument("--no-strict", action="store_true", help="Do not exit with error code if failed")
    args = parser.parse_args()
    
    sys.exit(run_evaluation(args.documents, args.manifest, not args.no_strict))
