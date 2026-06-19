"""Documentation retrieval for the documentation specialist.

Akamai's WAF blocks bulk-crawling the docs, so we do NOT pre-fetch page bodies.
Instead:

  1. At startup, embed the page INDEX from llms.txt - each entry's title, the
     words in its URL path, and any description - with a small ONNX model
     (fastembed, no torch). Most cloud-computing entries have no description, so
     the old whole-word title scorer was nearly blind; embedding title+path
     matches a question by meaning.
  2. Per query, embed the question, cosine-rank the pages, and fetch just the top
     few live (low volume, which the WAF allows), returning the section that best
     matches the question with its source URL.

If the embedder can't load, fall back to the original lexical scan + live fetch,
so the agent always answers. ``docs_lookup`` keeps the same name and return shape
it had in the orchestrator, so the documentation_agent wiring is unchanged.
"""

from __future__ import annotations

import json  # noqa: F401 - reserved for future cached-index use
import logging
import os
import re
import threading

import httpx
from strands import tool

from config.settings import settings

log = logging.getLogger("akamai_sa.docs")

MODEL = "BAAI/bge-small-en-v1.5"
CACHE = os.environ.get("FASTEMBED_CACHE", "/app/data/fastembed")
INDEX_DIR = os.environ.get(
    "DOCS_INDEX_DIR", os.path.join(os.path.dirname(__file__), "..", "data", "docs_index")
)
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

TOP_PAGES = 4      # semantic candidates to consider
FETCH_PAGES = 3    # how many of those to fetch live
LEXICAL_BOOST = 0.02

_ALLOWED = ("https://techdocs.akamai.com/cloud-computing/", "https://techdocs.akamai.com/linode-api/")
_ENTRY = re.compile(r"^- \[(.*?)\]\((https?://[^)]+\.md)\)(?::\s*(.*))?$", re.M)
_STOP = {"how", "the", "do", "to", "my", "in", "on", "of", "and", "or", "for", "is", "are",
         "what", "with", "you", "your", "can", "does", "this", "that", "it", "be", "from",
         "use", "get", "set", "any", "all"}
_BOILERPLATE = re.compile(r"\b(cloud computing|docs|reference|linode api|api)\b")


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def _clean_page(markdown: str) -> str:
    i = markdown.find("\n# ")
    return (markdown[i + 1:] if i != -1 else markdown).strip()


def _humanize(url: str) -> str:
    """Turn a docs URL path into searchable words: .../manage-access.md -> 'manage access'."""
    path = url.split("techdocs.akamai.com/", 1)[-1].rsplit(".md", 1)[0]
    words = re.sub(r"[/\-_]", " ", path)
    return _BOILERPLATE.sub(" ", words).strip()


def _entries() -> list[tuple[str, str, str]]:
    if not settings.docs_index_path:
        return []
    try:
        text = open(settings.docs_index_path, encoding="utf-8").read()
    except OSError:
        return []
    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []
    for m in _ENTRY.finditer(text):
        title, url, desc = m.group(1), m.group(2), (m.group(3) or "")
        if url.startswith(_ALLOWED) and url not in seen:
            seen.add(url)
            out.append((title, url, desc))
    return out


# --------------------------------------------------------------- semantic index
_lock = threading.Lock()
_idx: dict = {"loaded": False, "embedder": None, "vecs": None, "entries": None}


def _load_index() -> None:
    """Load the baked matrix + entries once, lazily, plus the query embedder.

    The corpus matrix is embedded at build time (scripts/build_docs_index.py), so
    here we only mmap a ~1MB matrix and load the model for embedding the single
    query per request - no corpus embedding at runtime, so memory stays flat.
    """
    if _idx["loaded"]:
        return
    with _lock:
        if _idx["loaded"]:
            return
        try:
            import numpy as np

            vecs = np.load(os.path.join(INDEX_DIR, "embeddings.npy")).astype(np.float32)
            with open(os.path.join(INDEX_DIR, "entries.jsonl"), encoding="utf-8") as fh:
                entries = [json.loads(line) for line in fh]  # dicts: title, url, desc
            if vecs.shape[0] != len(entries):
                raise ValueError(f"matrix/entries mismatch: {vecs.shape[0]} vs {len(entries)}")

            from fastembed import TextEmbedding

            embedder = TextEmbedding(model_name=MODEL, cache_dir=CACHE)
            warm = next(iter(embedder.embed(["warmup"], parallel=None)))
            if len(warm) != vecs.shape[1]:
                raise ValueError(f"embedding dim mismatch: query {len(warm)} vs index {vecs.shape[1]}")

            _idx.update(embedder=embedder, vecs=vecs, entries=entries)
            log.info("docs semantic index loaded: %d pages (dim %d)", len(entries), vecs.shape[1])
        except Exception as exc:  # noqa: BLE001 - lexical fallback keeps the agent working
            log.warning("semantic docs index unavailable (%s); using lexical fallback", exc)
            _idx["embedder"] = None
        _idx["loaded"] = True


