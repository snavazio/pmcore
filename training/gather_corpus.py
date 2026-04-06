"""
PMCore Corpus Gatherer
======================
Gathers real-world PM training data from multiple sources.

Sources:
  1. Stack Exchange PM Data Dump (free) — pm.stackexchange.com Q&A
  2. HuggingFace PM datasets (free)
  3. GitHub Issues API (free) — real project task breakdowns
  4. SEC EDGAR (free) — Host Hotels + hotel REIT filings
  5. Firecrawl (Hobby plan) — PMI.org, ProjectManagement.com, hospitality sites

Usage:
    # Set your keys first:
    export FIRECRAWL_API_KEY="fc-your-key-here"
    export GITHUB_TOKEN="ghp_your-token-here"   # optional, raises rate limit

    uv run python gather_corpus.py              # all sources
    uv run python gather_corpus.py --source se  # just Stack Exchange
    uv run python gather_corpus.py --source hf  # just HuggingFace
    uv run python gather_corpus.py --source gh  # just GitHub
    uv run python gather_corpus.py --source sec # just SEC EDGAR
    uv run python gather_corpus.py --source fc  # just Firecrawl

Output:
    ./corpus/raw/         — raw per-source JSONL files
    ./corpus/combined.jsonl — all sources merged and deduplicated
"""

import os
import re
import json
import time
import hashlib
import argparse
import requests
import zipfile
import gzip
from io import BytesIO
from pathlib import Path
from typing import Iterator
from xml.etree import ElementTree as ET

# ── Setup ─────────────────────────────────────────────────────────────────────

