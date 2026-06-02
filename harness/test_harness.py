"""Simple runtime smoke tests for Adisn harness."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from harness import create_harness


def main() -> None:
    agent = create_harness()
    status_before = agent.get_state()
    result = agent.process_request("create a debug skill for npm build failures")
    status_after = agent.get_state()

    report = {
        "status_before": status_before,
        "request_result": result,
        "status_after": status_after,
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
