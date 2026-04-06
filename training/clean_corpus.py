"""
PMCore Corpus Cleaner
=====================
1. Removes junk records (URL dumps, nav menus, sitemaps, pagination)
2. Filters short/low-quality outputs
3. Deduplicates on output content
4. Reports quality breakdown
"""

import json
import hashlib
import re
from pathlib import Path
from collections import Counter

RAW_SOURCES = [
    "corpus/combined_final.jsonl",
    "corpus/raw/deloitte_premium_corpus.jsonl",
    "corpus/raw/retry_corpus.jsonl",
    "corpus/raw/v4_burn_corpus.jsonl",
    "corpus/raw/v4b_burn_corpus.jsonl",
]

OUT_PATH = Path("corpus/clean_corpus.jsonl")

# ── Junk detection ────────────────────────────────────────────────────────────

def is_junk(output: str) -> tuple[bool, str]:
    """Returns (is_junk, reason)."""

    # Too short
    if len(output) < 200:
        return True, "too_short"

    # URL density — more than 4 URLs = sitemap/nav dump
    url_count = len(re.findall(r'https?://', output))
    if url_count > 4:
        return True, "url_dump"

    # Starts with a URL
    if output.strip().startswith("http"):
        return True, "starts_with_url"

    # Mostly markdown links
    md_links = len(re.findall(r'\[.*?\]\(https?://.*?\)', output))
    words = len(output.split())
    if words > 0 and md_links / max(words, 1) > 0.15:
        return True, "mostly_links"

    # Pagination / nav patterns
    nav_patterns = [
        r'^\s*\|\s*\d+\s*\|',          # table of just numbers
        r'Page \d+ of \d+',
        r'Next Page|Previous Page',
        r'Cookie Policy|Privacy Policy|Terms of Service',
        r'©\s*\d{4}.*All rights reserved',
        r'Skip to main content',
        r'Subscribe to newsletter',
    ]
    for pat in nav_patterns:
        if re.search(pat, output, re.IGNORECASE | re.MULTILINE):
            return True, "nav_boilerplate"

    # Repetitive short lines (navigation menus)
    lines = [l.strip() for l in output.split('\n') if l.strip()]
    if len(lines) > 10:
        avg_len = sum(len(l) for l in lines) / len(lines)
        if avg_len < 25:
            return True, "short_line_menu"

    # Mostly escaped markdown artifacts
    backslash_density = output.count('\\_') + output.count('\\[') + output.count('\\]')
    if backslash_density > 20:
        return True, "escaped_markdown"

    return False, ""


PM_KEYWORDS = [
    "project", "plan", "schedule", "milestone", "stakeholder", "risk",
    "budget", "scope", "agile", "sprint", "waterfall", "deliverable",
    "gantt", "critical path", "resource", "renovation", "capex", "hotel",
    "construction", "timeline", "deadline", "phase", "charter", "wbs",
    "work breakdown", "dependency", "governance", "pmo", "earned value",
    "change management", "lessons learned", "raci", "roi", "kpi",
    "portfolio", "investment", "capital", "hospitality", "asset",
    "program", "objective", "outcome", "procurement", "contract",
    "vendor", "quality", "cost", "duration", "baseline", "variance",
]

def pm_relevance(text: str) -> int:
    lower = text.lower()
    return sum(1 for kw in PM_KEYWORDS if kw in lower)


def is_structured(output: str) -> bool:
    """True if output contains meaningful JSON structure."""
    if '{' not in output or '}' not in output:
        return False
    pm_keys = ['task', 'risk', 'budget', 'phase', 'milestone', 'deadline',
                'duration', 'dependency', 'methodology', 'schedule', 'owner']
    return any(k in output.lower() for k in pm_keys)


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print("PMCore Corpus Cleaner")
    print("=" * 60)

    # Load all sources
    all_records = []
    for fname in RAW_SOURCES:
        p = Path(fname)
        if p.exists():
            batch = [json.loads(l) for l in p.open(encoding='utf-8') if l.strip()]
            print(f"  {fname}: {len(batch):,}")
            all_records.extend(batch)

    print(f"\nTotal loaded: {len(all_records):,}")

    # Filter + classify
    reasons = Counter()
    kept = []
    seen = set()

    for r in all_records:
        output = r.get("output", "")
        inp    = r.get("input", "")

        # Dedup on output
        key = hashlib.md5(output[:300].lower().encode()).hexdigest()
        if key in seen:
            reasons["duplicate"] += 1
            continue
        seen.add(key)

        # Junk check
        junk, reason = is_junk(output)
        if junk:
            reasons[reason] += 1
            continue

        # PM relevance — need at least 3 keyword hits
        score = pm_relevance(output + " " + inp)
        if score < 3:
            reasons["low_relevance"] += 1
            continue

        # Tag structured records
        r["_structured"] = is_structured(output)
        r["_pm_score"]   = score
        kept.append(r)

    print(f"\nKept: {len(kept):,}")
    print(f"Removed: {len(all_records) - len(kept):,}")
    print(f"\nRemoval reasons:")
    for reason, count in reasons.most_common():
        print(f"  {reason:30s}: {count:,}")

    structured_count = sum(1 for r in kept if r.get("_structured"))
    print(f"\nStructured JSON records: {structured_count:,} ({100*structured_count/len(kept):.1f}%)")
    print(f"Prose records:           {len(kept)-structured_count:,} ({100*(len(kept)-structured_count)/len(kept):.1f}%)")

    # Sort: structured first, then by PM score descending
    kept.sort(key=lambda r: (-int(r.get("_structured", False)), -r.get("_pm_score", 0)))

    # Write clean corpus
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for r in kept:
            # Strip internal tags before saving
            r.pop("_structured", None)
            r.pop("_pm_score", None)
            f.write(json.dumps(r) + "\n")

    size_mb = OUT_PATH.stat().st_size / 1e6
    print(f"\nSaved: {OUT_PATH} ({size_mb:.1f} MB)")

    sources = Counter(r["source"].split("_")[0] for r in kept)
    print(f"\nSources:")
    for src, count in sources.most_common():
        print(f"  {src:35s}: {count:,}")


if __name__ == "__main__":
    run()