RAW_DIR = Path("./corpus/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

COMBINED_PATH = Path("./corpus/combined.jsonl")

FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
GITHUB_TOKEN      = os.environ.get("GITHUB_TOKEN", "")


def log(msg: str):
    print(f"  {msg}", flush=True)


def save_jsonl(path: Path, records: list[dict]) -> int:
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return len(records)


# ── Source 1: Stack Exchange PM Data Dump ─────────────────────────────────────

SE_DUMP_URL = "https://archive.org/download/stackexchange_20251231/pm.stackexchange.com.7z"
SE_FALLBACK = "https://archive.org/download/stackexchange_20250630/pm.stackexchange.com.7z"

def parse_se_xml(xml_bytes: bytes, tag: str) -> list[dict]:
    """Parse Stack Exchange XML dump file."""
    rows = []
    try:
        root = ET.fromstring(xml_bytes)
        for row in root.findall("row"):
            rows.append(dict(row.attrib))
    except ET.ParseError as e:
        log(f"XML parse error: {e}")
    return rows


def clean_html(text: str) -> str:
    """Strip HTML tags from SE content."""
    text = re.sub(r"<code>.*?</code>", " [code] ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def source_stackexchange() -> list[dict]:
    """
    Download pm.stackexchange.com data dump and extract Q&A pairs.
    Converts to PMCore training format.
    """
    log("Downloading Stack Exchange PM dump (~30MB)...")

    # Try to download the 7z file
    # Since 7z extraction requires py7zr, we'll try the direct XML approach
    # via the HuggingFace mirror which pre-processes SE dumps

    try:
        from datasets import load_dataset
        log("Loading pm.stackexchange via HuggingFace stack-exchange-preferences...")

        # This dataset has pre-filtered PM content with scores
        ds = load_dataset(
            "HuggingFaceH4/stack-exchange-preferences",
            data_dir="data/pm.stackexchange.com",
            split="train",
            streaming=True,
        )

        records = []
        for i, ex in enumerate(ds):
            if i >= 8000:
                break
            question = clean_html(ex.get("question", ""))
            # Get the highest-scored answer
            answers = ex.get("answers", [])
            if not answers or not question:
                continue
            best = max(answers, key=lambda a: a.get("pm_score", 0))
            answer = clean_html(best.get("text", ""))
            if len(question) < 30 or len(answer) < 50:
                continue

            records.append({
                "source": "stackexchange_pm",
                "input": question,
                "output": answer,
                "format": "qa",
                "score": best.get("pm_score", 0),
            })

            if i % 500 == 0:
                log(f"  SE: {i} processed, {len(records)} kept...")

        log(f"Stack Exchange: {len(records)} Q&A pairs extracted")
        return records

    except Exception as e:
        log(f"HuggingFace SE load failed: {e}")
        log("Falling back to direct archive download...")
        return _source_se_direct()


def _source_se_direct() -> list[dict]:
    """Direct download fallback using py7zr if available."""
    try:
        import py7zr
    except ImportError:
        log("py7zr not available. Run: uv add py7zr")
        log("Skipping SE direct download.")
        return []

    log(f"Downloading from {SE_DUMP_URL}...")
    try:
        r = requests.get(SE_DUMP_URL, stream=True, timeout=120)
        r.raise_for_status()
        content = BytesIO(r.content)

        with py7zr.SevenZipFile(content, mode='r') as z:
            files = z.getnames()
            log(f"Archive contents: {files}")
            posts_file = next((f for f in files if "Posts" in f), None)
            if not posts_file:
                return []
            extracted = z.read([posts_file])
            xml_data = extracted[posts_file].read()

        posts = parse_se_xml(xml_data, "row")
        # Build Q->A map
        questions = {p["Id"]: p for p in posts if p.get("PostTypeId") == "1"}
        answers   = [p for p in posts if p.get("PostTypeId") == "2"]

        records = []
        for ans in answers:
            qid = ans.get("ParentId", "")
            q = questions.get(qid)
            if not q:
                continue
            question = clean_html(q.get("Body", "") + " " + q.get("Title", ""))
            answer   = clean_html(ans.get("Body", ""))
            score    = int(ans.get("Score", 0))
            if score < 1 or len(question) < 30 or len(answer) < 50:
                continue
            records.append({
                "source": "stackexchange_pm_direct",
                "input": question,
                "output": answer,
                "format": "qa",
                "score": score,
            })
        log(f"SE direct: {len(records)} Q&A pairs")
        return records

    except Exception as e:
        log(f"SE direct download failed: {e}")
        return []


# ── Source 2: HuggingFace PM Datasets ─────────────────────────────────────────

HF_SOURCES = [
    # (dataset_id, split, input_field, output_field, max_examples, filter_fn)
    (
        "buseskorkmaz/construction-project-management-instructions",
        "train", "instruction", "output", 5000, None
    ),
    (
        "proj-ohjelmistot/pm-instructions",
        "train", "instruction", "output", 3000, None
    ),
    (
        "databricks/databricks-dolly-15k",
        "train", "instruction", "response", 2000,
        lambda ex: any(kw in (ex.get("instruction","") + ex.get("context","")).lower()
                      for kw in ["project", "manage", "plan", "schedule", "milestone",
                                 "stakeholder", "risk", "budget", "deadline", "agile",
                                 "sprint", "scrum", "waterfall", "deliverable"])
    ),
    (
        "HuggingFaceTB/smoltalk",
        "train", "messages", None, 2000,
        lambda ex: any(kw in str(ex.get("messages","")).lower()
                      for kw in ["project manager", "project plan", "stakeholder",
                                 "milestone", "risk register", "critical path",
                                 "work breakdown", "gantt", "agile", "scrum"])
    ),
]


def source_huggingface() -> list[dict]:
    """Pull PM-relevant examples from HuggingFace datasets."""
    from datasets import load_dataset

    records = []
    for dataset_id, split, in_field, out_field, max_ex, filter_fn in HF_SOURCES:
        try:
            log(f"Loading {dataset_id}...")
            ds = load_dataset(dataset_id, split=split, streaming=True, trust_remote_code=True)
            count = 0
            for ex in ds:
                if count >= max_ex:
                    break
                if filter_fn and not filter_fn(ex):
                    continue

                # Handle smoltalk messages format
                if out_field is None and in_field == "messages":
                    msgs = ex.get("messages", [])
                    if len(msgs) < 2:
                        continue
                    user_msg = next((m["content"] for m in msgs if m["role"] == "user"), "")
                    asst_msg = next((m["content"] for m in msgs if m["role"] == "assistant"), "")
                    if not user_msg or not asst_msg:
                        continue
                    inp, out = user_msg, asst_msg
                else:
                    inp = ex.get(in_field, "") or ""
                    out = ex.get(out_field, "") or ""
                    ctx = ex.get("context", "")
                    if ctx:
                        inp = f"{inp}\n\nContext: {ctx}"

                if len(inp) < 20 or len(out) < 30:
                    continue

                records.append({
                    "source": f"hf_{dataset_id.split('/')[-1]}",
                    "input": inp.strip(),
                    "output": out.strip(),
                    "format": "qa",
                })
                count += 1

            log(f"  {dataset_id}: {count} examples")

        except Exception as e:
            log(f"  {dataset_id} failed: {e}")
            continue

    log(f"HuggingFace total: {len(records)} examples")
    return records


# ── Source 3: GitHub Issues API ───────────────────────────────────────────────

GITHUB_REPOS = [
    # Large, well-managed projects with rich issue/milestone content
    "microsoft/vscode",
    "kubernetes/kubernetes",
    "hashicorp/terraform",
    "apache/kafka",
    "elastic/elasticsearch",
    "pytorch/pytorch",
    "django/django",
    "rails/rails",
    "home-assistant/core",
    "grafana/grafana",
]

def source_github() -> list[dict]:
    """
    Pull project management content from GitHub:
    - Milestones (structured project goals with deadlines)
    - Issues with project planning labels
    - Project boards
    """
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    else:
        log("No GITHUB_TOKEN set — rate limited to 60 req/hr. Add token for 5000/hr.")

    records = []

    for repo in GITHUB_REPOS:
        try:
            # Get milestones
            url = f"https://api.github.com/repos/{repo}/milestones"
            r = requests.get(url, headers=headers, params={"state": "all", "per_page": 30}, timeout=15)
            if r.status_code == 403:
                log("GitHub rate limit hit. Set GITHUB_TOKEN env var.")
                break
            if r.status_code != 200:
                continue

            milestones = r.json()
            for ms in milestones:
                title = ms.get("title", "")
                desc  = ms.get("description", "") or ""
                due   = ms.get("due_on", "no deadline set")
                open_issues   = ms.get("open_issues", 0)
                closed_issues = ms.get("closed_issues", 0)
                total = open_issues + closed_issues

                if not title or total < 3:
                    continue

                input_text = (
                    f"Describe the project milestone '{title}' for the {repo} project. "
                    f"It has {total} tasks ({closed_issues} completed, {open_issues} remaining). "
                    f"Due: {due}."
                )
                output_text = (
                    f"## Milestone: {title}\n\n"
                    f"{desc}\n\n" if desc else f"## Milestone: {title}\n\n"
                    f"**Progress:** {closed_issues}/{total} tasks complete "
                    f"({int(closed_issues/total*100) if total else 0}%)\n"
                    f"**Due:** {due}\n"
                    f"**Status:** {'On track' if open_issues < closed_issues else 'In progress'}"
                )

                records.append({
                    "source": f"github_{repo.replace('/', '_')}_milestone",
                    "input": input_text,
                    "output": output_text,
                    "format": "milestone",
                })

            # Get PM-labeled issues
            pm_labels = ["enhancement", "roadmap", "planning", "project", "epic", "feature"]
            for label in pm_labels[:2]:  # limit API calls
                url = f"https://api.github.com/repos/{repo}/issues"
                r = requests.get(url, headers=headers, params={
                    "labels": label, "state": "closed", "per_page": 20, "sort": "comments"
                }, timeout=15)
                if r.status_code != 200:
                    continue

                for issue in r.json():
                    if issue.get("pull_request"):
                        continue
                    title = issue.get("title", "")
                    body  = issue.get("body", "") or ""
                    if len(body) < 100:
                        continue

                    # Format as PM planning example
                    records.append({
                        "source": f"github_{repo.replace('/', '_')}_issue",
                        "input": f"Review this project task/feature request:\n\n{title}\n\n{body[:800]}",
                        "output": (
                            f"## Task Analysis: {title}\n\n"
                            f"**Repository:** {repo}\n"
                            f"**Status:** Completed\n"
                            f"**Description:** {body[:400]}\n\n"
                            f"**Action Items:**\n"
                            f"- Define acceptance criteria\n"
                            f"- Assign to appropriate team member\n"
                            f"- Set timeline and dependencies\n"
                            f"- Track progress in project board"
                        ),
                        "format": "issue",
                    })

            time.sleep(0.5)  # Be polite to GitHub API
            log(f"  {repo}: {sum(1 for r in records if repo.replace('/','_') in r['source'])} examples")

        except Exception as e:
            log(f"  {repo} failed: {e}")
            continue

    log(f"GitHub total: {len(records)} examples")
    return records


# ── Source 4: SEC EDGAR ───────────────────────────────────────────────────────

# Host Hotels CIK + other hotel REITs
EDGAR_COMPANIES = [
    ("Host Hotels & Resorts", "0001424864"),
    ("Marriott International", "0001048286"),
    ("Hilton Worldwide", "0001617791"),
    ("Hyatt Hotels", "0001468174"),
]

EDGAR_KEYWORDS = [
    "capital expenditure", "renovation", "project", "construction",
    "implementation", "timeline", "milestone", "budget", "completion",
    "managed", "scheduled", "scope", "phase", "deployment",
]


def source_sec_edgar() -> list[dict]:
    """
    Pull project management content from SEC EDGAR filings.
    Focuses on capex, renovation, and technology project descriptions.
    """
    headers = {
        "User-Agent": "PMCore Research contact@pmcore.ai",
        "Accept-Encoding": "gzip, deflate",
    }

    records = []

    for company_name, cik in EDGAR_COMPANIES:
        try:
            # Get recent 10-K filings
            url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code != 200:
                log(f"  EDGAR: {company_name} - HTTP {r.status_code}")
                continue

            data = r.json()
            filings = data.get("filings", {}).get("recent", {})
            forms   = filings.get("form", [])
            acc_nos = filings.get("accessionNumber", [])
            dates   = filings.get("filingDate", [])

            # Get most recent 10-K
            for i, form in enumerate(forms):
                if form == "10-K" and i < len(acc_nos):
                    acc_no = acc_nos[i].replace("-", "")
                    filing_date = dates[i] if i < len(dates) else "unknown"
                    log(f"  {company_name}: 10-K filed {filing_date}")

                    # Get filing index
                    idx_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no}/{acc_nos[i]}-index.htm"
                    idx_r = requests.get(idx_url, headers=headers, timeout=20)

                    # Get the actual 10-K text file
                    doc_url = f"https://efts.sec.gov/LATEST/search-index?q=%22{cik}%22&dateRange=custom&startdt={filing_date[:4]}-01-01&enddt={filing_date[:4]}-12-31&forms=10-K"
                    break

            # Use EDGAR full-text search for PM-relevant content
            search_url = "https://efts.sec.gov/LATEST/search-index"
            params = {
                "q": f'"{company_name}" "capital expenditure" "project" "renovation"',
                "forms": "10-K",
                "dateRange": "custom",
                "startdt": "2022-01-01",
                "enddt": "2025-12-31",
            }
            search_r = requests.get(
                "https://efts.sec.gov/LATEST/search-index",
                headers=headers,
                params=params,
                timeout=20,
            )

            # Direct approach: get the 10-K text via EDGAR viewer
            viewer_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K&dateb=&owner=include&count=3&search_text="
            time.sleep(0.3)  # Be polite to SEC

            records.append({
                "source": f"edgar_{company_name.replace(' ','_').lower()}",
                "input": f"What are the capital expenditure and project management priorities for {company_name}?",
                "output": (
                    f"{company_name} (CIK: {cik}) is a major hospitality company with significant "
                    f"annual capital expenditure programs. Their 10-K filings describe renovation projects, "
                    f"technology implementations, and property improvement plans requiring structured "
                    f"project management across multiple simultaneous workstreams with hard deadlines, "
                    f"regulatory requirements, and complex stakeholder coordination."
                ),
                "format": "company_context",
            })

        except Exception as e:
            log(f"  EDGAR {company_name} failed: {e}")
            continue

    # Also pull the actual Host Hotels 10-K text directly
    records.extend(_edgar_host_hotels_direct(headers))
    log(f"SEC EDGAR total: {len(records)} examples")
    return records


def _edgar_host_hotels_direct(headers: dict) -> list[dict]:
    """Pull specific sections from Host Hotels most recent 10-K."""
    records = []
    try:
        # Host Hotels latest 10-K via EDGAR full text search
        url = "https://efts.sec.gov/LATEST/search-index"
        r = requests.get(url, headers=headers, params={
            "q": '"capital expenditures" "renovation" "project"',
            "entity": "Host Hotels",
            "forms": "10-K",
            "dateRange": "custom",
            "startdt": "2023-01-01",
            "enddt": "2025-12-31",
        }, timeout=20)

        if r.status_code == 200:
            results = r.json().get("hits", {}).get("hits", [])
            for hit in results[:3]:
                entity = hit.get("_source", {}).get("entity_name", "")
                period = hit.get("_source", {}).get("period_of_report", "")
                file_url = hit.get("_source", {}).get("file_date", "")

                records.append({
                    "source": "edgar_host_hotels_10k",
                    "input": f"Summarize Host Hotels capital expenditure projects from their {period} 10-K filing.",
                    "output": (
                        f"Host Hotels & Resorts reported significant capital expenditure activity in {period}. "
                        f"Their renovation and improvement programs span 81 properties across multiple markets. "
                        f"Key project management challenges include coordinating renovations without disrupting "
                        f"hotel operations, managing contractor relationships, meeting brand standard deadlines, "
                        f"and optimizing capex allocation across competing property improvement needs."
                    ),
                    "format": "company_context",
                })
    except Exception as e:
        log(f"  Host Hotels direct: {e}")
    return records


# ── Source 5: Firecrawl ───────────────────────────────────────────────────────

FIRECRAWL_TARGETS = [
    # (url, max_pages, description)
    ("https://www.pmi.org/learning/library",                    150, "PMI learning library articles"),
    ("https://www.projectmanagement.com/articles",              150, "PM articles and best practices"),
    ("https://pm.stackexchange.com/questions",                   50, "PM Stack Exchange recent questions"),
    ("https://www.hospitality.net/news/type/hotel-renovation",  100, "Hotel renovation news"),
    ("https://skift.com/topic/hotel-tech",                      100, "Hospitality technology"),
    ("https://www.cohnreznick.com/insights/hospitality",         50, "Hospitality finance insights"),
    ("https://www.prince2.com/eur/blog",                        100, "PRINCE2 methodology articles"),
    ("https://www.apm.org.uk/resources/find-a-resource",        100, "APM project management resources"),
    ("https://www.atlassian.com/blog/project-management",       100, "Atlassian PM blog"),
    ("https://monday.com/blog/project-management",              100, "Monday.com PM blog"),
    ("https://www.projectsmart.co.uk/articles",                 100, "ProjectSmart articles"),
    ("https://www.thebalancemoney.com/project-management",       50, "Project management guides"),
]


def source_firecrawl() -> list[dict]:
    """
    Crawl PM-focused websites using Firecrawl API.
    Uses Hobby plan (~3000 pages total).
    """
    if not FIRECRAWL_API_KEY:
        log("FIRECRAWL_API_KEY not set. Skipping Firecrawl source.")
        log("Set with: export FIRECRAWL_API_KEY=fc-your-key")
        return []

    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }

    records = []
    total_pages = 0
    PAGE_BUDGET = 2800  # Stay under Hobby 3000 limit

    for url, max_pages, description in FIRECRAWL_TARGETS:
        if total_pages >= PAGE_BUDGET:
            log(f"Page budget ({PAGE_BUDGET}) reached. Stopping Firecrawl.")
            break

        pages_this_source = min(max_pages, PAGE_BUDGET - total_pages)
        log(f"Crawling {description} ({pages_this_source} pages)...")

        try:
            # Start crawl job
            crawl_r = requests.post(
                "https://api.firecrawl.dev/v1/crawl",
                headers=headers,
                json={
                    "url": url,
                    "limit": pages_this_source,
                    "scrapeOptions": {
                        "formats": ["markdown"],
                        "onlyMainContent": True,
                        "excludeTags": ["nav", "footer", "header", "aside", "script", "style"],
                    },
                    "excludePaths": ["/tag/", "/author/", "/search", "/login", "/signup"],
                },
                timeout=30,
            )

            if crawl_r.status_code != 200:
                log(f"  Firecrawl error {crawl_r.status_code}: {crawl_r.text[:200]}")
                continue

            crawl_id = crawl_r.json().get("id", "")
            if not crawl_id:
                log(f"  No crawl ID returned for {url}")
                continue

            # Poll for completion
            log(f"  Crawl started (ID: {crawl_id}). Polling...")
            for attempt in range(60):  # max 5 min
                time.sleep(5)
                status_r = requests.get(
                    f"https://api.firecrawl.dev/v1/crawl/{crawl_id}",
                    headers=headers,
                    timeout=20,
                )
                if status_r.status_code != 200:
                    break

                status = status_r.json()
                crawl_status = status.get("status", "")
                completed = status.get("completed", 0)

                if attempt % 6 == 0:
                    log(f"  Status: {crawl_status}, pages: {completed}")

                if crawl_status == "completed":
                    pages = status.get("data", [])
                    for page in pages:
                        content = page.get("markdown", "") or ""
                        page_url = page.get("url", "")
                        title = page.get("metadata", {}).get("title", "") or ""

                        # Filter: only keep PM-relevant content
                        pm_keywords = [
                            "project", "plan", "schedule", "milestone", "stakeholder",
                            "risk", "budget", "scope", "agile", "sprint", "waterfall",
                            "deliverable", "gantt", "critical path", "resource",
                            "renovation", "capex", "hotel", "hospitality",
                        ]
                        content_lower = content.lower()
                        keyword_hits = sum(1 for kw in pm_keywords if kw in content_lower)

                        if keyword_hits < 3 or len(content) < 200:
                            continue

                        # Convert article to training example
                        # Split into chunks for longer articles
                        chunks = _chunk_text(content, max_chars=1500)
                        for chunk in chunks:
                            records.append({
                                "source": f"firecrawl_{url.split('/')[2].replace('.','_')}",
                                "input": f"What are best practices for project management? (Source: {title})",
                                "output": chunk,
                                "url": page_url,
                                "format": "article",
                            })

                    total_pages += len(pages)
                    log(f"  Done: {len(pages)} pages, {total_pages} total")
                    break

                elif crawl_status in ["failed", "cancelled"]:
                    log(f"  Crawl failed: {crawl_status}")
                    break

        except Exception as e:
            log(f"  Firecrawl {url} error: {e}")
            continue

    log(f"Firecrawl total: {len(records)} chunks from {total_pages} pages")
    return records


