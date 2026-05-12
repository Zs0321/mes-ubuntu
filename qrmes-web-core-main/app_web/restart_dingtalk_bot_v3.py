#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


BOT_ROOT = Path("/volume2/qrmes-v3.0/qrmes-dingtalk-bot")


def run_script(script_name: str) -> subprocess.CompletedProcess[str]:
    script = BOT_ROOT / script_name
    if not script.exists():
        raise FileNotFoundError(f"missing script: {script}")
    return subprocess.run(
        [str(script)],
        cwd=str(BOT_ROOT),
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )


def main() -> int:
    if not BOT_ROOT.exists():
        print(f"missing bot root: {BOT_ROOT}", file=sys.stderr)
        return 1
    stop_result = run_script("stop.sh")
    start_result = run_script("start.sh")
    output = []
    if stop_result.stdout.strip():
        output.append(stop_result.stdout.strip())
    if stop_result.stderr.strip():
        output.append(stop_result.stderr.strip())
    if start_result.stdout.strip():
        output.append(start_result.stdout.strip())
    if start_result.stderr.strip():
        output.append(start_result.stderr.strip())
    print("\n".join(output))
    return start_result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
