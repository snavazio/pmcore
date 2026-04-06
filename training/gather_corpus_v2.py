"""
PMCore Corpus Gatherer v2 — Wide Net Edition
=============================================
Expanded sources:
  1. Stack Exchange PM (already done - loads cache)
  2. HuggingFace — fixed smoltalk config + new datasets
  3. GitHub (already done - loads cache)
  4. SEC EDGAR — 15 hotel companies + REITs (expanded)
  5. Firecrawl — 20 PM/hospitality sites (expanded)
  6. Kaggle — construction + PM datasets via direct download
  7. Data.gov — DOE project management, federal construction data
  8. World Bank — open project data API
  9. PMI/PMBOK public content via Firecrawl
 10. Wikipedia PM articles via HuggingFace wikipedia dataset

Usage:
    source ~/.pmcore_env
    uv run python gather_corpus_v2.py

Output:
    ./corpus/raw/v2_*.jsonl      — new source files
    ./corpus/combined_v2.jsonl  — all sources merged
"""

import os, re, json, time, hashlib, argparse, requests
from pathlib import Path
from typing import Iterator
from xml.etree import ElementTree as ET

RAW_DIR = Path("./corpus/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)
COMBINED_V2 = Path("./corpus/combined_v2.jsonl")

FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
GITHUB_TOKEN      = os.environ.get("GITHUB_TOKEN", "")

def log(msg): print(f"  {msg}", flush=True)

def save_jsonl(path, records):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return len(records)

def clean_html(text):
    if not text: return ""
    text = re.sub(r"<code>.*?</code>", " [code] ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    for h, r in [("&lt;","<"),("&gt;",">"),("&amp;","&"),("&quot;",'"'),("&#39;","'")]:
        text = text.replace(h, r)
    return re.sub(r"\s+", " ", text).strip()


# ── Source: HuggingFace v2 (fixed + expanded) ─────────────────────────────────

def source_huggingface_v2() -> list[dict]:
    from datasets import load_dataset
    records = []

    sources = [
        # (id, config, split, in_field, out_field, max, filter_kw)
        ("HuggingFaceTB/smoltalk", "smol-magpie-ultra", "train", "messages", None, 3000,
         ["project", "manage", "plan", "schedule", "milestone", "stakeholder",
          "risk", "budget", "agile", "sprint", "waterfall", "deliverable",
          "critical path", "gantt", "resource allocation", "scope"]),

        ("HuggingFaceTB/smoltalk", "apigen-80k", "train", "messages", None, 1000,
         ["project management", "task", "milestone", "deliverable", "stakeholder"]),

        ("teknium/OpenHermes-2.5", None, "train", "conversations", None, 3000,
         ["project", "manage", "plan", "schedule", "milestone", "risk",
          "budget", "agile", "waterfall", "construction", "renovation"]),

        ("Open-Orca/OpenOrca", None, "train", "question", "response", 2000,
         ["project", "manage", "plan", "timeline", "milestone", "stakeholder",
          "risk", "agile", "scrum", "sprint", "budget", "scope", "deliverable"]),

        ("garage-bAInd/Open-Platypus", None, "train", "instruction", "output", 1000,
         ["project", "manage", "schedule", "plan", "milestone", "risk",
          "budget", "stakeholder", "team", "deliverable"]),

        ("camel-ai/ai_society", None, "train", "message_1", "message_2", 1000,
         ["project manager", "project management", "plan", "schedule",
          "milestone", "stakeholder", "risk", "budget"]),
    ]

    for entry in sources:
        dataset_id, config, split, in_field, out_field, max_ex, keywords = entry
        label = f"{dataset_id.split('/')[-1]}" + (f"_{config}" if config else "")
        try:
            log(f"Loading {label}...")
            kwargs = dict(split=split, streaming=True)
            if config:
                kwargs["name"] = config
            ds = load_dataset(dataset_id, **kwargs)

            count = 0
            for ex in ds:
                if count >= max_ex: break

                # Handle conversation formats
                if in_field == "messages" or in_field == "conversations":
                    msgs = ex.get(in_field, [])
                    if not msgs: continue
                    # Normalize role names
                    normalized = []
                    for m in msgs:
                        role    = m.get("role") or m.get("from") or ""
                        content = m.get("content") or m.get("value") or ""
                        if role in ("human", "user"):    normalized.append(("user", content))
                        elif role in ("gpt", "assistant"): normalized.append(("assistant", content))
                    if len(normalized) < 2: continue
                    inp = next((c for r,c in normalized if r == "user"), "")
                    out = next((c for r,c in normalized if r == "assistant"), "")
                else:
                    inp = str(ex.get(in_field, "") or "")
                    out = str(ex.get(out_field, "") or "")
                    ctx = ex.get("context") or ex.get("system_prompt") or ""
                    if ctx: inp = f"{inp}\n\nContext: {ctx}"

                combined = (inp + " " + out).lower()
                if not any(kw in combined for kw in keywords): continue
                if len(inp) < 20 or len(out) < 40: continue

                records.append({
                    "source": f"hf_{label}",
                    "input": inp.strip()[:2000],
                    "output": out.strip()[:2000],
                    "format": "qa",
                })
                count += 1

            log(f"  {label}: {count} examples")

        except Exception as e:
            log(f"  {label} failed: {e}")

    log(f"HuggingFace v2 total: {len(records)}")
    return records


# ── Source: SEC EDGAR v2 (expanded hotel universe) ────────────────────────────

EDGAR_COMPANIES_V2 = [
    # Hotel REITs
    ("Host Hotels & Resorts",      "0001070750"),
    ("Park Hotels & Resorts",      "0001617208"),
    ("Pebblebrook Hotel Trust",    "0001474098"),
    ("Ryman Hospitality Properties","0001014473"),
    ("Summit Hotel Properties",    "0001498542"),
    ("Apple Hospitality REIT",     "0001418121"),
    ("Chatham Lodging Trust",      "0001477932"),
    ("Sunstone Hotel Investors",   "0001295810"),
    ("Braemar Hotels & Resorts",   "0001232524"),
    ("Condor Hospitality Trust",   "0001005286"),
    # Hotel Operators
    ("Hilton Worldwide Holdings",  "0001585689"),
    ("Marriott International",     "0001048286"),
    ("Hyatt Hotels Corporation",   "0001468174"),
    ("Wyndham Hotels & Resorts",   "0001722684"),
    ("Choice Hotels International","0000730469"),
    ("InterContinental Hotels",    "0001532744"),
    ("Radisson Hotel Group",       "0000059558"),
    ("MGM Resorts International",  "0000789570"),
    ("Las Vegas Sands",            "0001300514"),
    ("Vail Resorts",               "0000812011"),
]

# Keywords that signal PM-relevant content in filings
PM_SIGNAL_WORDS = [
    "capital expenditure", "renovation", "construction", "implementation",
    "project", "timeline", "completion", "scheduled", "phase", "milestone",
    "technology", "system upgrade", "deployment", "infrastructure",
    "brand standard", "property improvement plan", "PIP",
]

def source_edgar_v2() -> list[dict]:
    headers = {"User-Agent": "PMCore Research steve@pmcore.ai"}
    records = []

    for company_name, cik in EDGAR_COMPANIES_V2:
        cik_clean = cik.lstrip("0")
        try:
            log(f"Fetching {company_name} (CIK {cik_clean})...")
            url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code != 200:
                log(f"  HTTP {r.status_code}")
                continue

            data     = r.json()
            filings  = data.get("filings", {}).get("recent", {})
            forms    = filings.get("form", [])
            acc_nos  = filings.get("accessionNumber", [])
            dates    = filings.get("filingDate", [])
            docs     = filings.get("primaryDocument", [])

            # Get last 3 10-K filings for richer data
            tenk_filings = [
                (acc_nos[i], dates[i], docs[i] if i < len(docs) else "")
                for i, f in enumerate(forms) if f == "10-K"
            ][:3]

            for acc_no, filing_date, primary_doc in tenk_filings:
                acc_formatted = acc_no.replace("-", "")
                doc_url = (
                    f"https://www.sec.gov/Archives/edgar/data/{cik_clean}/"
                    f"{acc_formatted}/{primary_doc}"
                )

                # Fetch the actual 10-K text
                try:
                    doc_r = requests.get(doc_url, headers=headers, timeout=30)
                    if doc_r.status_code != 200:
                        continue

                    raw_text = doc_r.text
                    # Strip HTML
                    text = clean_html(raw_text)
                    # Extract PM-relevant sentences
                    sentences = re.split(r'(?<=[.!?])\s+', text)
                    pm_sentences = [
                        s.strip() for s in sentences
                        if any(kw.lower() in s.lower() for kw in PM_SIGNAL_WORDS)
                        and 40 < len(s) < 600
                    ]

                    if len(pm_sentences) < 5:
                        continue

                    # Group into chunks of 5-10 sentences
                    for i in range(0, len(pm_sentences), 8):
                        chunk = " ".join(pm_sentences[i:i+8])
                        if len(chunk) < 200:
                            continue
                        records.append({
                            "source": f"edgar_{company_name.replace(' ','_').lower()}",
                            "input": (
                                f"What are the capital expenditure and project management "
                                f"activities reported by {company_name} in their {filing_date[:4]} "
                                f"annual report?"
                            ),
                            "output": chunk,
                            "filing_date": filing_date,
                            "format": "sec_filing",
                        })

                    log(f"  {company_name} {filing_date[:4]}: {len(pm_sentences)} PM sentences → {len(records)} total")

                except Exception as e:
                    log(f"  Doc fetch failed: {e}")

                time.sleep(0.2)  # SEC rate limit

        except Exception as e:
            log(f"  {company_name} failed: {e}")
        time.sleep(0.3)

    log(f"SEC EDGAR v2 total: {len(records)} examples")
    return records


# ── Source: Kaggle PM Datasets (direct CSV download) ──────────────────────────

KAGGLE_DATASETS = [
    # (owner/dataset, filename, description)
    ("claytonmiller/construction-and-project-management-example-data",
     None, "construction_pm"),
    ("programmer3/construction-project-management-dataset",
     None, "construction_pm_2"),
    ("ka66ledata/project-management-risk-raw",
     None, "pm_risk"),
    ("digrok/agile-project-dataset-2024",
     None, "agile_2024"),
    ("sircheruiyot/project-management-dataset",
     None, "pm_general"),
    ("ahmadilmanashraf/project-management-dataset-example",
     None, "pm_example"),
]

def source_kaggle() -> list[dict]:
    """Download Kaggle PM datasets using kaggle API."""
    try:
        import kaggle
    except ImportError:
        log("kaggle package not installed. Run: uv add kaggle")
        log("Also need ~/.kaggle/kaggle.json with your API credentials.")
        return _source_kaggle_manual()

    records = []
    dl_dir  = Path("./corpus/kaggle_downloads")
    dl_dir.mkdir(exist_ok=True)

    for dataset_id, filename, label in KAGGLE_DATASETS:
        try:
            log(f"Downloading {dataset_id}...")
            kaggle.api.dataset_download_files(
                dataset_id,
                path=str(dl_dir / label),
                unzip=True,
                quiet=True,
            )
            # Parse whatever CSV/JSON files we got
            for f in (dl_dir / label).rglob("*"):
                if f.suffix.lower() in [".csv", ".json", ".jsonl"]:
                    recs = _parse_kaggle_file(f, label, dataset_id)
                    records.extend(recs)
                    log(f"  {f.name}: {len(recs)} examples")

        except Exception as e:
            log(f"  {dataset_id} failed: {e}")

    log(f"Kaggle total: {len(records)} examples")
    return records


def _parse_kaggle_file(path: Path, label: str, source_id: str) -> list[dict]:
    """Convert Kaggle dataset rows into PMCore training format."""
    import csv
    records = []
    try:
        if path.suffix == ".csv":
            with open(path, encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Convert row to a PM Q&A example
                    text = " | ".join(f"{k}: {v}" for k, v in row.items() if v and v.strip())
                    if len(text) < 50: continue

                    # Build a natural language framing
                    records.append({
                        "source": f"kaggle_{label}",
                        "input": f"Analyze this project management data record: {list(row.keys())[:5]}",
                        "output": text[:1500],
                        "format": "structured_data",
                    })
        elif path.suffix in [".json", ".jsonl"]:
            with open(path, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                        text = json.dumps(obj)
                        if len(text) > 50:
                            records.append({
                                "source": f"kaggle_{label}",
                                "input": "Analyze this project management record:",
                                "output": text[:1500],
                                "format": "structured_data",
                            })
                    except: continue
    except Exception as e:
        log(f"  Parse error {path}: {e}")
    return records


def _source_kaggle_manual() -> list[dict]:
    """
    Fallback: download via direct Kaggle dataset URLs using requests.
    Requires KAGGLE_USERNAME and KAGGLE_KEY env vars.
    """
    username = os.environ.get("KAGGLE_USERNAME", "")
    key      = os.environ.get("KAGGLE_KEY", "")
    if not username or not key:
        log("Set KAGGLE_USERNAME and KAGGLE_KEY env vars or install kaggle package.")
        return []

    records = []
    dl_dir  = Path("./corpus/kaggle_downloads")
    dl_dir.mkdir(exist_ok=True)

    for dataset_id, _, label in KAGGLE_DATASETS:
        try:
            url = f"https://www.kaggle.com/api/v1/datasets/download/{dataset_id}"
            r = requests.get(url, auth=(username, key), stream=True, timeout=60)
            if r.status_code != 200:
                log(f"  {dataset_id}: HTTP {r.status_code}")
                continue

            import zipfile, io
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                z.extractall(dl_dir / label)

            for f in (dl_dir / label).rglob("*"):
                if f.suffix.lower() in [".csv", ".json", ".jsonl"]:
                    recs = _parse_kaggle_file(f, label, dataset_id)
                    records.extend(recs)
                    log(f"  {f.name}: {len(recs)} examples")

        except Exception as e:
            log(f"  {dataset_id} failed: {e}")

    log(f"Kaggle (manual) total: {len(records)}")
    return records


# ── Source: Data.gov + US Government Open Data ────────────────────────────────

DATAGOV_APIS = [
    # DOE Enterprise Project Management data
    ("https://api.data.gov/ed/collegescorecard/v1/schools.json",
     None,  # not relevant, skip
    ),
]

def source_datagov() -> list[dict]:
    """
    Pull from Data.gov and US government project data APIs.
    Focuses on:
    - DOE project management portfolio ($30B+ active projects)
    - GSA federal construction projects
    - DASNY active construction projects
    - Federal IT Dashboard (major IT projects)
    """
    headers = {"User-Agent": "PMCore Research steve@pmcore.ai"}
    records = []

    # 1. Federal IT Dashboard — major government IT projects
    log("Fetching Federal IT Dashboard...")
    try:
        url = "https://itdashboard.gov/api/v1/ITDB2/businessCase"
        r = requests.get(url, headers=headers, params={
            "statusId": "2",  # active projects
            "$top": 200,
            "$format": "json",
        }, timeout=30)
        if r.status_code == 200:
            data = r.json()
            items = data.get("value") or data.get("items") or (data if isinstance(data, list) else [])
            for item in items[:200]:
                name  = item.get("investmentTitle") or item.get("name", "")
                desc  = item.get("description") or item.get("objectives", "")
                budget= item.get("totalFYSpending") or item.get("budget", "")
                agency= item.get("agencyName") or item.get("agency", "")
                if not name or len(str(desc)) < 30: continue
                records.append({
                    "source": "datagov_it_dashboard",
                    "input": f"Describe the federal IT project: {name} (Agency: {agency})",
                    "output": f"## Federal IT Project: {name}\n\nAgency: {agency}\nBudget: ${budget}\n\n{desc}",
                    "format": "government_project",
                })
            log(f"  IT Dashboard: {len(records)} projects")
    except Exception as e:
        log(f"  IT Dashboard: {e}")

    # 2. DASNY Active Construction Projects (NY State)
    log("Fetching DASNY construction projects...")
    try:
        url = "https://data.ny.gov/resource/eem5-iyvb.json"
        r = requests.get(url, headers=headers, params={"$limit": 500}, timeout=30)
        if r.status_code == 200:
            for item in r.json():
                proj_name = item.get("project_name", "")
                managing_org = item.get("managing_organization", "")
                phase = item.get("phase_status", "")
                cost = item.get("project_cost", "")
                if not proj_name: continue
                records.append({
                    "source": "datagov_dasny_construction",
                    "input": f"What is the status of the {proj_name} construction project?",
                    "output": (
                        f"## Project: {proj_name}\n\n"
                        f"Managing Organization: {managing_org}\n"
                        f"Phase: {phase}\n"
                        f"Budget: {cost}\n\n"
                        f"This is an active construction project under DASNY oversight "
                        f"with full project management controls including scope, schedule, and budget tracking."
                    ),
                    "format": "government_project",
                })
            log(f"  DASNY: {sum(1 for r in records if 'dasny' in r['source'])} projects")
    except Exception as e:
        log(f"  DASNY: {e}")

    # 3. NYC Capital Projects (one of the largest public PM datasets)
    log("Fetching NYC Capital Projects...")
    try:
        url = "https://data.cityofnewyork.us/resource/fi59-268w.json"
        r = requests.get(url, headers=headers, params={"$limit": 500}, timeout=30)
        if r.status_code == 200:
            for item in r.json():
                name   = item.get("project_name") or item.get("projectname", "")
                scope  = item.get("project_description") or item.get("scope", "")
                budget = item.get("total_budget") or item.get("budget", "")
                agency = item.get("managing_agency") or item.get("agency", "")
                status = item.get("phase") or item.get("status", "active")
                if not name or len(str(scope)) < 20: continue
                records.append({
                    "source": "datagov_nyc_capital",
                    "input": f"Summarize this NYC capital project: {name}",
                    "output": (
                        f"## NYC Capital Project: {name}\n\n"
                        f"Agency: {agency}\n"
                        f"Phase: {status}\n"
                        f"Budget: ${budget}\n\n"
                        f"Scope: {str(scope)[:600]}"
                    ),
                    "format": "government_project",
                })
            log(f"  NYC Capital: {sum(1 for r in records if 'nyc' in r['source'])} projects")
    except Exception as e:
        log(f"  NYC Capital: {e}")

    # 4. US DOT Federal Highway Projects
    log("Fetching DOT Federal Aid Projects...")
    try:
        url = "https://data.transportation.gov/resource/4n3x-t5vc.json"
        r = requests.get(url, headers=headers, params={"$limit": 300}, timeout=30)
        if r.status_code == 200:
            for item in r.json():
                desc  = str(item.get("project_description","") or item.get("description",""))
                cost  = item.get("federal_share_amount","")
                state = item.get("state_name","")
                cat   = item.get("work_type_description","")
                if len(desc) < 30: continue
                records.append({
                    "source": "datagov_dot_highway",
                    "input": f"Describe this federal highway construction project in {state}:",
                    "output": (
                        f"## Federal Highway Project\n\n"
                        f"State: {state}\nWork Type: {cat}\n"
                        f"Federal Share: ${cost}\n\n"
                        f"Description: {desc[:800]}"
                    ),
                    "format": "government_project",
                })
            log(f"  DOT Highway: {sum(1 for r in records if 'dot' in r['source'])} projects")
    except Exception as e:
        log(f"  DOT Highway: {e}")

    # 5. World Bank Open Data — project portfolio
    log("Fetching World Bank projects...")
    try:
        url = "https://search.worldbank.org/api/v2/projects"
        r = requests.get(url, headers=headers, params={
            "format": "json",
            "rows": 200,
            "fl": "project_name,projectdocs,sector1,totalamt,status,closingdate,project_abstract",
            "fq": "status:Active",
        }, timeout=30)
        if r.status_code == 200:
            projects = r.json().get("projects", {})
            for pid, proj in list(projects.items())[:200]:
                if pid == "total": continue
                name     = proj.get("project_name", "")
                abstract = proj.get("project_abstract", {})
                if isinstance(abstract, dict):
                    abstract = abstract.get("cdata", "") or str(abstract)
                sector = proj.get("sector1", {})
                if isinstance(sector, dict):
                    sector = sector.get("Name", "")
                budget = proj.get("totalamt", "")
                if not name or len(str(abstract)) < 50: continue
                records.append({
                    "source": "worldbank_projects",
                    "input": f"Describe the World Bank project: {name}",
                    "output": (
                        f"## World Bank Project: {name}\n\n"
                        f"Sector: {sector}\nTotal Amount: ${budget}\n\n"
                        f"{str(abstract)[:800]}"
                    ),
                    "format": "government_project",
                })
            log(f"  World Bank: {sum(1 for r in records if 'worldbank' in r['source'])} projects")
    except Exception as e:
        log(f"  World Bank: {e}")

    log(f"Data.gov / Gov total: {len(records)} examples")
    return records


# ── Source: Firecrawl v2 (expanded targets) ───────────────────────────────────

FIRECRAWL_V2_TARGETS = [
    # PM methodology & best practices
    ("https://www.pmi.org/learning/library/articles",             100, "PMI articles"),
    ("https://www.prince2.com/eur/blog",                           80, "PRINCE2 blog"),
    ("https://www.apm.org.uk/resources/find-a-resource/articles",  80, "APM resources"),
    ("https://www.projectmanagement.com/articles",                100, "PM.com articles"),
    ("https://www.smartsheet.com/content-center/project-management",100,"Smartsheet PM guides"),
    ("https://www.wrike.com/project-management-guide",             80, "Wrike PM guide"),
    ("https://asana.com/resources/project-management",             80, "Asana PM resources"),
    ("https://www.teamgantt.com/blog",                             80, "TeamGantt blog"),
    ("https://www.mpug.com/articles",                              80, "MPUG Microsoft PM"),
    ("https://www.girlsguidetopm.com/articles",                    60, "PM career articles"),
    # Hospitality / hotel industry
    ("https://www.hospitalitynet.org/news/4hotel_investment",      80, "Hotel investment news"),
    ("https://hoteltechnologynews.com",                             80, "Hotel tech news"),
    ("https://www.hvs.com/articles",                               80, "HVS hospitality insights"),
    ("https://www.costar.com/article/hospitality",                 50, "CoStar hotel news"),
    ("https://str.com/press-release",                              50, "STR hotel data reports"),
    # Real estate / REIT / capex
    ("https://www.reit.com/news/articles",                         80, "NAREIT articles"),
    ("https://www.globest.com/hotel",                              80, "GlobeSt hotel RE"),
    ("https://www.bisnow.com/national/news/hotel",                 80, "Bisnow hotel news"),
    # Risk management
    ("https://www.riskmgmt.com/articles",                          50, "Risk management"),
    ("https://continuitycentral.com/index.php/news/business-continuity-news", 50, "Business continuity"),
]

def source_firecrawl_v2() -> list[dict]:
    if not FIRECRAWL_API_KEY:
        log("FIRECRAWL_API_KEY not set. Skipping.")
        return []

    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }

    PM_KEYWORDS = [
        "project", "plan", "schedule", "milestone", "stakeholder", "risk",
        "budget", "scope", "agile", "sprint", "waterfall", "deliverable",
        "gantt", "critical path", "resource", "renovation", "capex", "hotel",
        "construction", "timeline", "deadline", "phase", "charter",
        "work breakdown", "dependency", "constraint",
    ]

    records     = []
    total_pages = 0
    PAGE_BUDGET = 95000  # Leave buffer on Hobby plan

    for url, max_pages, description in FIRECRAWL_V2_TARGETS:
        if total_pages >= PAGE_BUDGET:
            log(f"Page budget reached ({PAGE_BUDGET}). Stopping.")
            break

        pages_this = min(max_pages, PAGE_BUDGET - total_pages)
        log(f"Crawling: {description} ({pages_this} pages)...")

        try:
            r = requests.post(
                "https://api.firecrawl.dev/v1/crawl",
                headers=headers,
                json={
                    "url": url,
                    "limit": pages_this,
                    "scrapeOptions": {
                        "formats": ["markdown"],
                        "onlyMainContent": True,
                        "excludeTags": ["nav","footer","header","aside","script","style","form"],
                    },
                    "excludePaths": ["/tag/","/author/","/search","/login","/signup","/cart","/shop"],
                },
                timeout=30,
            )
            if r.status_code != 200:
                log(f"  Error {r.status_code}: {r.text[:100]}")
                continue

            crawl_id = r.json().get("id","")
            if not crawl_id:
                continue

            # Poll for results
            for attempt in range(90):
                time.sleep(5)
                sr = requests.get(f"https://api.firecrawl.dev/v1/crawl/{crawl_id}", headers=headers, timeout=20)
                if sr.status_code != 200: break

                status = sr.json()
                if attempt % 6 == 0:
                    log(f"  {status.get('status','?')}: {status.get('completed',0)} pages")

                if status.get("status") == "completed":
                    pages = status.get("data", [])
                    added = 0
                    for page in pages:
                        content = page.get("markdown","") or ""
                        title   = page.get("metadata",{}).get("title","") or ""
                        page_url= page.get("url","")

                        kw_hits = sum(1 for kw in PM_KEYWORDS if kw in content.lower())
                        if kw_hits < 3 or len(content) < 300: continue

                        # Chunk the article
                        paragraphs = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 80]
                        chunk, chunks = "", []
                        for para in paragraphs:
                            if len(chunk) + len(para) > 1200 and chunk:
                                chunks.append(chunk)
                                chunk = para
                            else:
                                chunk = (chunk + "\n\n" + para).strip()
                        if chunk: chunks.append(chunk)

                        for i, c in enumerate(chunks):
                            records.append({
                                "source": f"fc_{url.split('/')[2].replace('.','_')}",
                                "input": (
                                    f"Explain project management best practices. "
                                    f"(Source: {title}, Part {i+1})"
                                    if i == 0 else
                                    f"Continue explaining project management concepts from: {title}"
                                ),
                                "output": c,
                                "url": page_url,
                                "format": "article",
                            })
                            added += 1

                    total_pages += len(pages)
                    log(f"  Done: {len(pages)} pages → {added} chunks (total pages: {total_pages})")
                    break

                elif status.get("status") in ["failed","cancelled"]:
                    log(f"  Crawl {crawl_id} failed")
                    break

        except Exception as e:
            log(f"  {url}: {e}")

    log(f"Firecrawl v2 total: {len(records)} chunks from {total_pages} pages")
    return records


# ── Load v1 cached sources ────────────────────────────────────────────────────

def load_v1_cache() -> list[dict]:
    """Load previously gathered v1 data."""
    records = []
    for fname in ["se_corpus.jsonl", "gh_corpus.jsonl", "sec_corpus.jsonl"]:
        path = RAW_DIR / fname
        if path.exists():
            with open(path) as f:
                batch = [json.loads(l) for l in f if l.strip()]
            log(f"Loaded cache: {fname} ({len(batch):,})")
            records.extend(batch)
    return records


# ── Dedup + Combine ───────────────────────────────────────────────────────────

def deduplicate(records):
    seen, unique = set(), []
    for r in records:
        key = hashlib.md5(r.get("input","")[:200].lower().encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def combine_and_save(all_records):
    unique = deduplicate(all_records)
    unique.sort(key=lambda r: len(r.get("output","")), reverse=True)

    with open(COMBINED_V2, "w") as f:
        for r in unique:
            f.write(json.dumps(r) + "\n")

    print(f"\n{'='*60}")
    print(f"Combined v2 corpus: {len(unique):,} unique examples")
    print(f"Saved to: {COMBINED_V2}")

    from collections import Counter
    sources = Counter(r["source"].split("_")[0] for r in unique)
    for src, count in sources.most_common():
        print(f"  {src:20s}: {count:,}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("PMCore Corpus Gatherer v2 — Wide Net")
    print("=" * 60)

    all_records = []

    # Load v1 cache first (SE, GitHub already done)
    print("\n[Loading v1 cache]")
    all_records.extend(load_v1_cache())

    # HuggingFace v2 (fixed smoltalk + new datasets)
    print("\n[HuggingFace v2]")
    path = RAW_DIR / "hf_v2_corpus.jsonl"
    hf_recs = source_huggingface_v2()
    save_jsonl(path, hf_recs)
    all_records.extend(hf_recs)

    # SEC EDGAR v2 (expanded hotel universe — actual 10-K text)
    print("\n[SEC EDGAR v2 — 20 Hotel Companies]")
    path = RAW_DIR / "edgar_v2_corpus.jsonl"
    edgar_recs = source_edgar_v2()
    save_jsonl(path, edgar_recs)
    all_records.extend(edgar_recs)

    # Kaggle
    print("\n[Kaggle PM Datasets]")
    path = RAW_DIR / "kaggle_corpus.jsonl"
    kaggle_recs = source_kaggle()
    save_jsonl(path, kaggle_recs)
    all_records.extend(kaggle_recs)

    # Data.gov + World Bank + Government
    print("\n[Data.gov / Government / World Bank]")
    path = RAW_DIR / "gov_corpus.jsonl"
    gov_recs = source_datagov()
    save_jsonl(path, gov_recs)
    all_records.extend(gov_recs)

    # Firecrawl v2 (expanded targets)
    print("\n[Firecrawl v2 — 20 Sites]")
    path = RAW_DIR / "fc_v2_corpus.jsonl"
    fc_recs = source_firecrawl_v2()
    save_jsonl(path, fc_recs)
    all_records.extend(fc_recs)

    combine_and_save(all_records)
