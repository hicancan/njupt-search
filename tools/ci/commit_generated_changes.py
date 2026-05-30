from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(args))
    return subprocess.run(args, check=check, text=True)


def capture(args: list[str]) -> str:
    return subprocess.check_output(args, text=True).strip()


def set_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def current_ref() -> str:
    return capture(["git", "rev-parse", "HEAD"])


def target_branch() -> str:
    return os.environ.get("GITHUB_REF_NAME") or capture(["git", "branch", "--show-current"]) or "main"


def has_staged_changes() -> bool:
    return subprocess.run(["git", "diff", "--staged", "--quiet"], check=False).returncode != 0


def push_with_rebase(branch: str, attempts: int) -> None:
    for attempt in range(1, attempts + 1):
        push = run(["git", "push", "origin", f"HEAD:{branch}"], check=False)
        if push.returncode == 0:
            return
        if attempt == attempts:
            raise SystemExit(f"git push failed after {attempts} attempts")
        print(f"Push failed on attempt {attempt}; rebasing onto origin/{branch} before retry.")
        run(["git", "fetch", "origin", branch])
        rebase = run(["git", "rebase", f"origin/{branch}"], check=False)
        if rebase.returncode != 0:
            run(["git", "rebase", "--abort"], check=False)
            raise SystemExit(f"Cannot rebase generated commit onto origin/{branch}; resolve the conflicting automation output.")
        time.sleep(2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--message", required=True)
    parser.add_argument("--add", nargs="+", required=True)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--changed-output", default="changed")
    parser.add_argument("--ref-output")
    args = parser.parse_args()

    run(["git", "config", "--global", "user.name", "github-actions[bot]"])
    run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"])
    run(["git", "add", *args.add])

    if not has_staged_changes():
        print("No generated changes.")
        set_output(args.changed_output, "false")
        if args.ref_output:
            set_output(args.ref_output, current_ref())
        return 0

    run(["git", "commit", "-m", args.message])
    push_with_rebase(target_branch(), args.attempts)
    set_output(args.changed_output, "true")
    if args.ref_output:
        set_output(args.ref_output, current_ref())
    return 0


if __name__ == "__main__":
    sys.exit(main())
