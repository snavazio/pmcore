"""
Fix deduplication and properly merge all corpus files.

Problem: Previous dedup used input[:200] as key.
For Firecrawl articles, all chunks from the same site share
the same input question — only 1 survived per site.

Fix: Use output[:300] as the dedup key instead.
Each chunk has unique output content even if same input question.

Also: Harvest any completed big crawl jobs that timed out during polling.
"""

import os, json, hashlib, requests, time
from pathlib import Path
from collections import Counter

FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
RAW_DIR = Path("./corpus/raw")
COMBINED = Path("./corpus/combined_final.jsonl")

headers = {
    "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
    "Content-Type": "application/json",
}

def log(msg): print(f"  {msg}", flush=True)


def dedup_by_output(records: list) -> list:
    """Deduplicate on output content — keeps all unique article chunks."""
    seen, unique = set(), []
    for r in records:
        # Use output content as the key (first 300 chars)
        key = hashlib.md5(r.get("output","")[:300].lower().encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def harvest_timed_out_jobs():
    """
    Check if any big crawl jobs from v3 are still completed on Firecrawl servers.
    Jobs stay available for 24 hours after completion.
    Parse the v3 log to find submitted job IDs.
    """
    if not FIRECRAWL_API_KEY:
        return []

    log("Checking for completed jobs from v3 run...")

    # Read job IDs from v3 log
    log_path = Path("./corpus_gather_v3.log")
    if not log_path.exists():
        log("v3 log not found")
        return []

    import re
    job_ids = {}
    with open(log_path, "rb") as f:
        content = f.read().decode("utf-8", errors="ignore")

    # Parse "Submitted: label (ID: xxx)" lines
    for match in re.finditer(r"Submitted: (\w+) \(ID: ([0-9a-f-]+)\)", content):
        label, job_id = match.group(1), match.group(2)
        job_ids[label] = job_id

    log(f"Found {len(job_ids)} job IDs from v3 log")

    # Find which ones timed out (returned 0 pages in v3)
    timed_out_labels = set()
    for match in re.finditer(r"\[(\w+)\] timed out", content):
        timed_out_labels.add(match.group(1))

    # Also find ones that returned 0 pages
    zero_page_labels = set()
    for match in re.finditer(r"\[(\w+)\] DONE: 0 pages", content):
        zero_page_labels.add(match.group(1))

    # Big sites we care about that may have finished
    priority_labels = {
        "pmi_library", "hospitalitynet_full", "teamgantt", "monday_pm",
        "atlassian_pm", "pm_com", "hotel_tech_news", "hotel_management_net",
        "smartsheet_pm", "apm_org", "girlsguidepm", "projectsmart",
        "phocuswire_hotels", "hotelier_me", "4hoteliers", "lodging_magazine",
        "hotels_magazine", "hospitality_investor", "hvs", "str_insights",
        "lodging_econ", "nareit",
    }

    # Label to question map (from v3 targets)
    label_questions = {
        "pmi_library":        "What are PMI's best practices and methodologies for project management?",
        "hospitalitynet_full":"What are the latest trends and insights in the hotel industry?",
        "teamgantt":          "What are practical tips for project planning and scheduling?",
        "monday_pm":          "What are effective project management strategies?",
        "atlassian_pm":       "What are Atlassian's insights on agile and project management?",
        "pm_com":             "What are expert project management articles and insights?",
        "hotel_tech_news":    "What are the latest technology innovations in hotels?",
        "hotel_management_net":"What are the latest hotel management strategies?",
        "smartsheet_pm":      "What are best practices and guides for project management?",
        "apm_org":            "What does the APM say about project management best practices?",
        "girlsguidepm":       "What are practical project management tips and career insights?",
        "projectsmart":       "What are key principles and tools for project management?",
        "phocuswire_hotels":  "What are technology and business trends in the hotel industry?",
        "hotelier_me":        "What are hotel industry insights and management strategies?",
        "4hoteliers":         "What are hotel management best practices and industry news?",
        "lodging_magazine":   "What are key developments in lodging industry investment?",
        "hotels_magazine":    "What are key trends in hotel development and operations?",
        "hospitality_investor":"What do hotel investors think about capex, renovation and returns?",
        "hvs":                "What are HVS insights on hotel development costs and investment?",
        "str_insights":       "What are STR's hotel performance data insights?",
        "lodging_econ":       "What is the hotel development pipeline and construction outlook?",
        "nareit":             "What are the latest REIT industry insights and investment strategies?",
    }

    PM_KEYWORDS = [
        "project", "plan", "schedule", "milestone", "stakeholder", "risk",
        "budget", "scope", "agile", "hotel", "renovation", "capex",
        "construction", "management", "investment", "capital", "hospitality",
    ]

    all_new = []

    for label, job_id in job_ids.items():
        if label not in priority_labels:
            continue

        try:
            r = requests.get(
                f"https://api.firecrawl.dev/v1/crawl/{job_id}",
                headers=headers, timeout=20
            )
            if r.status_code != 200:
                continue

            status_data = r.json()
            status    = status_data.get("status","")
            completed = status_data.get("completed", 0)

            if status == "completed" and completed > 0:
                pages = status_data.get("data", [])
                question = label_questions.get(label, "What are key project management insights?")

                records = []
                for page in pages:
                    content = page.get("markdown","") or ""
                    title   = (page.get("metadata") or {}).get("title","") or ""
                    url     = page.get("url","")

                    if len(content) < 200: continue
                    kw_hits = sum(1 for kw in PM_KEYWORDS if kw in content.lower())
                    if kw_hits < 2: continue

                    paragraphs = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 80]
                    chunk = ""
                    for para in paragraphs:
                        if len(chunk) + len(para) > 1400 and chunk:
                            records.append({
                                "source": f"fc_{label}",
                                "input": question,
                                "output": chunk.strip(),
                                "url": url,
                                "title": title,
                                "format": "article",
                            })
                            chunk = para
                        else:
                            chunk = (chunk + "\n\n" + para).strip()
                    if chunk and len(chunk) > 100:
                        records.append({
                            "source": f"fc_{label}",
                            "input": question,
                            "output": chunk.strip(),
                            "url": url,
                            "title": title,
                            "format": "article",
                        })

                log(f"  [{label}] Harvested {completed} pages → {len(records)} chunks")
                all_new.extend(records)
            else:
                log(f"  [{label}] Status: {status}, pages: {completed} — skipping")

            time.sleep(0.3)

        except Exception as e:
            log(f"  [{label}] error: {e}")

    log(f"Harvest total: {len(all_new)} new chunks")
    return all_new