def _fetch_page(url: str) -> str | None:
    try:
        r = httpx.get(url, headers={"User-Agent": _UA}, timeout=20, follow_redirects=True)
        return _clean_page(r.text) if r.status_code == 200 else None
    except Exception:  # noqa: BLE001
        return None


def _best_section(md: str, qtok: set[str]) -> str:
    """Return the heading section with the most query-term overlap, else the page."""
    secs = re.split(r"(?m)^(?=#{1,3}\s)", md)
    if len(secs) <= 1:
        return md
    best = max(secs, key=lambda s: len(qtok & _tokens(s)))
    return best if (qtok & _tokens(best)) else md


def _semantic(question: str) -> str | None:
    if _idx["embedder"] is None:
        return None
    import numpy as np

    qv = np.array(next(iter(_idx["embedder"].embed([question], parallel=None))), dtype=np.float32)
    qv /= np.linalg.norm(qv) + 1e-9
    sims = _idx["vecs"] @ qv  # cosine (both normalized)

    qtok = {w for w in _tokens(question) if w not in _STOP and len(w) > 2}
    entries = _idx["entries"]
    boosts = np.array([LEXICAL_BOOST * len(qtok & _tokens(e["title"])) for e in entries], dtype=np.float32)
    order = np.argsort(sims + boosts)[::-1][:TOP_PAGES]

    parts: list[str] = []
    for i in order:
        if len(parts) >= FETCH_PAGES:
            break
        e = entries[int(i)]
        body = _fetch_page(e["url"])
        if body:
            parts.append(f"## {e['title']}\nSource: {e['url']}\n\n{_best_section(body, qtok)[:2200]}")
    if parts:
        return "\n\n---\n\n".join(parts)
    # Live fetch failed for every candidate: still cite the best-matched pages.
    cite = [f"## {entries[int(i)]['title']}\nSource: {entries[int(i)]['url']}" for i in order[:3]]
    return "\n\n---\n\n".join(cite) + "\n\n(Could not fetch the page bodies right now; the links above are the best matches.)"


# --------------------------------------------------------------- lexical fallback
def _lexical(question: str) -> str:
    entries = _entries()
    if not entries:
        return "No matching Akamai Cloud docs page was found (the docs index may be unset)."
    qwords = {w for w in _tokens(question) if w not in _STOP and len(w) > 2}
    scored = []
    for title, url, desc in entries:
        tw, ow = _tokens(title), _tokens(desc + " " + url)
        score = sum((3 if w in tw else 0) + (1 if w in ow else 0) for w in qwords)
        if score:
            scored.append((score, title, url))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return "No matching Akamai Cloud docs page was found."
    parts = []
    for _s, title, url in scored[:3]:
        body = _fetch_page(url)
        parts.append(f"## {title}\nSource: {url}\n\n{(body or '(could not fetch this page)')[:2000]}")
    return "\n\n---\n\n".join(parts)


def warm() -> None:
    """Pre-build the semantic index at startup so the first query isn't slow."""
    _load_index()


@tool
def docs_lookup(question: str) -> str:
    """Find and read the Akamai Cloud doc pages that answer a question.

    Ranks the official docs index semantically, then fetches the top matching
    pages live and returns the most relevant section of each with its source URL.

    Args:
        question: An Akamai Cloud product or best-practices question.
    Returns:
        The matching doc passages' text, each with its source URL.
    """
    _load_index()
    return _semantic(question) or _lexical(question)