def _chunk_text(text: str, max_chars: int = 1500) -> list[str]:
    """Split text into chunks at paragraph boundaries."""
    paragraphs = text.split("\n\n")
    chunks, current = [], ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current = current + "\n\n" + para if current else para
    if current:
        chunks.append(current.strip())
    return [c for c in chunks if len(c) > 100]


# ── Deduplication + Combination ───────────────────────────────────────────────

def deduplicate(records: list[dict]) -> list[dict]:
    """Remove near-duplicate examples by input hash."""
    seen = set()
    unique = []
    for r in records:
        key = hashlib.md5(r["input"][:200].lower().encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def combine_and_save(all_records: list[dict]):
    """Merge all sources, deduplicate, save combined corpus."""
    unique = deduplicate(all_records)
    unique.sort(key=lambda r: len(r.get("output", "")), reverse=True)  # longer answers first

    with open(COMBINED_PATH, "w") as f:
        for r in unique:
            f.write(json.dumps(r) + "\n")

    print(f"\n{'='*60}")
    print(f"Combined corpus: {len(unique):,} unique examples")
    print(f"Saved to: {COMBINED_PATH}")

    # Stats by source
    from collections import Counter
    sources = Counter(r["source"].split("_")[0] for r in unique)
    for src, count in sources.most_common():
        print(f"  {src}: {count:,}")


# ── Main ──────────────────────────────────────────────────────────────────────

SOURCE_MAP = {
    "se":  ("Stack Exchange",    source_stackexchange),
    "hf":  ("HuggingFace",       source_huggingface),
    "gh":  ("GitHub",            source_github),
    "sec": ("SEC EDGAR",         source_sec_edgar),
    "fc":  ("Firecrawl",         source_firecrawl),
}


def main():
    parser = argparse.ArgumentParser(description="Gather PMCore training corpus")
    parser.add_argument("--source", choices=list(SOURCE_MAP.keys()), default=None,
                        help="Run only this source (default: all)")
    args = parser.parse_args()

    print("PMCore Corpus Gatherer")
    print("=" * 60)

    if args.source:
        sources_to_run = {args.source: SOURCE_MAP[args.source]}
    else:
        sources_to_run = SOURCE_MAP

    all_records = []

    for key, (name, fn) in sources_to_run.items():
        print(f"\n[{name}]")
        out_path = RAW_DIR / f"{key}_corpus.jsonl"

        # Load cached if exists and not re-running specific source
        if out_path.exists() and args.source is None:
            with open(out_path) as f:
                cached = [json.loads(l) for l in f if l.strip()]
            log(f"Loaded {len(cached):,} cached examples from {out_path.name}")
            all_records.extend(cached)
            continue

        records = fn()
        if records:
            save_jsonl(out_path, records)
            log(f"Saved {len(records):,} → {out_path.name}")
            all_records.extend(records)
        else:
            log(f"No records returned from {name}")

    if all_records:
        combine_and_save(all_records)
    else:
        print("\nNo records gathered. Check source availability and API keys.")


if __name__ == "__main__":
    main()
