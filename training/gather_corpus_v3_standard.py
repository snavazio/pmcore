"""
PMCore Corpus Gatherer v3 — Standard Plan Full Send
=====================================================
100,000 Firecrawl credits. No more holding back.

New targets at full depth:
  - PM methodology sites (PMI, PRINCE2, APM, Agile Alliance, Scrum.org)
  - Project management blogs (deep crawls, 200-500 pages each)
  - Hospitality publications (deep crawls)
  - Consulting firm research (McKinsey, BCG, Bain, Oliver Wyman)
  - Academic / PMBOK-aligned content
  - Hotel industry trade press (full archives)
  - Real estate / REIT research
  - Construction management sites
  - Technology PM (Atlassian, GitHub Blog, Linear, Notion)
  - Risk management deep content

Target: 50,000+ additional training chunks
"""

import os, json, time, requests, hashlib
from pathlib import Path
from collections import Counter

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
    "raci", "wbs", "roi", "kpi", "program management", "portfolio",
    "investment", "capital", "hospitality", "reit", "asset management",
]

def log(msg): print(f"  {msg}", flush=True)


def crawl_site(url: str, limit: int, label: str, extra_exclude: list = None) -> list:
    exclude = ["/login","/subscribe","/cart","/register","/search","/tag/",
               "/author/","/signup","/checkout","/account"]
    if extra_exclude:
        exclude.extend(extra_exclude)
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
        if r.status_code != 200:
            log(f"    Start failed {r.status_code}")
            return []

        crawl_id = r.json().get("id","")
        log(f"    Crawl {crawl_id[:16]}...")
        for attempt in range(120):
            time.sleep(6)
            sr = requests.get(f"https://api.firecrawl.dev/v1/crawl/{crawl_id}", headers=headers, timeout=20)
            if sr.status_code != 200: break
            s = sr.json()
            if attempt % 8 == 0:
                log(f"    {s.get('status','?')}: {s.get('completed',0)}/{limit}")
            if s.get("status") == "completed":
                return s.get("data", [])
            if s.get("status") in ["failed","cancelled"]:
                log(f"    Crawl ended: {s.get('status')}")
                break
    except Exception as e:
        log(f"    Exception: {e}")
    return []


def pages_to_records(pages: list, source_label: str, default_question: str) -> list[dict]:
    records = []
    for page in pages:
        content = page.get("markdown","") or ""
        title   = (page.get("metadata") or {}).get("title","") or ""
        url     = page.get("url","")

        if len(content) < 200:
            continue
        kw_hits = sum(1 for kw in PM_KEYWORDS if kw in content.lower())
        if kw_hits < 2:
            continue

        paragraphs = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 80]
        chunk = ""
        for para in paragraphs:
            if len(chunk) + len(para) > 1400 and chunk:
                records.append({
                    "source": f"fc_{source_label}",
                    "input": default_question,
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
                "source": f"fc_{source_label}",
                "input": default_question,
                "output": chunk.strip(),
                "url": url,
                "title": title,
                "format": "article",
            })
    return records


# ── CRAWL TARGETS ─────────────────────────────────────────────────────────────
# Format: (url, limit, label, question, extra_excludes)