if __name__ == "__main__":
    print("PMCore Corpus — Fix Dedup + Final Merge")
    print("=" * 60)

    # Load ALL corpus files
    print("\n[Loading all corpus files]")
    all_records = []

    corpus_files = [
        ("corpus/raw/se_corpus.jsonl",              "Stack Exchange"),
        ("corpus/raw/hf_v2_corpus.jsonl",           "HuggingFace v2"),
        ("corpus/raw/gh_corpus.jsonl",              "GitHub"),
        ("corpus/raw/edgar_v2_corpus.jsonl",        "SEC EDGAR v2"),
        ("corpus/raw/gov_corpus.jsonl",             "Government/World Bank"),
        ("corpus/raw/fc_v2_corpus.jsonl",           "Firecrawl v2"),
        ("corpus/raw/retry_corpus.jsonl",           "Retry sites"),
        ("corpus/raw/deloitte_premium_corpus.jsonl","Deloitte premium"),
        ("corpus/raw/v3_parallel_corpus.jsonl",     "v3 parallel"),
        ("corpus/raw/kaggle_corpus.jsonl",          "Kaggle"),
    ]

    for fpath, label in corpus_files:
        p = Path(fpath)
        if p.exists():
            with open(p) as f:
                batch = [json.loads(l) for l in f if l.strip()]
            log(f"{label}: {len(batch):,}")
            all_records.extend(batch)
        else:
            log(f"{label}: not found ({fpath})")

    print(f"\nTotal before dedup: {len(all_records):,}")

    # Harvest any timed-out big jobs
    print("\n[Harvesting timed-out crawl jobs]")
    harvested = harvest_timed_out_jobs()
    if harvested:
        # Save harvested records
        harvest_path = RAW_DIR / "harvested_corpus.jsonl"
        with open(harvest_path, "w") as f:
            for r in harvested:
                f.write(json.dumps(r) + "\n")
        log(f"Saved {len(harvested):,} harvested records")
        all_records.extend(harvested)

    # Fix deduplication — use OUTPUT content as key
    print(f"\n[Deduplicating on output content]")
    unique = dedup_by_output(all_records)
    print(f"After dedup: {len(unique):,} unique examples (was {len(all_records):,})")

    # Sort by output length — longer = richer
    unique.sort(key=lambda r: len(r.get("output","")), reverse=True)

    # Save final corpus
    with open(COMBINED, "w") as f:
        for r in unique:
            f.write(json.dumps(r) + "\n")

    print(f"\n{'='*60}")
    print(f"FINAL CORPUS: {len(unique):,} unique examples")
    print(f"Saved: {COMBINED}")
    print()

    sources = Counter(r["source"].split("_")[0] for r in unique)
    for src, count in sources.most_common():
        print(f"  {src:30s}: {count:,}")

    # Size on disk
    size_mb = COMBINED.stat().st_size / 1e6
    print(f"\nCorpus size: {size_mb:.1f} MB")
