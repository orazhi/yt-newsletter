"""Dedup, clustering, and the "diff since last night" memory.

This is what turns a pile of feed items into a *briefing*: it removes things you
already saw on previous nights (the diff), collapses the same story reported by
several sources into one clustered entry (read it once), and hands the model only
the genuinely-new material grouped by beat.

Everything here is pure/deterministic and unit-tested — no network, no model — so
the part you most need to trust (that you won't be re-served yesterday's news) is
verifiable in isolation.

Memory format (small JSON, persisted between runs via the workflow cache):
    { "seen": { "<canonical_key>": "<first_seen_iso>" } }
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


@dataclass
class Item:
    """One normalized thing pulled from a source (article, paper, post, video)."""

    beat: str
    source: str
    title: str
    url: str
    published_at: str = ""  # ISO-8601 when known
    summary: str = ""       # feed summary / abstract / description (untrusted text)
    kind: str = "rss"

    @property
    def key(self) -> str:
        return canonical_key(self.url, self.title)


# --- canonical keys: the same story must map to the same key -----------------

_TRACKING_PREFIXES = ("utm_", "ref", "ref_src", "fbclid", "gclid", "mc_cid", "mc_eid")


def canonical_key(url: str, title: str = "") -> str:
    """A stable dedup key: the cleaned URL, else a hash of the normalized title.

    Strips scheme, "www.", tracking query params, and trailing slashes so the
    same article shared with different decorations collapses to one key.
    """
    u = (url or "").strip()
    if u:
        try:
            parts = urlsplit(u if "://" in u else "https://" + u)
            host = parts.netloc.lower().removeprefix("www.")
            path = parts.path.rstrip("/")
            kept = [
                kv
                for kv in parts.query.split("&")
                if kv and not any(kv.lower().startswith(p) for p in _TRACKING_PREFIXES)
            ]
            query = "&".join(kept)
            cleaned = urlunsplit(("https", host, path, query, ""))
            if host and path:
                return cleaned
        except ValueError:
            pass
    norm = normalize_title(title)
    return "title:" + hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (title or "").lower()).strip()


_STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "is", "are", "by",
         "how", "why", "with", "your", "you", "new", "this", "that", "as", "at", "its"}


def _stem(w: str) -> str:
    """Crudely fold plural/verb endings so 'releases' and 'released' match."""
    if len(w) > 4:
        for suf in ("ing", "ed", "es", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                return w[: -len(suf)]
    return w


def _tokens(title: str) -> set[str]:
    # Drop common words + stem so "X announces Y" and "Y announced by X" still match.
    return {_stem(w) for w in normalize_title(title).split() if w and w not in _STOP}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# --- dedup + clustering ------------------------------------------------------

def dedup_within(items: list[Item]) -> list[Item]:
    """Drop exact-key duplicates within a single run, keeping the first seen."""
    seen: set[str] = set()
    out: list[Item] = []
    for it in items:
        k = it.key
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


@dataclass
class Cluster:
    """The same story from one or more sources, plus whether it's an update."""

    items: list[Item] = field(default_factory=list)
    is_update: bool = False  # True if part of this story was already briefed before

    @property
    def newest(self) -> Item:
        return max(self.items, key=lambda i: i.published_at or "")


def cluster_similar(items: list[Item], threshold: float = 0.6) -> list[Cluster]:
    """Greedily group items whose normalized titles overlap above `threshold`.

    Simple by design: O(n^2) over a night's items (tens, not thousands), no
    embeddings, no network — so it's cheap and the behavior is obvious/testable.
    """
    clusters: list[Cluster] = []
    token_cache: list[set[str]] = []
    for it in items:
        toks = _tokens(it.title)
        placed = False
        for ci, cl in enumerate(clusters):
            if _jaccard(toks, token_cache[ci]) >= threshold:
                cl.items.append(it)
                token_cache[ci] = token_cache[ci] | toks
                placed = True
                break
        if not placed:
            clusters.append(Cluster(items=[it]))
            token_cache.append(toks)
    return clusters


# --- memory: the cross-night diff --------------------------------------------

def load_memory(path: Path) -> dict:
    if not path.exists():
        return {"seen": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"seen": {}}
    if not isinstance(data, dict) or not isinstance(data.get("seen"), dict):
        return {"seen": {}}
    return data