TARGETS = [

    # ── PM METHODOLOGY (deep crawls) ──────────────────────────────────────────
    ("https://www.pmi.org/learning/library",
     500, "pmi_library",
     "What are PMI's best practices and methodologies for project management?",
     ["/membership","/certification","/events","/store"]),

    ("https://www.agilealliance.org/agile101",
     200, "agile_alliance",
     "What are the core principles and practices of agile project management?",
     None),

    ("https://www.scrum.org/resources",
     200, "scrum_org",
     "How does Scrum framework work and what are its best practices?",
     None),

    ("https://www.scrumalliance.org/learn-about-scrum",
     150, "scrum_alliance",
     "What are the Scrum Alliance's guidelines for agile project delivery?",
     None),

    ("https://www.prince2.com/eur",
     300, "prince2",
     "What are the PRINCE2 methodology principles, themes and processes?",
     ["/shop","/training","/certification"]),

    ("https://www.apm.org.uk/resources",
     300, "apm_org",
     "What does the Association for Project Management say about best practices?",
     ["/membership","/events","/qualifications"]),

    ("https://www.pmi.org/pmbok-guide-standards",
     100, "pmbok",
     "What are the PMBOK Guide standards and knowledge areas for project management?",
     None),

    # ── PM BLOGS & GUIDES (deep crawls) ───────────────────────────────────────
    ("https://www.projectmanagement.com/articles",
     400, "pm_com",
     "What are expert project management articles and insights?",
     None),

    ("https://www.smartsheet.com/content-center/project-management",
     300, "smartsheet_pm",
     "What are the best practices and guides for project management?",
     ["/pricing","/features","/integrations"]),

    ("https://www.wrike.com/project-management-guide",
     200, "wrike_guide",
     "What is the complete guide to project management methodologies and tools?",
     None),

    ("https://asana.com/resources/project-management",
     300, "asana_pm",
     "What are best practices for managing projects and teams effectively?",
     ["/pricing","/product","/integrations"]),

    ("https://monday.com/blog/project-management",
     300, "monday_pm",
     "What are effective project management strategies and techniques?",
     None),

    ("https://www.atlassian.com/blog/project-management",
     300, "atlassian_pm",
     "What are Atlassian's insights on agile and project management?",
     ["/software","/pricing","/teams"]),

    ("https://www.teamgantt.com/blog",
     200, "teamgantt",
     "What are practical tips for project planning, scheduling and Gantt charts?",
     None),

    ("https://www.projectsmart.co.uk",
     200, "projectsmart",
     "What are the key principles and tools for successful project management?",
     None),

    ("https://www.mpug.com",
     200, "mpug",
     "What are Microsoft Project best practices and project management techniques?",
     None),

    ("https://www.girlsguidetopm.com",
     200, "girlsguidepm",
     "What are practical project management tips and career insights?",
     None),

    ("https://www.thebalancemoney.com/project-management-4161739",
     100, "balance_pm",
     "What are the fundamentals of project management for business leaders?",
     None),

    ("https://www.workfront.com/project-management",
     150, "workfront",
     "What are best practices for enterprise project and work management?",
     None),

    ("https://www.clarizen.com/project-management-blog",
     100, "clarizen",
     "What are enterprise project management strategies and insights?",
     None),

    # ── RISK MANAGEMENT ───────────────────────────────────────────────────────
    ("https://www.pmi.org/learning/library/risk-management",
     150, "pmi_risk",
     "What are best practices for project risk management and mitigation?",
     None),

    ("https://www.riskmgmt.com",
     100, "risk_mgmt",
     "What are the frameworks and strategies for effective risk management?",
     None),

    ("https://continuitycentral.com",
     100, "continuity_central",
     "What are best practices for business continuity and risk management?",
     None),

    # ── HOSPITALITY INDUSTRY ──────────────────────────────────────────────────
    ("https://www.hospitalitynet.org",
     500, "hospitalitynet_full",
     "What are the latest trends, insights and analysis in the hotel industry?",
     ["/advertise","/subscribe","/login"]),

    ("https://hoteltechnologynews.com",
     300, "hotel_tech_news",
     "What are the latest technology innovations and implementations in hotels?",
     None),

    ("https://www.hotels-magazine.com",
     200, "hotels_magazine",
     "What are the key trends in hotel development, investment and operations?",
     None),

    ("https://www.hoteliermiddleeast.com",
     200, "hotelier_me",
     "What are hotel industry insights and management strategies?",
     None),

    ("https://www.4hoteliers.com",
     200, "4hoteliers",
     "What are hotel management best practices and industry news?",
     None),

    ("https://www.hotelmanagement.net",
     300, "hotel_management_net",
     "What are the latest hotel management strategies and industry trends?",
     None),

    ("https://www.lodgingmagazine.com",
     150, "lodging_magazine",
     "What are the key developments in lodging industry investment and operations?",
     None),

    ("https://skift.com/topic/hotels",
     300, "skift_hotels",
     "What are the strategic trends shaping the hotel industry?",
     ["/pro","/subscribe","/login"]),

    ("https://www.phocuswire.com/Hotels",
     200, "phocuswire_hotels",
     "What are the technology and business trends in the hotel industry?",
     None),

    # ── REAL ESTATE / REIT / INVESTMENT ───────────────────────────────────────
    ("https://www.reit.com/news/articles",
     300, "nareit",
     "What are the latest REIT industry insights, trends and investment strategies?",
     None),

    ("https://www.globest.com/hotels",
     300, "globest_hotels",
     "What are the commercial real estate and hotel investment trends?",
     None),

    ("https://www.bisnow.com/national/news/hotel",
     200, "bisnow_hotel",
     "What are the key developments in hotel real estate and investment?",
     None),

    ("https://www.costar.com/article/hospitality",
     150, "costar_hospitality",
     "What are the hotel market analytics and investment trends?",
     ["/subscribe","/login"]),

    # ── CONSULTING FIRMS ──────────────────────────────────────────────────────
    ("https://www.mckinsey.com/industries/travel-logistics-and-infrastructure/our-insights",
     200, "mckinsey_travel",
     "What are McKinsey's strategic insights for the travel and hospitality industry?",
     ["/careers","/about"]),

    ("https://www.bcg.com/industries/travel-tourism/insights",
     150, "bcg_travel",
     "What are BCG's strategic insights for travel, tourism and hospitality?",
     ["/careers","/about","/contact"]),

    ("https://www.oliverwyman.com/our-expertise/industries/transport-travel-leisure.html",
     100, "oliver_wyman_travel",
     "What are Oliver Wyman's insights on travel and hospitality strategy?",
     None),

    ("https://kpmg.com/us/en/industries/consumer-retail/travel-leisure-hospitality.html",
     100, "kpmg_hospitality",
     "What are KPMG's insights on hospitality industry trends and strategy?",
     None),

    ("https://www.ey.com/en_us/insights/hospitality",
     100, "ey_hospitality",
     "What are EY's insights on hospitality industry challenges and opportunities?",
     None),

    # ── CONSTRUCTION & CAPEX ──────────────────────────────────────────────────
    ("https://www.constructiondive.com",
     200, "construction_dive",
     "What are the latest construction industry trends, costs and project management practices?",
     ["/subscribe","/login"]),

    ("https://www.enr.com/topics/1430-project-management",
     150, "enr_pm",
     "What are engineering and construction project management best practices?",
     ["/subscribe","/login"]),

    ("https://www.bdcnetwork.com/building-types/hotel",
     100, "bdc_hotel",
     "What are best practices for hotel building design and construction management?",
     None),

    # ── TECHNOLOGY PM ─────────────────────────────────────────────────────────
    ("https://linear.app/docs",
     100, "linear_docs",
     "How do modern engineering teams manage projects, sprints and roadmaps?",
     None),

    ("https://www.notion.so/blog/topic/project-management",
     100, "notion_pm",
     "What are effective strategies for project and knowledge management?",
     None),

    ("https://basecamp.com/guides",
     80, "basecamp",
     "What are practical principles for managing remote teams and projects?",
     None),

    # ── ACADEMIC / STANDARDS ──────────────────────────────────────────────────
    ("https://www.sei.cmu.edu/our-work/project-management",
     80, "sei_cmu",
     "What are Carnegie Mellon SEI's frameworks for software project management?",
     None),

    ("https://www.mitre.org/our-impact/publications?topic=systems-engineering-guide",
     80, "mitre",
     "What are MITRE's systems engineering and project management guidelines?",
     None),
]


