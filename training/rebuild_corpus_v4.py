"""
PMCore Corpus v4 Builder
========================
Merges clean prose + synthetic structured data into the final
training corpus for PMCore v3.

Sources (in priority order):
  1. corpus/raw/synthetic_structured.jsonl  — structured JSON (highest weight)
  2. corpus/clean_corpus.jsonl              — cleaned prose
"""

import json
import hashlib
from pathlib import Path
from collections import Counter

OUT_PATH = Path("corpus/master_corpus_v4.jsonl")

SOURCES = [
    ("corpus/raw/synthetic_structured.jsonl", 3),  # weight 3x — oversample structured
    ("corpus/clean_corpus.jsonl",             1),  # weight 1x — prose
]


def run():
    print("PMCore Corpus v4 Builder")
    print("=" * 60)

    all_records = []
    seen = set()

    for fname, weight in SOURCES:
        p = Path(fname)
        if not p.exists():
            print(f"  MISSING: {fname}")
            continue

        batch = [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()]
        print(f"  {fname}: {len(batch):,} records (weight {weight}x)")

        for r in batch:
            key = hashlib.md5(r.get("output", "")[:300].lower().encode()).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            # Apply weight by repeating structured records
            for _ in range(weight):
                all_records.append(r)

    # Shuffle so structured examples are distributed throughout
    import random
    random.seed(42)
    random.shuffle(all_records)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r) + "\n")

    size_mb = OUT_PATH.stat().st_size / 1e6
    print(f"\nTotal records: {len(all_records):,}")
    print(f"Unique outputs: {len(seen):,}")
    print(f"Size: {size_mb:.1f} MB")
    print(f"Saved: {OUT_PATH}")

    sources = Counter(r.get("source", "unknown").split("_")[0] for r in all_records)
    print(f"\nSource breakdown:")
    for src, count in sources.most_common():
        pct = 100 * count / len(all_records)
        print(f"  {src:35s}: {count:,} ({pct:.1f}%)")


if __name__ == "__main__":
    run()
