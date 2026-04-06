"""
Harvest completed Firecrawl jobs from v4b run.
Checks status of every submitted job ID, pulls completed data,
converts to training records, merges into master corpus.
"""

import os, json, time, requests, hashlib
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
FC_HEADERS = {
    "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
    "Content-Type": "application/json",
}

RAW_DIR = Path("./corpus/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

write_lock = Lock()

PM_KEYWORDS = [
    "project", "plan", "schedule", "milestone", "stakeholder", "risk",
    "budget", "scope", "agile", "sprint", "waterfall", "deliverable",
    "gantt", "critical path", "resource", "renovation", "capex", "hotel",
    "construction", "timeline", "deadline", "phase", "charter", "wbs",
    "work breakdown", "dependency", "constraint", "governance", "pmo",
    "earned value", "change management", "lessons learned", "kickoff",
    "raci", "roi", "kpi", "portfolio", "investment", "capital",
    "hospitality", "reit", "asset", "program", "objective", "outcome",
    "task", "owner", "status", "priority", "effort", "cost", "duration",
    "procurement", "contract", "vendor", "quality", "launch",
]

# All jobs submitted in the v4b run — label → (crawl_id, question)
JOBS = {
    "adb_admin_manuals":      ("019d523b-a9d4-76", "What are the project administration requirements, procurement rules, and implementation arrangements?"),
    "worldbank_projects":     ("019d523b-a9ca-75", "What are the project objectives, budget, timeline, and risk factors for this World Bank project?"),
    "adb_datasets":           ("019d523b-aa05-72", "What structured project data and metrics are available in this ADB dataset?"),
    "adb_projects":           ("019d523b-aa3a-73", "What are the project scope, budget, timeline, risks and implementation status for this ADB project?"),
    "worldbank_risk_docs":    ("019d523b-a9d1-72", "What risk management frameworks and mitigation strategies are described in this project document?"),
    "worldbank_detail":       ("019d523b-aa29-75", "Describe the project scope, implementation plan, and risk management approach."),
    "doe_evm":                ("019d523b-aa4b-76", "How does the Department of Energy implement earned value management on capital projects?"),
    "nasa_pm_requirements":   ("019d523b-a9e2-73", "What are the NASA project management requirements, processes, and documentation standards?"),
    "doe_pm":                 ("019d523b-aa77-72", "What project management policies, requirements, and best practices does the DOE use for major projects?"),
    "worldbank_docs":         ("019d523b-aa64-75", "What are the key project management components documented in this World Bank report?"),
    "gsa_design":             ("019d523b-aa2c-74", "What design and construction project excellence standards does the GSA require?"),
    "un_pm":                  ("019d523b-aa48-77", "What project management frameworks does the UN use for large-scale programs?"),
    "gsa_construction":       ("019d523b-a99d-76", "What are the federal construction project management requirements, specifications, and standards?"),
    "nasa_program_mgmt":      ("019d523b-aa85-74", "What are NASA's program and project management policy requirements?"),
    "nasa_reports":           ("019d523b-aa1d-71", "What project management methodologies, plans, and lessons learned are documented in this NASA technical report?"),
    "undp_projects":          ("019d523b-a9cc-76", "What are the UNDP project objectives, budget, timeline, and implementation approach?"),
    "iadb_projects":          ("019d523b-a9f8-70", "What are the project objectives, budget, schedule, and risk factors for this IDB project?"),
    "cordis_projects":        ("019d523b-a9ba-75", "What are the project objectives, work packages, deliverables, and budget for this EU Horizon project?"),
    "cordis_project_detail":  ("019d523b-aa7b-75", "Describe the project work breakdown structure, milestones, and expected outcomes."),
    "nasa_risk_reports":      ("019d523b-aa95-77", "What risk management approaches and risk registers are documented in this NASA report?"),
    "hotel_tech_deep":        ("019d523b-b53e-74", "What technology implementations, project rollouts, and digital transformation initiatives are hotels undertaking?"),
    "wrike_templates":        ("019d523b-b56a-70", "What project phases, task hierarchies, and dependencies does this Wrike template structure?"),
    "it_dashboard":           ("019d523b-b565-77", "What IT project management data, costs, and performance metrics are reported on the Federal IT Dashboard?"),
    "notion_templates":       ("019d523b-b596-77", "What project structure, databases, and workflow definitions does this Notion template contain?"),
    "ms_adoption":            ("019d523b-b533-76", "What project implementation and change management guidance does Microsoft provide?"),
    "hospitalitynet_deep":    ("019d523b-b5a6-72", "What are the key trends, strategies, and management insights in the hotel and hospitality industry?"),
    "cms_pm":                 ("019d523b-b5b1-77", "What technology lifecycle and project management standards does CMS use?"),
    "trello_templates":       ("019d523b-b553-74", "What board structure, lists, labels, and card formats does this Trello project template use?"),
    "teamgantt_templates":    ("019d523b-b5c8-70", "What Gantt chart structure, task dependencies, and timeline data does this project template include?"),
    "smartsheet_templates":   ("019d523b-b5ee-73", "What structured rows, columns, formulas, and project data does this Smartsheet template provide?"),
    "dau_aaf":                ("019d523b-b59d-76", "What are the DoD's adaptive acquisition framework program management requirements?"),
    "monday_templates":       ("019d523b-b5a6-74", "What columns, statuses, automations, and project structures does this PM board template include?"),
    "airtable_pm_templates":  ("019d523b-b558-77", "What database structure, fields, views, and project tracking does this Airtable template provide?"),
    "asana_templates":        ("019d523b-b620-74", "What project structure, task types, dependencies, and workflows does this project management template define?"),
    "skift_deep":             ("019d523b-b602-70", "What strategic trends are shaping travel, hospitality, and hotel investment decisions?"),
    "ms_project_learn":       ("019d523b-b619-74", "What project management concepts, schedules, resources, and tracking does Microsoft Project support?"),
    "miro_pm_templates":      ("019d523b-b5f0-73", "What project planning frameworks, retrospective formats, and visual PM structures does this template use?"),
    "clickup_templates":      ("019d523b-b613-75", "What task structures, custom fields, and project workflows does this ClickUp template define?"),
    "hvs_publications":       ("019d523c-30be-73", "What hotel development, valuation, and capex research does HVS publish?"),
    "costar_hospitality_deep":("019d523c-30e2-71", "What hotel market analytics, transaction data, and investment trends does CoStar report?"),
    "hotels_investor_deep":   ("019d523c-312c-74", "What hotel investment strategies, acquisition plans, and capex priorities are hotel investors pursuing?"),
    "hvs_deep":               ("019d523c-3136-75", "What hotel development costs, investment returns, and renovation project data does HVS report?"),
    "scrum_org_deep":         ("019d523c-315a-72", "What Scrum framework guidance, practices, and resources does Scrum.org provide?"),
    "jll_hospitality_deep":   ("019d523c-3138-70", "What hotel market data, investment trends, and project management insights does JLL provide?"),
    "prince2_deep":           ("019d523c-30bd-74", "What are the PRINCE2 methodology principles, themes, processes, and management products?"),
    "str_deep":               ("019d523c-315a-73", "What hotel performance benchmarks, market data, and investment metrics does STR report?"),
    "apm_deep":               ("019d523c-3127-75", "What project management knowledge, tools, and best practices does the APM Body of Knowledge cover?"),
    "cbre_reports_deep":      ("019d523c-3171-72", "What hotel investment, capex, and real estate project insights does CBRE report?"),
}

# Jobs that were still running when script exited — poll these longer
STILL_RUNNING = {
    "hospitalitynet_deep", "cordis_project_detail", "hotel_tech_deep",
    "prince2_deep", "str_deep", "apm_deep", "asana_templates",
    "hvs_deep", "notion_templates", "clickup_templates", "monday_templates",
}


def fetch_job(label: str, crawl_id: str, question: str) -> tuple[str, list]:
    """Fetch completed crawl data. Waits up to 30min for still-running jobs."""
    max_wait = 1800 if label in STILL_RUNNING else 60
    start = time.time()

    while True:
        elapsed = time.time() - start
        if elapsed > max_wait:
            print(f"  [{label}] gave up after {int(elapsed)}s")
            return label, []
        try:
            r = requests.get(
                f"https://api.firecrawl.dev/v1/crawl/{crawl_id}",
                headers=FC_HEADERS, timeout=30
            )
            if r.status_code == 404:
                print(f"  [{label}] job expired/not found")
                return label, []
            if r.status_code != 200:
                time.sleep(10)
                continue

            s = r.json()
            status    = s.get("status", "")
            completed = s.get("completed", 0)

            if status == "completed":
                pages = s.get("data", [])
                print(f"  [{label}] DONE: {len(pages)} pages")
                return label, pages
            elif status in ["failed", "cancelled"]:
                print(f"  [{label}] {status}")
                return label, []
            else:
                print(f"  [{label}] {status}: {completed} pages ({int(elapsed)}s) — waiting...")
                time.sleep(20 if label in STILL_RUNNING else 5)

        except Exception as e:
            print(f"  [{label}] error: {e}")
            time.sleep(10)


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

        paragraphs = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 60]
        chunk = ""
        for para in paragraphs:
            if len(chunk) + len(para) > 1400 and chunk:
                records.append({
                    "source": f"fc_{label}",
                    "input":  question,
                    "output": chunk.strip(),
                    "url":    url,
                    "title":  title,
                    "format": "article",
                })
                chunk = para
            else:
                chunk = (chunk + "\n\n" + para).strip()
        if chunk and len(chunk) > 100:
            records.append({
                "source": f"fc_{label}",
                "input":  question,
                "output": chunk.strip(),
                "url":    url,
                "title":  title,
                "format": "article",
            })
    return records