def save_memory(path: Path, memory: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")


def prune_memory(memory: dict, keep_days: int = 45) -> dict:
    """Forget keys older than keep_days so the store stays small and bounded."""
    cutoff = datetime.now(timezone.utc).timestamp() - keep_days * 86400
    seen = memory.get("seen", {})
    kept = {}
    for k, iso in seen.items():
        try:
            ts = datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
        except (ValueError, AttributeError):
            ts = datetime.now(timezone.utc).timestamp()  # keep unparseable, just in case
        if ts >= cutoff:
            kept[k] = iso
    return {"seen": kept}


def select_new(items: list[Item], memory: dict) -> list[Item]:
    """Keep only items whose key has NOT been briefed on a previous night."""
    seen = memory.get("seen", {})
    return [it for it in items if it.key not in seen]


def commit_memory(items: list[Item], memory: dict) -> dict:
    """Mark every given item as seen (call this only after a successful send)."""
    now = datetime.now(timezone.utc).isoformat()
    seen = dict(memory.get("seen", {}))
    for it in items:
        seen.setdefault(it.key, now)
    return prune_memory({"seen": seen})


# --- assemble the model's input ----------------------------------------------

def build_input(items: list[Item], memory: dict) -> dict:
    """Group new+clustered items by beat into the JSON the synthesis stage reads.

    The 'watch' beat is passed through flat (pointers, never clustered/merged).
    """
    fresh = select_new(dedup_within(items), memory)

    by_beat: dict[str, list[Item]] = {}
    for it in fresh:
        by_beat.setdefault(it.beat, []).append(it)

    out: dict = {"beats": {}, "watch": []}
    seen_keys = memory.get("seen", {})
    for beat, beat_items in by_beat.items():
        if beat == "watch":
            out["watch"] = [
                {"channel": it.source, "title": it.title, "url": it.url, "note": it.summary}
                for it in beat_items
            ]
            continue
        clusters = cluster_similar(beat_items)
        rendered = []
        for cl in clusters:
            # is_update: any sibling story key already in long-term memory
            cl.is_update = any(i.key in seen_keys for i in cl.items)
            rendered.append(
                {
                    "is_update": cl.is_update,
                    "sources": [
                        {
                            "source": i.source,
                            "title": i.title,
                            "url": i.url,
                            "published_at": i.published_at,
                            "summary": i.summary,
                        }
                        for i in cl.items
                    ],
                }
            )
        out["beats"][beat] = rendered
    return out


def items_from_input(data: dict) -> list[Item]:
    """Reconstruct the flat Item list from a build_input() payload (for commit)."""
    items: list[Item] = []
    for beat, clusters in data.get("beats", {}).items():
        for cl in clusters:
            for s in cl.get("sources", []):
                items.append(
                    Item(
                        beat=beat,
                        source=s.get("source", ""),
                        title=s.get("title", ""),
                        url=s.get("url", ""),
                        published_at=s.get("published_at", ""),
                        summary=s.get("summary", ""),
                    )
                )
    for w in data.get("watch", []):
        items.append(Item(beat="watch", source=w.get("channel", ""),
                          title=w.get("title", ""), url=w.get("url", ""), kind="youtube"))
    return items


def item_to_dict(it: Item) -> dict:
    return asdict(it)


def main() -> None:
    """Fold the night's briefed items into long-term memory (run AFTER a send)."""
    import argparse

    parser = argparse.ArgumentParser(description="Commit briefed items into the cross-night memory.")
    parser.add_argument("--input", default="briefing/input.json", help="The build_input() payload.")
    parser.add_argument("--memory", default="state/memory.json", help="Memory store to update.")
    args = parser.parse_args()

    inp = Path(args.input)
    if not inp.exists():
        print(f"[memory] nothing to commit ({inp} missing)")
        return
    data = json.loads(inp.read_text(encoding="utf-8"))
    items = items_from_input(data)
    mem_path = Path(args.memory)
    updated = commit_memory(items, load_memory(mem_path))
    save_memory(mem_path, updated)
    print(f"[memory] committed {len(items)} item(s); {len(updated['seen'])} key(s) remembered")


if __name__ == "__main__":
    main()
