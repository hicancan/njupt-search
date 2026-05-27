from __future__ import annotations

import argparse

from . import analyze_and_update, auto_update_exam_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Update and process njupt-search exam artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("fetch", help="Fetch the latest exam spreadsheets from JWC.")
    subparsers.add_parser("process", help="Process downloaded exam spreadsheets into JSON artifacts.")
    subparsers.add_parser("run", help="Fetch and process exam artifacts.")
    args = parser.parse_args()

    if args.command in {"fetch", "run"}:
        result = auto_update_exam_data.find_latest_schedule_notification()
        if result:
            url, title = result
            auto_update_exam_data.process_detail_page(url, title)
        else:
            print("未进行任何更新。")
    if args.command in {"process", "run"}:
        analyze_and_update.main()