def run_all():
    if not FIRECRAWL_API_KEY:
        print("ERROR: FIRECRAWL_API_KEY not set")
        return

    print("PMCore Corpus v3 — Standard Plan Full Send")
    print(f"Targets: {len(TARGETS)} sites")
    print("=" * 60)

    all_records = []
    total_pages = 0
    PAGE_BUDGET = 90000  # Keep 10k buffer

    out_path = RAW_DIR / "v3_standard_corpus.jsonl"

    # Stream results to disk as we go
    with open(out_path, "w") as out_f:

        for i, target in enumerate(TARGETS):
            if total_pages >= PAGE_BUDGET:
                log(f"Page budget reached ({PAGE_BUDGET:,}). Done.")
                break

            url, limit, label, question, extra_exclude = target
            pages_this = min(limit, PAGE_BUDGET - total_pages)

            print(f"\n[{i+1}/{len(TARGETS)}] {label} (up to {pages_this} pages)")
            print(f"  URL: {url}")

            pages = crawl_site(url, pages_this, label, extra_exclude)
            records = pages_to_records(pages, label, question)

            log(f"  {len(pages)} pages → {len(records)} training chunks")
            total_pages += len(pages)
            all_records.extend(records)

            # Write batch to disk
            for r in records:
                out_f.write(json.dumps(r) + "\n")
            out_f.flush()

            log(f"  Running total: {total_pages:,} pages | {len(all_records):,} chunks")

    print(f"\n{'='*60}")
    print(f"v3 complete: {len(all_records):,} chunks from {total_pages:,} pages")
    print(f"Saved to: {out_path}")

    # Merge everything
    combined_path = Path("./corpus/combined_v3.jsonl")
    print(f"\nMerging all corpora into {combined_path}...")

    existing = []
    for fname in ["combined_v2.jsonl"]:
        p = Path("./corpus") / fname
        if p.exists():
            with open(p) as f:
                batch = [json.loads(l) for l in f if l.strip()]
            print(f"  Loaded {fname}: {len(batch):,}")
            existing.extend(batch)

    # Also load the Deloitte premium corpus if it exists
    deloitte_path = RAW_DIR / "deloitte_premium_corpus.jsonl"
    if deloitte_path.exists():
        with open(deloitte_path) as f:
            batch = [json.loads(l) for l in f if l.strip()]
        print(f"  Loaded deloitte_premium: {len(batch):,}")
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

    print(f"\nFINAL CORPUS: {len(merged):,} unique examples")
    print(f"Saved to: {combined_path}")
    print()
    sources = Counter(r["source"].split("_")[0] for r in merged)
    for src, count in sources.most_common():
        print(f"  {src:30s}: {count:,}")


if __name__ == "__main__":
    run_all()