def run():
    if not FIRECRAWL_API_KEY:
        print("ERROR: FIRECRAWL_API_KEY not set.")
        return

    print(f"Harvesting {len(JOBS)} Firecrawl jobs from v4b run...")
    print(f"Still-running jobs (up to 30min wait): {len(STILL_RUNNING)}")
    print("=" * 60)

    out_path = RAW_DIR / "v4b_harvest_corpus.jsonl"
    all_records = []
    total_pages = 0

    with open(out_path, "w") as out_f:
        with ThreadPoolExecutor(max_workers=20) as ex:
            futures = {
                ex.submit(fetch_job, label, crawl_id, question): label
                for label, (crawl_id, question) in JOBS.items()
            }
            for future in as_completed(futures):
                label, pages = future.result()
                question = JOBS[label][1]
                records = pages_to_records(pages, label, question)
                total_pages += len(pages)

                with write_lock:
                    all_records.extend(records)
                    for r in records:
                        out_f.write(json.dumps(r) + "\n")
                    out_f.flush()

                if records:
                    print(f"  [{label}] {len(pages)} pages → {len(records)} chunks | total: {len(all_records):,}")

    print(f"\n{'='*60}")
    print(f"Harvest complete: {len(all_records):,} chunks from {total_pages:,} pages")
    print(f"Saved: {out_path}")

    # Merge into master
    print("\n[Merging into master corpus...]")
    master_path = Path("./corpus/master_corpus.jsonl")

    existing = []
    for fname in [
        "corpus/combined_final.jsonl",
        "corpus/raw/deloitte_premium_corpus.jsonl",
        "corpus/raw/retry_corpus.jsonl",
        "corpus/raw/v4_burn_corpus.jsonl",
        "corpus/raw/v4b_burn_corpus.jsonl",
    ]:
        p = Path(fname)
        if p.exists():
            with open(p) as f:
                batch = [json.loads(l) for l in f if l.strip()]
            print(f"  {fname}: {len(batch):,}")
            existing.extend(batch)

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
    print(f"MASTER CORPUS: {len(merged):,} unique examples | {size_mb:.1f} MB")

    sources = Counter(r["source"].split("_")[0] for r in merged)
    for src, count in sources.most_common():
        print(f"  {src:35s}: {count:,}")


if __name__ == "__main__":
    run()
