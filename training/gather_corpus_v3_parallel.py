"""
PMCore Corpus Gatherer v3 — Standard Plan, Full Parallel
=========================================================
100,000 credits. 100 concurrent requests.
Fires ALL crawl jobs simultaneously, then harvests results.

Strategy:
  1. Submit all crawl jobs at once (takes ~30 seconds)
  2. Poll all jobs in parallel until all complete
  3. Process results and write corpus

Expected runtime: ~30-45 minutes instead of 8+ hours sequential.
Expected output: 50,000-100,000 training chunks.
"""

import os, json, time, requests, hashlib
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
RAW_DIR = Path("./corpus/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

headers = {
    "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
    "Content-Type": "application/json",
}

PM_KEYWORDS = [
    "project", "plan", "schedule", "milestone", "stakeholder", "risk",
    "budget", "scope", "agile", "sprint", "waterfall", "deliverable",
    "gantt", "critical path", "resource", "renovation", "capex", "hotel",
    "construction", "timeline", "deadline", "phase", "charter",
    "work breakdown", "dependency", "constraint", "governance", "pmo",
    "earned value", "change management", "lessons learned", "kickoff",
    "raci", "wbs", "roi", "kpi", "portfolio", "investment", "capital",
    "hospitality", "reit", "asset management", "program management",
]

write_lock = Lock()

def log(msg): print(f"  {msg}", flush=True)


# ── TARGETS ───────────────────────────────────────────────────────────────────
# (url, limit, label, question)

TARGETS = [
    # PM Methodology
    ("https://www.pmi.org/learning/library",                    500, "pmi_library",         "What are PMI's best practices and methodologies for project management?"),
    ("https://www.agilealliance.org/agile101",                  200, "agile_alliance",       "What are the core principles and practices of agile project management?"),
    ("https://www.scrum.org/resources",                         200, "scrum_org",            "How does Scrum framework work and what are its best practices?"),
    ("https://www.scrumalliance.org/learn-about-scrum",         150, "scrum_alliance",       "What are Scrum Alliance guidelines for agile project delivery?"),
    ("https://www.prince2.com/eur",                             300, "prince2",              "What are the PRINCE2 methodology principles, themes and processes?"),
    ("https://www.apm.org.uk/resources",                        300, "apm_org",              "What does the APM say about project management best practices?"),
    ("https://www.pmi.org/pmbok-guide-standards",               100, "pmbok",                "What are the PMBOK Guide standards and knowledge areas?"),
    # PM Blogs
    ("https://www.projectmanagement.com/articles",              400, "pm_com",               "What are expert project management articles and insights?"),
    ("https://www.smartsheet.com/content-center/project-management", 300, "smartsheet_pm",   "What are best practices and guides for project management?"),
    ("https://www.wrike.com/project-management-guide",          200, "wrike_guide",          "What is the complete guide to project management methodologies?"),
    ("https://asana.com/resources/project-management",          300, "asana_pm",             "What are best practices for managing projects and teams?"),
    ("https://monday.com/blog/project-management",              300, "monday_pm",            "What are effective project management strategies?"),
    ("https://www.atlassian.com/blog/project-management",       300, "atlassian_pm",         "What are Atlassian's insights on agile and project management?"),
    ("https://www.teamgantt.com/blog",                          200, "teamgantt",            "What are practical tips for project planning and scheduling?"),
    ("https://www.projectsmart.co.uk",                          200, "projectsmart",         "What are key principles and tools for project management?"),
    ("https://www.mpug.com",                                    200, "mpug",                 "What are Microsoft Project best practices?"),
    ("https://www.girlsguidetopm.com",                          200, "girlsguidepm",         "What are practical project management tips and career insights?"),
    ("https://www.workfront.com/project-management",            150, "workfront",            "What are best practices for enterprise project management?"),
    # Risk Management
    ("https://www.pmi.org/learning/library/risk-management",    150, "pmi_risk",             "What are best practices for project risk management?"),
    ("https://continuitycentral.com",                           100, "continuity_central",   "What are best practices for business continuity and risk management?"),
    # Hospitality
    ("https://www.hospitalitynet.org",                          500, "hospitalitynet_full",  "What are the latest trends and insights in the hotel industry?"),
    ("https://hoteltechnologynews.com",                         300, "hotel_tech_news",      "What are the latest technology innovations in hotels?"),
    ("https://www.hotelmanagement.net",                         300, "hotel_management_net", "What are the latest hotel management strategies?"),
    ("https://www.lodgingmagazine.com",                         150, "lodging_magazine",     "What are key developments in lodging industry investment?"),
    ("https://skift.com/topic/hotels",                          300, "skift_hotels",         "What are the strategic trends shaping the hotel industry?"),
    ("https://www.phocuswire.com/Hotels",                       200, "phocuswire_hotels",    "What are technology and business trends in the hotel industry?"),
    ("https://www.4hoteliers.com",                              200, "4hoteliers",           "What are hotel management best practices and industry news?"),
    ("https://www.hoteliermiddleeast.com",                      200, "hotelier_me",          "What are hotel industry insights and management strategies?"),
    # Real Estate / REIT
    ("https://www.reit.com/news/articles",                      300, "nareit",               "What are the latest REIT industry insights and investment strategies?"),
    ("https://www.globest.com/hotels",                          300, "globest_hotels",       "What are commercial real estate and hotel investment trends?"),
    ("https://www.bisnow.com/national/news/hotel",              200, "bisnow_hotel",         "What are key developments in hotel real estate?"),
    # Consulting
    ("https://www.mckinsey.com/industries/travel-logistics-and-infrastructure/our-insights", 200, "mckinsey_travel", "What are McKinsey's strategic insights for hospitality?"),
    ("https://www.bcg.com/industries/travel-tourism/insights",  150, "bcg_travel",           "What are BCG's strategic insights for travel and hospitality?"),
    ("https://kpmg.com/us/en/industries/consumer-retail/travel-leisure-hospitality.html", 100, "kpmg_hospitality", "What are KPMG's insights on hospitality industry trends?"),
    ("https://www.ey.com/en_us/insights/hospitality",           100, "ey_hospitality",       "What are EY's insights on hospitality challenges?"),
    # Construction / CapEx
    ("https://www.constructiondive.com",                        200, "construction_dive",    "What are construction industry trends and project management practices?"),
    ("https://www.enr.com/topics/1430-project-management",      150, "enr_pm",               "What are engineering and construction project management practices?"),
    # Tech PM
    ("https://linear.app/docs",                                 100, "linear_docs",          "How do modern engineering teams manage projects and sprints?"),
    ("https://www.notion.so/blog/topic/project-management",     100, "notion_pm",            "What are effective strategies for project and knowledge management?"),
    ("https://basecamp.com/guides",                              80, "basecamp",             "What are practical principles for managing remote teams?"),
    # Lodging econometrics + HVS (already have some, get more)
    ("https://lodgingeconometrics.com",                         100, "lodging_econ",         "What is the hotel development pipeline and construction outlook?"),
    ("https://www.hvs.com/article",                              80, "hvs",                  "What are HVS insights on hotel development costs and investment?"),
    # Bonus hospitality research
    ("https://str.com/data-insights-hub",                        80, "str_insights",         "What are STR's hotel performance data insights and market analysis?"),
    ("https://www.hospitalityinvestor.com",                     150, "hospitality_investor", "What do hotel investors think about capex, renovation and returns?"),
    ("https://www.hotels-magazine.com",                         200, "hotels_magazine",      "What are key trends in hotel development and operations?"),
]


def submit_crawl(url: str, limit: int, label: str) -> dict | None:
    """Submit a crawl job and return job info immediately (non-blocking)."""
    exclude = ["/login","/subscribe","/cart","/register","/search","/tag/",
               "/author/","/signup","/checkout","/account","/pricing","/careers"]
    try:
        r = requests.post(
            "https://api.firecrawl.dev/v1/crawl",
            headers=headers,
            json={
                "url": url,
                "limit": limit,
                "scrapeOptions": {
                    "formats": ["markdown"],
                    "onlyMainContent": True,
                    "waitFor": 2000,
                    "excludeTags": ["nav","footer","header","aside","script","style","form","iframe"],
                },
                "excludePaths": exclude,
            },
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            crawl_id = data.get("id","")
            if crawl_id:
                return {"id": crawl_id, "url": url, "limit": limit, "label": label}
        log(f"    Submit failed {url}: HTTP {r.status_code}")
    except Exception as e:
        log(f"    Submit exception {url}: {e}")
    return None


def poll_crawl(job: dict, max_wait_seconds: int = 600) -> list:
    """Poll a crawl job until complete. Returns list of pages."""
    crawl_id = job["id"]
    label    = job["label"]
    start    = time.time()

    for attempt in range(max_wait_seconds // 6):
        time.sleep(6)
        try:
            sr = requests.get(
                f"https://api.firecrawl.dev/v1/crawl/{crawl_id}",
                headers=headers, timeout=20
            )
            if sr.status_code != 200:
                continue
            s = sr.json()
            status    = s.get("status","")
            completed = s.get("completed", 0)

            if attempt % 10 == 0:
                elapsed = int(time.time() - start)
                log(f"  [{label}] {status}: {completed} pages ({elapsed}s)")

            if status == "completed":
                pages = s.get("data", [])
                log(f"  [{label}] DONE: {len(pages)} pages")
                return pages
            if status in ["failed","cancelled"]:
                log(f"  [{label}] ended: {status}")
                return []
        except Exception as e:
            log(f"  [{label}] poll error: {e}")

    log(f"  [{label}] timed out after {max_wait_seconds}s")
    return []


def pages_to_records(pages: list, label: str, question: str) -> list[dict]:
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
    return records


def run_parallel():
    if not FIRECRAWL_API_KEY:
        print("ERROR: FIRECRAWL_API_KEY not set")
        return

    print("PMCore Corpus v3 — 100 Concurrent Requests, Full Send")
    print(f"Submitting {len(TARGETS)} crawl jobs simultaneously...")
    print("=" * 60)

    # ── Phase 1: Submit ALL jobs at once ──────────────────────────
    jobs = []
    print("\n[Phase 1: Submitting all crawl jobs]")
    # Submit in small batches of 20 to avoid rate limit on submission itself
    SUBMIT_BATCH = 20
    for i in range(0, len(TARGETS), SUBMIT_BATCH):
        batch = TARGETS[i:i+SUBMIT_BATCH]
        with ThreadPoolExecutor(max_workers=20) as ex:
            futures = {ex.submit(submit_crawl, url, limit, label): (url, label)
                      for url, limit, label, _ in batch}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    jobs.append(result)
                    log(f"  Submitted: {result['label']} (ID: {result['id'][:16]})")
        time.sleep(2)  # Brief pause between submission batches

    print(f"\n{len(jobs)}/{len(TARGETS)} jobs submitted successfully")

    # Build label→question map for later
    label_to_question = {label: question for _, _, label, question in TARGETS}

    # ── Phase 2: Poll all jobs in parallel ────────────────────────
    print("\n[Phase 2: Polling all jobs in parallel]")
    out_path = RAW_DIR / "v3_parallel_corpus.jsonl"
    all_records = []
    total_pages = 0

    with open(out_path, "w") as out_f:
        with ThreadPoolExecutor(max_workers=50) as ex:
            future_to_job = {ex.submit(poll_crawl, job): job for job in jobs}
            for future in as_completed(future_to_job):
                job   = future_to_job[future]
                label = job["label"]
                question = label_to_question.get(label, "What are the key project management insights?")

                try:
                    pages = future.result()
                    records = pages_to_records(pages, label, question)
                    total_pages += len(pages)

                    with write_lock:
                        all_records.extend(records)
                        for r in records:
                            out_f.write(json.dumps(r) + "\n")
                        out_f.flush()
                        log(f"  [{label}] → {len(records)} chunks | Total: {len(all_records):,} chunks / {total_pages:,} pages")

                except Exception as e:
                    log(f"  [{label}] result error: {e}")

    # ── Phase 3: Merge everything ─────────────────────────────────
    print(f"\n{'='*60}")
    print(f"v3 complete: {len(all_records):,} chunks from {total_pages:,} pages")

    print("\n[Phase 3: Merging all corpora]")
    combined_path = Path("./corpus/combined_v3.jsonl")
    existing = []

    for fname in ["combined_v2.jsonl"]:
        p = Path("./corpus") / fname
        if p.exists():
            with open(p) as f:
                batch = [json.loads(l) for l in f if l.strip()]
            print(f"  {fname}: {len(batch):,}")
            existing.extend(batch)

    for fname in ["deloitte_premium_corpus.jsonl", "retry_corpus.jsonl"]:
        p = RAW_DIR / fname
        if p.exists():
            with open(p) as f:
                batch = [json.loads(l) for l in f if l.strip()]
            print(f"  {fname}: {len(batch):,}")
            existing.extend(batch)

    seen, merged = set(), []
    for r in existing + all_records:
        key = hashlib.md5(r.get("input","")[:200].lower().encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            merged.append(r)

    with open(combined_path, "w") as f:
        for r in merged:
            f.write(json.dumps(r) + "\n")

    print(f"\n{'='*60}")
    print(f"FINAL CORPUS: {len(merged):,} unique examples")
    print(f"Saved: {combined_path}")
    print()
    sources = Counter(r["source"].split("_")[0] for r in merged)
    for src, count in sources.most_common():
        print(f"  {src:30s}: {count:,}")


if __name__ == "__main__":
    run_parallel()
