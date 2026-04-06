"""
PMCore Corpus Gatherer v4 — USE 65K CREDITS (25k buffer reserved)
===================================================================
90,000 Firecrawl credits expire April 9, 2026.
Budget: 65,000 credits. Reserve: 25,000 for next week.

Strategy:
  - Tier 1: Structured project data (World Bank, CORDIS, NASA, ADB) — HIGHEST VALUE
  - Tier 2: Government project databases (GSA, UN, federal)
  - Tier 3: PM template galleries (Asana, Monday, Smartsheet, Notion)
  - Tier 4: Full deep crawls of all PM + hospitality sites at maximum depth
  - Tier 5: PM knowledge deep crawls

All jobs submitted in parallel using 100 concurrent requests.
Results streamed to disk as they arrive.
Estimated output: 200,000+ training chunks.
Target: ~64,000 pages (leaves ~26k credits in reserve)

Run: source ~/.pmcore_env && uv run python gather_corpus_v4_burn.py
"""

import os, json, time, requests, hashlib
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
RAW_DIR = Path("./corpus/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

FC_HEADERS = {
    "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
    "Content-Type": "application/json",
}

PM_KEYWORDS = [
    "project", "plan", "schedule", "milestone", "stakeholder", "risk",
    "budget", "scope", "agile", "sprint", "waterfall", "deliverable",
    "gantt", "critical path", "resource", "renovation", "capex", "hotel",
    "construction", "timeline", "deadline", "phase", "charter", "wbs",
    "work breakdown", "dependency", "constraint", "governance", "pmo",
    "earned value", "change management", "lessons learned", "kickoff",
    "raci", "roi", "kpi", "portfolio", "investment", "capital",
    "hospitality", "reit", "asset", "program", "objective", "outcome",
    "deliverable", "task", "owner", "status", "priority", "effort",
    "cost", "duration", "start", "finish", "baseline", "variance",
    "procurement", "contract", "vendor", "quality", "testing", "launch",
]

write_lock = Lock()
total_records = 0
total_pages   = 0

def log(msg): print(f"  {msg}", flush=True)


# ── TARGETS ───────────────────────────────────────────────────────────────────
# Format: (url, limit, label, question, priority)
# Priority 1 = most structured/valuable, 5 = filler

TARGETS = [

    # ════════════════════════════════════════════════
    # TIER 1: STRUCTURED PROJECT DATABASES (highest value)
    # ════════════════════════════════════════════════

    # World Bank — 10,000+ real projects with standardized risk/budget/timeline
    ("https://projects.worldbank.org/en/projects-operations/projects-home",
     650, "worldbank_projects",
     "What are the project objectives, budget, timeline, and risk factors for this World Bank project?", 1),

    ("https://projects.worldbank.org/en/projects-operations/project-detail",
     650, "worldbank_detail",
     "Describe the project scope, implementation plan, and risk management approach.", 1),

    ("https://documents.worldbank.org/en/publication/documents-reports?qterm=project+management+plan",
     400, "worldbank_docs",
     "What are the key project management components documented in this World Bank report?", 1),

    ("https://documents.worldbank.org/en/publication/documents-reports?qterm=risk+management+plan",
     400, "worldbank_risk_docs",
     "What risk management frameworks and mitigation strategies are described in this project document?", 1),

    # CORDIS — EU Horizon Research Projects (50,000+ projects)
    ("https://cordis.europa.eu/projects/en",
     2600, "cordis_projects",
     "What are the project objectives, work packages, deliverables, and budget for this EU Horizon project?", 1),

    ("https://cordis.europa.eu/project/id",
     1300, "cordis_project_detail",
     "Describe the project work breakdown structure, milestones, and expected outcomes.", 1),

    # NASA — Highest quality structured PM templates
    ("https://nodis3.gsfc.nasa.gov/displayDir.cfm?Internal_ID=N_PR_7120_005E_&page_name=Chapter3",
     50, "nasa_pm_requirements",
     "What are the NASA project management requirements, processes, and documentation standards?", 1),

    ("https://ntrs.nasa.gov/search?q=project+management+plan",
     100, "nasa_reports",
     "What project management methodologies, plans, and lessons learned are documented in this NASA technical report?", 1),

    ("https://ntrs.nasa.gov/search?q=risk+management",
     100, "nasa_risk_reports",
     "What risk management approaches and risk registers are documented in this NASA report?", 1),

    ("https://nodis3.gsfc.nasa.gov/displayDir.cfm?t=NPR&c=7120&s=5",
     100, "nasa_program_mgmt",
     "What are NASA's program and project management policy requirements?", 1),

    # Asian Development Bank — 6,000+ infrastructure project profiles
    ("https://www.adb.org/projects",
     650, "adb_projects",
     "What are the project scope, budget, timeline, risks and implementation status for this ADB project?", 1),

    ("https://www.adb.org/projects/documents/project-administration-manuals",
     300, "adb_admin_manuals",
     "What are the project administration requirements, procurement rules, and implementation arrangements?", 1),

    ("https://data.adb.org/dataset",
     100, "adb_datasets",
     "What structured project data and metrics are available in this ADB dataset?", 1),

    # UN Project Data
    ("https://undp.org/projects-programmes",
     400, "undp_projects",
     "What are the UNDP project objectives, budget, timeline, and implementation approach?", 1),

    ("https://www.un.org/en/academic-impact/pm-project-management",
     100, "un_pm",
     "What project management frameworks does the UN use for large-scale programs?", 1),

    # Inter-American Development Bank
    ("https://www.iadb.org/en/projects",
     400, "iadb_projects",
     "What are the project objectives, budget, schedule, and risk factors for this IDB project?", 1),

    # ════════════════════════════════════════════════
    # TIER 2: US GOVERNMENT STRUCTURED PROJECT DATA
    # ════════════════════════════════════════════════

    # GSA — Federal project specs and procurement
    ("https://www.gsa.gov/real-estate/design-construction/project-management",
     100, "gsa_construction",
     "What are the federal construction project management requirements, specifications, and standards?", 2),

    ("https://www.gsa.gov/real-estate/design-construction/design-excellence/design-excellence-program",
     100, "gsa_design",
     "What design and construction project excellence standards does the GSA require?", 2),

    # DOE — $30B+ active project portfolio
    ("https://www.energy.gov/management/project-management",
     100, "doe_pm",
     "What project management policies, requirements, and best practices does the DOE use for major projects?", 2),

    ("https://www.energy.gov/management/earned-value-management",
     100, "doe_evm",
     "How does the Department of Energy implement earned value management on capital projects?", 2),

    # DOD Acquisition — largest PM documentation library
    ("https://www.dau.edu/tools/t/program-management-tools",
     100, "dau_pm_tools",
     "What program management tools, templates, and frameworks does the Department of Defense use?", 2),

    ("https://aaf.dau.edu/aaf/program-management/",
     100, "dau_aaf",
     "What are the DoD's adaptive acquisition framework program management requirements?", 2),

    # Federal IT Dashboard — major IT projects
    ("https://itdashboard.gov/portfolio/detail/850",
     100, "it_dashboard",
     "What IT project management data, costs, and performance metrics are reported on the Federal IT Dashboard?", 2),

    # CMS (Centers for Medicare) — large IT project management
    ("https://www.cms.gov/research-statistics-data-and-systems/cms-information-technology/tlc",
     100, "cms_pm",
     "What technology lifecycle and project management standards does CMS use?", 2),

    # ════════════════════════════════════════════════
    # TIER 3: PM TEMPLATE GALLERIES (structured task data)
    # ════════════════════════════════════════════════

    ("https://asana.com/templates",
     300, "asana_templates",
     "What project structure, task types, dependencies, and workflows does this project management template define?", 3),

    ("https://monday.com/templates",
     300, "monday_templates",
     "What columns, statuses, automations, and project structures does this PM board template include?", 3),

    ("https://www.smartsheet.com/marketplace/templates",
     300, "smartsheet_templates",
     "What structured rows, columns, formulas, and project data does this Smartsheet template provide?", 3),

    ("https://www.notion.so/templates",
     200, "notion_templates",
     "What project structure, databases, and workflow definitions does this Notion template contain?", 3),

    ("https://clickup.com/templates",
     200, "clickup_templates",
     "What task structures, custom fields, and project workflows does this ClickUp template define?", 3),

    ("https://www.wrike.com/templates",
     100, "wrike_templates",
     "What project phases, task hierarchies, and dependencies does this Wrike template structure?", 3),

    ("https://www.teamgantt.com/free-project-management-templates",
     100, "teamgantt_templates",
     "What Gantt chart structure, task dependencies, and timeline data does this project template include?", 3),

    ("https://miro.com/templates/project-management",
     100, "miro_pm_templates",
     "What project planning frameworks, retrospective formats, and visual PM structures does this template use?", 3),

    ("https://www.airtable.com/templates/project-management",
     100, "airtable_pm_templates",
     "What database structure, fields, views, and project tracking does this Airtable template provide?", 3),

    ("https://trello.com/templates/project-management",
     100, "trello_templates",
     "What board structure, lists, labels, and card formats does this Trello project template use?", 3),

    # Microsoft official PM guidance
    ("https://learn.microsoft.com/en-us/project/project-online-get-started",
     100, "ms_project_learn",
     "What project management concepts, schedules, resources, and tracking does Microsoft Project support?", 3),

    ("https://adoption.microsoft.com/en-us/sample-solution-guide/",
     100, "ms_adoption",
     "What project implementation and change management guidance does Microsoft provide?", 3),

    # ════════════════════════════════════════════════
    # TIER 4: HOSPITALITY DEEP CRAWL (burn credits on best sites)
    # ════════════════════════════════════════════════

    ("https://www.hospitalitynet.org",
     2600, "hospitalitynet_deep",
     "What are the key trends, strategies, and management insights in the hotel and hospitality industry?", 4),

    ("https://hoteltechnologynews.com",
     950, "hotel_tech_deep",
     "What technology implementations, project rollouts, and digital transformation initiatives are hotels undertaking?", 4),

    ("https://www.hotelmanagement.net",
     950, "hotel_mgmt_deep",
     "What hotel management strategies, renovation projects, and operational improvements are being implemented?", 4),

    ("https://skift.com",
     950, "skift_deep",
     "What strategic trends are shaping travel, hospitality, and hotel investment decisions?", 4),

    ("https://www.hvs.com/article",
     500, "hvs_deep",
     "What hotel development costs, investment returns, and renovation project data does HVS report?", 4),

    ("https://lodgingeconometrics.com",
     500, "lodging_econ_deep",
     "What hotel development pipeline data, construction starts, and project completion trends does Lodging Econometrics track?", 4),

    ("https://str.com",
     300, "str_deep",
     "What hotel performance benchmarks, market data, and investment metrics does STR report?", 4),

    ("https://www.costar.com/article/hospitality",
     300, "costar_hospitality_deep",
     "What hotel market analytics, transaction data, and investment trends does CoStar report?", 4),

    ("https://www.hotelsinvestor.com",
     300, "hotels_investor_deep",
     "What hotel investment strategies, acquisition plans, and capex priorities are hotel investors pursuing?", 4),

    ("https://www.globest.com/hotels",
     300, "globest_deep",
     "What are the latest hotel real estate transactions, development projects, and market trends?", 4),

    ("https://www.bisnow.com/national/news/hotel",
     300, "bisnow_deep",
     "What hotel development, investment, and renovation projects are underway in major markets?", 4),

    ("https://www.reit.com",
     300, "nareit_deep",
     "What REIT industry strategies, capital allocation decisions, and project management approaches are being reported?", 4),

    # CBRE + JLL + Cushman full depth
    ("https://www.cbre.com/insights/reports",
     300, "cbre_reports_deep",
     "What hotel investment, capex, and real estate project insights does CBRE report?", 4),

    ("https://www.jll.com/en/industries/hotels-and-hospitality",
     200, "jll_hospitality_deep",
     "What hotel market data, investment trends, and project management insights does JLL provide?", 4),

    ("https://www.cushmanwakefield.com/en/insights",
     200, "cushman_insights",
     "What real estate and hospitality market trends does Cushman & Wakefield report?", 4),

    # HVS in-depth reports and studies
    ("https://www.hvs.com/Publications",
     200, "hvs_publications",
     "What hotel development, valuation, and capex research does HVS publish?", 4),

    # ════════════════════════════════════════════════
    # TIER 5: PM KNOWLEDGE DEEP CRAWLS (exhaust remaining credits)
    # ════════════════════════════════════════════════

    ("https://www.pmi.org/learning/library",
     2600, "pmi_full_deep",
     "What project management knowledge, methodologies, and best practices does PMI recommend?", 5),

    ("https://www.pmi.org/learning/library/articles",
     1300, "pmi_articles_deep",
     "What are the key project management insights and lessons from PMI's article library?", 5),

    ("https://www.pmi.org/learning/library/case-studies",
     500, "pmi_cases",
     "What real-world project management case studies, outcomes, and lessons learned does PMI document?", 5),

    ("https://www.prince2.com",
     950, "prince2_deep",
     "What are the PRINCE2 methodology principles, themes, processes, and management products?", 5),

    ("https://www.apm.org.uk/resources",
     950, "apm_deep",
     "What project management knowledge, tools, and best practices does the APM Body of Knowledge cover?", 5),

    ("https://www.agilealliance.org",
     300, "agile_alliance_deep",
     "What agile principles, practices, and frameworks does the Agile Alliance document?", 5),

    ("https://www.scrum.org",
     300, "scrum_org_deep",
     "What Scrum framework guidance, practices, and resources does Scrum.org provide?", 5),

    ("https://www.projectmanagement.com",
     650, "pm_com_deep",
     "What project management techniques, tools, and expert insights does ProjectManagement.com cover?", 5),

    ("https://www.smartsheet.com/content-center",
     950, "smartsheet_deep",
     "What project management guides, templates, and best practices does Smartsheet document?", 5),

    ("https://asana.com/resources",
     950, "asana_resources_deep",
     "What project management and team productivity resources does Asana provide?", 5),

    ("https://www.atlassian.com/blog",
     950, "atlassian_deep",
     "What agile, project management, and team collaboration insights does Atlassian share?", 5),

    ("https://monday.com/blog",
     650, "monday_blog_deep",
     "What project management strategies, productivity tips, and industry insights does Monday.com cover?", 5),

    ("https://www.wrike.com/blog",
     650, "wrike_blog_deep",
     "What project management methodologies, tools, and best practices does Wrike cover?", 5),

    ("https://www.teamgantt.com/blog",
     300, "teamgantt_deep",
     "What project scheduling, Gantt chart, and timeline management tips does TeamGantt provide?", 5),

    ("https://www.projectsmart.co.uk",
     300, "projectsmart_deep",
     "What project management tools, techniques, and resources does ProjectSmart document?", 5),

    ("https://www.mpug.com",
     300, "mpug_deep",
     "What Microsoft Project and enterprise project management guidance does MPUG provide?", 5),

    ("https://www.girlsguidetopm.com",
     300, "girlsguidepm_deep",
     "What practical project management tips, career insights, and PM techniques are covered?", 5),

    ("https://hbr.org/topic/subject/project-management",
     300, "hbr_pm_deep",
     "What project management insights and leadership lessons does Harvard Business Review publish?", 5),

    ("https://www.mckinsey.com/capabilities/operations/our-insights",
     300, "mckinsey_ops_deep",
     "What operational excellence and project management insights does McKinsey publish?", 5),

    ("https://www.bcg.com/capabilities/operations/insights",
     200, "bcg_ops_deep",
     "What project delivery and operations management insights does BCG publish?", 5),

    ("https://www.constructiondive.com",
     1300, "construction_dive_deep",
     "What construction project management trends, costs, and best practices are covered?", 5),

    ("https://www.enr.com/topics/1430-project-management",
     300, "enr_deep",
     "What engineering and construction project management practices does ENR document?", 5),

    # Risk management deep
    ("https://www.riskmgmt.com",
     300, "risk_mgmt_deep",
     "What risk management frameworks, tools, and best practices are documented?", 5),

    ("https://www.pmi.org/learning/library/risk-management",
     300, "pmi_risk_deep",
     "What PMI risk management practices, frameworks, and tools are recommended?", 5),

    # Consulting deep
    ("https://www.ey.com/en_us/insights/strategy",
     200, "ey_strategy",
     "What strategic transformation and project delivery insights does EY publish?", 5),

    ("https://kpmg.com/us/en/articles",
     200, "kpmg_articles",
     "What project management and business transformation insights does KPMG publish?", 5),

    ("https://www.pwc.com/gx/en/issues/transformation",
     200, "pwc_transformation",
     "What business transformation and project delivery insights does PwC publish?", 5),

    ("https://www.deloitte.com/us/en/insights",
     300, "deloitte_insights_deep",
     "What strategic business and industry transformation insights does Deloitte publish?", 5),

    # Agile / DevOps deep
    ("https://www.infoq.com/project-management",
     300, "infoq_pm",
     "What software project management, agile, and DevOps insights does InfoQ cover?", 5),

    ("https://www.mountaingoatsoftware.com/blog",
     200, "mountain_goat",
     "What agile and Scrum project management techniques does Mountain Goat Software cover?", 5),

    ("https://www.romanpichler.com/blog",
     100, "roman_pichler",
     "What agile product management and project leadership insights are covered?", 5),
]


# ── Crawl functions ───────────────────────────────────────────────────────────

def submit_crawl(url: str, limit: int, label: str) -> dict | None:
    exclude = [
        "/login", "/subscribe", "/cart", "/register", "/search", "/tag/",
        "/author/", "/signup", "/checkout", "/account", "/pricing", "/careers",
        "/download", "/pdf", "/sitemap",
    ]
    try:
        r = requests.post(
            "https://api.firecrawl.dev/v1/crawl",
            headers=FC_HEADERS,
            json={
                "url": url,
                "limit": limit,
                "scrapeOptions": {
                    "formats": ["markdown"],
                    "onlyMainContent": True,
                    "waitFor": 2000,
                    "excludeTags": ["nav","footer","header","aside","script","style","form","iframe","advertisement"],
                },
                "excludePaths": exclude,
            },
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("id"):
                return {"id": data["id"], "url": url, "limit": limit, "label": label}
        log(f"Submit failed {label}: HTTP {r.status_code} — {r.text[:100]}")
    except Exception as e:
        log(f"Submit error {label}: {e}")
    return None


def poll_crawl(job: dict, max_wait: int = 14400) -> list:
    """Poll until complete. Max 4 hours per job (large crawls need time)."""
    crawl_id = job["id"]
    label    = job["label"]
    start    = time.time()

    # Adaptive sleep: fast polling early, slower as time passes
    def sleep_interval(elapsed: float) -> float:
        if elapsed < 120:   return 6
        if elapsed < 600:   return 15
        if elapsed < 1800:  return 30
        return 60

    attempt = 0
    while True:
        elapsed = time.time() - start
        if elapsed >= max_wait:
            break
        time.sleep(sleep_interval(elapsed))
        attempt += 1
        try:
            sr = requests.get(
                f"https://api.firecrawl.dev/v1/crawl/{crawl_id}",
                headers=FC_HEADERS, timeout=20
            )
            if sr.status_code != 200:
                continue
            s = sr.json()
            status    = s.get("status", "")
            completed = s.get("completed", 0)

            if attempt % 10 == 0:
                log(f"  [{label}] {status}: {completed} pages ({int(elapsed)}s)")

            if status == "completed":
                return s.get("data", [])
            if status in ["failed", "cancelled"]:
                log(f"  [{label}] ended: {status}")
                return []
        except Exception as e:
            log(f"  [{label}] poll error: {e}")

    log(f"  [{label}] timed out after {max_wait}s")
    return []


def pages_to_records(pages: list, label: str, question: str) -> list[dict]:
    records = []
    for page in pages:
        content = page.get("markdown", "") or ""
        title   = (page.get("metadata") or {}).get("title", "") or ""
        url     = page.get("url", "")

        if len(content) < 150:
            continue

        kw_hits = sum(1 for kw in PM_KEYWORDS if kw in content.lower())
        if kw_hits < 2:
            continue

        # Chunk into ~1400 char pieces at paragraph breaks
        paragraphs = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 60]
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


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    if not FIRECRAWL_API_KEY:
        print("ERROR: FIRECRAWL_API_KEY not set. Run: source ~/.pmcore_env")
        return

    print("PMCore Corpus v4 — 65K CREDIT RUN (25k buffer reserved)")
    print(f"Targets: {len(TARGETS)} sites")
    print(f"Estimated pages: {sum(t[1] for t in TARGETS):,}")
    print("=" * 60)

    out_path = RAW_DIR / "v4b_burn_corpus.jsonl"
    label_to_q = {label: q for _, _, label, q, _ in TARGETS}

    # Sort by priority so Tier 1 jobs finish first
    targets_sorted = sorted(TARGETS, key=lambda t: t[4])

    # ── Phase 1: Submit all jobs in batches ───────────────────────
    print(f"\n[Phase 1] Submitting {len(targets_sorted)} crawl jobs...")
    all_jobs = []
    BATCH_SIZE = 20

    for i in range(0, len(targets_sorted), BATCH_SIZE):
        batch = targets_sorted[i:i+BATCH_SIZE]
        with ThreadPoolExecutor(max_workers=BATCH_SIZE) as ex:
            futures = {
                ex.submit(submit_crawl, url, limit, label): label
                for url, limit, label, _, _ in batch
            }
            for f in as_completed(futures):
                result = f.result()
                if result:
                    all_jobs.append(result)
                    log(f"Submitted [{result['label']}] (ID: {result['id'][:16]})")
        time.sleep(1)

    print(f"\n{len(all_jobs)}/{len(targets_sorted)} jobs submitted")

    # ── Phase 2: Poll all jobs in parallel ────────────────────────
    print(f"\n[Phase 2] Polling {len(all_jobs)} jobs in parallel...")
    all_records = []
    total_pages = 0

    with open(out_path, "w") as out_f:
        with ThreadPoolExecutor(max_workers=60) as ex:
            future_to_job = {ex.submit(poll_crawl, job): job for job in all_jobs}

            for future in as_completed(future_to_job):
                job   = future_to_job[future]
                label = job["label"]
                q     = label_to_q.get(label, "What are the key project management insights?")

                try:
                    pages   = future.result()
                    records = pages_to_records(pages, label, q)
                    total_pages += len(pages)

                    with write_lock:
                        all_records.extend(records)
                        for r in records:
                            out_f.write(json.dumps(r) + "\n")
                        out_f.flush()

                    log(f"[{label}] {len(pages)} pages → {len(records)} chunks | "
                        f"Running: {len(all_records):,} chunks / {total_pages:,} pages")

                except Exception as e:
                    log(f"[{label}] error: {e}")

    # ── Phase 3: Merge into master corpus ─────────────────────────
    print(f"\n{'='*60}")
    print(f"v4 complete: {len(all_records):,} new chunks from {total_pages:,} pages")
    print(f"Saved raw: {out_path}")

    print("\n[Phase 3] Building master corpus...")
    master_path = Path("./corpus/master_corpus.jsonl")

    existing = []
    for fname in [
        "corpus/combined_final.jsonl",
        "corpus/raw/deloitte_premium_corpus.jsonl",
        "corpus/raw/retry_corpus.jsonl",
        "corpus/raw/v4_burn_corpus.jsonl",
    ]:
        p = Path(fname)
        if p.exists():
            with open(p) as f:
                batch = [json.loads(l) for l in f if l.strip()]
            print(f"  Loaded {fname}: {len(batch):,}")
            existing.extend(batch)

    # Deduplicate on OUTPUT content (not input)
    seen, merged = set(), []
    for r in existing + all_records:
        key = hashlib.md5(r.get("output", "")[:300].lower().encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            merged.append(r)

    with open(master_path, "w") as f:
        for r in merged:
            f.write(json.dumps(r) + "\n")

    size_mb = master_path.stat().st_size / 1e6

    print(f"\n{'='*60}")
    print(f"MASTER CORPUS: {len(merged):,} unique examples")
    print(f"Size: {size_mb:.1f} MB")
    print(f"Saved: {master_path}")
    print()

    sources = Counter(r["source"].split("_")[0] for r in merged)
    for src, count in sources.most_common():
        print(f"  {src:35s}: {count:,}")


if __name__ == "__main__":
    run()
