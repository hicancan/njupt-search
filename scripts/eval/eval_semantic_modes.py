import json
import os
from collections import Counter
import argparse

def main():
    parser = argparse.ArgumentParser(description="Evaluate semantic pipeline modes")
    parser.add_argument("--index-path", default="public/index", help="Path to index directory")
    args = parser.parse_args()

    manifest_path = os.path.join(args.index_path, "manifest.json")
    if not os.path.exists(manifest_path):
        print(f"Manifest not found at {manifest_path}")
        return

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    print("=== Semantic Pipeline Evaluation ===")
    print(f"Version: {manifest.get('semantic_pipeline_version', 'Unknown')}")
    print(f"Total Documents: {manifest.get('total_documents', 0)}")
    
    print("\n--- Semantic Modes ---")
    modes = manifest.get('semantic_mode_counts', {})
    for mode, count in modes.items():
        print(f"{mode}: {count}")
        
    print("\n--- Training Eligibility ---")
    print(f"Eligible for fine-tuning: {manifest.get('training_eligible_count', 0)}")
    print(f"Degraded heuristic fallbacks: {manifest.get('heuristic_degraded_count', 0)}")
    print(f"LLM Purity Rate: {manifest.get('llm_purity_rate', 0):.2%}")
    
    print("\n--- Task Frame Sources ---")
    task_frames = manifest.get('task_frame_source_mode_counts', {})
    for mode, count in task_frames.items():
        print(f"{mode}: {count}")

    print("\n--- LLM Missing Fields ---")
    missing_fields = manifest.get('llm_missing_field_counts', {})
    for field, count in missing_fields.items():
        print(f"{field}: {count}")

    print("\n--- Field Sources ---")
    sources = manifest.get('field_source_counts', {})
    for field, counts in sources.items():
        print(f"\n{field}:")
        for source, count in counts.items():
            print(f"  {source}: {count}")

if __name__ == "__main__":
    main()
