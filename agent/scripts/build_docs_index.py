"""Bake the semantic page index at build time (NO crawl).

Reads data/llms.txt, builds a retrieval doc per page (title + URL-path words +
any description), embeds them with the baked ONNX model (fastembed, no torch),
and writes data/docs_index/{embeddings.npy, entries.jsonl, meta.json}.

Doing this at build time means the runtime never embeds the corpus - it only
loads the matrix and embeds the single query per request - which keeps the pod's
memory flat and startup instant. No network is needed beyond the one-time model
download (Akamai's WAF blocks crawling page bodies anyway; those are fetched live
per query at runtime).

    python scripts/build_docs_index.py
"""

from __future__ import annotations

import json
import os
import re
import sys

import numpy as np
from fastembed import TextEmbedding

MODEL = "BAAI/bge-small-en-v1.5"
CACHE = os.environ.get("FASTEMBED_CACHE", "/app/data/fastembed")
LLMS_PATH = os.environ.get("DOCS_INDEX_PATH", "data/llms.txt")
INDEX_DIR = os.environ.get("DOCS_INDEX_DIR", "data/docs_index")

_ALLOWED = ("https://techdocs.akamai.com/cloud-computing/", "https://techdocs.akamai.com/linode-api/")
_ENTRY = re.compile(r"^- \[(.*?)\]\((https?://[^)]+\.md)\)(?::\s*(.*))?$", re.M)
_BOILERPLATE = re.compile(r"\b(cloud computing|docs|reference|linode api|api)\b")


def _humanize(url: str) -> str:
    path = url.split("techdocs.akamai.com/", 1)[-1].rsplit(".md", 1)[0]
    return _BOILERPLATE.sub(" ", re.sub(r"[/\-_]", " ", path)).strip()


def main() -> None:
    text = open(LLMS_PATH, encoding="utf-8").read()
    seen: set[str] = set()
    entries: list[dict] = []
    for m in _ENTRY.finditer(text):
        title, url, desc = m.group(1), m.group(2), (m.group(3) or "")
        if url.startswith(_ALLOWED) and url not in seen:
            seen.add(url)
            entries.append({"title": title, "url": url, "desc": desc})
    print(f"[index] {len(entries)} pages from {LLMS_PATH}", flush=True)
    if len(entries) < 50:
        print("[index] ERROR: too few entries, aborting", file=sys.stderr)
        sys.exit(1)

    docs = [f"{e['title']}. {_humanize(e['url'])}." + (f" {e['desc']}" if e["desc"] else "") for e in entries]
    embedder = TextEmbedding(model_name=MODEL, cache_dir=CACHE)
    # Embed in small in-process slices (no worker subprocesses; flat memory).
    rows: list = []
    for start in range(0, len(docs), 64):
        rows.extend(embedder.embed(docs[start:start + 64], parallel=None))
    vecs = np.array(rows, dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9

    os.makedirs(INDEX_DIR, exist_ok=True)
    np.save(os.path.join(INDEX_DIR, "embeddings.npy"), vecs.astype(np.float16))
    with open(os.path.join(INDEX_DIR, "entries.jsonl"), "w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    json.dump(
        {"model": MODEL, "dim": int(vecs.shape[1]), "count": len(entries)},
        open(os.path.join(INDEX_DIR, "meta.json"), "w"),
    )
    print(f"[index] wrote {INDEX_DIR}/ (embeddings.npy {vecs.shape}, entries.jsonl, meta.json)", flush=True)


if __name__ == "__main__":
    main()
