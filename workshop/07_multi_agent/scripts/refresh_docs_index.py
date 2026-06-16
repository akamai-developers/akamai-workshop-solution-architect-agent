"""Refresh the local Akamai docs index used by the documentation agent.

The documentation agent grounds its answers in the real Akamai TechDocs. Those
docs publish an index at https://techdocs.akamai.com/llms.txt: a flat list of
every doc page with a short description. The file is about 1.8 MB and rarely
changes, so we keep it local and only re-download it when we want it updated.

The agent reads this local index, finds the pages that match a question, then
fetches those few pages live from the net. Run this script to update the index:

    python workshop/07_multi_agent/scripts/refresh_docs_index.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

INDEX_URL = "https://techdocs.akamai.com/llms.txt"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INDEX_PATH = DATA_DIR / "llms.txt"


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {INDEX_URL} ...")
    try:
        resp = httpx.get(INDEX_URL, timeout=60, follow_redirects=True)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - report and stop
        print(f"Failed to download the index: {exc}")
        return 1

    text = resp.text
    INDEX_PATH.write_text(text, encoding="utf-8")
    lines = text.count("\n") + 1
    kb = len(text.encode("utf-8")) / 1024
    print(f"Saved {INDEX_PATH} ({kb:.0f} KB, {lines} lines).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
