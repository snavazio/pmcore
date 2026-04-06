"""
Retry blocked hospitality sites with aggressive Firecrawl options.
Uses stealth mode + longer wait times + specific known article URLs
instead of crawling index pages (which trip bot detection faster).
"""

import os, json, time, requests
from pathlib import Path

FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
RAW_DIR = Path("./corpus/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

headers = {
    "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
    "Content-Type": "application/json",
}

PM_KEYWORDS = [
    "project", "plan", "renovation", "capital", "investment", "hotel",
    "construction", "budget", "timeline", "management", "strategy",
    "revenue", "reit", "asset", "property", "development", "market",
]

def log(msg): print(f"  {msg}", flush=True)


def scrape_page(url: str, label: str) -> dict | None:
    """Scrape a single page with stealth options."""
    try:
        r = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers=headers,
            json={
                "url": url,
                "formats": ["markdown"],
                "onlyMainContent": True,
                "waitFor": 4000,           # Wait 4s for JS to render
                "mobile": False,
                "skipTlsVerification": False,
                "timeout": 30000,
                "actions": [
                    {"type": "wait", "milliseconds": 2000},
                    {"type": "scroll", "direction": "down", "amount": 500},
                ],
            },
            timeout=60,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("success"):
                return data.get("data", {})
        log(f"  Scrape failed {r.status_code}: {r.text[:150]}")
    except Exception as e:
        log(f"  Exception: {e}")
    return None


def crawl_site(url: str, limit: int, label: str) -> list:
    """Crawl with stealth + JS rendering options."""
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
                    "waitFor": 3000,
                    "excludeTags": ["nav","footer","header","aside","script","style","form","iframe"],
                },
                "excludePaths": ["/tag/","/author/","/search","/login","/register","/subscribe","/cart"],
                "allowBackwardLinks": False,
                "allowExternalLinks": False,
            },
            timeout=30,
        )
        if r.status_code != 200:
            log(f"  Crawl start failed {r.status_code}: {r.text[:150]}")
            return []

        crawl_id = r.json().get("id", "")
        log(f"  Crawl ID: {crawl_id}")

        for attempt in range(60):
            time.sleep(6)
            sr = requests.get(
                f"https://api.firecrawl.dev/v1/crawl/{crawl_id}",
                headers=headers, timeout=20
            )
            if sr.status_code != 200: break
            status = sr.json()
            crawl_status = status.get("status","")
            completed    = status.get("completed", 0)
            if attempt % 5 == 0:
                log(f"  {crawl_status}: {completed} pages")
            if crawl_status == "completed":
                return status.get("data", [])
            if crawl_status in ["failed","cancelled"]:
                log(f"  Crawl {crawl_status}")
                break
    except Exception as e:
        log(f"  Crawl exception: {e}")
    return []


def pages_to_records(pages: list, source_label: str) -> list[dict]:
    records = []
    for page in pages:
        content = page.get("markdown","") or page.get("content","") or ""
        title   = (page.get("metadata") or {}).get("title","") or ""
        url     = page.get("url","")

        kw_hits = sum(1 for kw in PM_KEYWORDS if kw in content.lower())
        if kw_hits < 2 or len(content) < 200:
            continue

        # Split into chunks
        paragraphs = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 80]
        chunk = ""
        for para in paragraphs:
            if len(chunk) + len(para) > 1200 and chunk:
                records.append({
                    "source": f"fc_{source_label}",
                    "input": f"What are the latest trends and insights in hotel and hospitality project management? (Source: {title})",
                    "output": chunk.strip(),
                    "url": url,
                    "format": "article",
                })
                chunk = para
            else:
                chunk = (chunk + "\n\n" + para).strip()
        if chunk and len(chunk) > 100:
            records.append({
                "source": f"fc_{source_label}",
                "input": f"Summarize key hospitality industry insights for project managers. (Source: {title})",
                "output": chunk.strip(),
                "url": url,
                "format": "article",
            })
    return records


# ── Site-specific strategies ──────────────────────────────────────────────────

def try_hvs():
    """HVS - hotel valuation & consulting firm. Try known article sections."""
    log("HVS: Trying direct article pages...")
    records = []

    # HVS publishes reports at predictable URLs
    hvs_urls = [
        "https://www.hvs.com/article/hospitality-industry",
        "https://www.hvs.com/article/hotel-development",
        "https://www.hvs.com/article/hotel-management",
        "https://www.hvs.com/article/hotel-investment",
        "https://www.hvs.com/article/capital-expenditure",
        "https://www.hvs.com/content/3247.pdf",  # Hotel Development Cost Survey
        "https://www.hvs.com/content/3559.pdf",  # Hotel Cap Ex study
    ]

    for url in hvs_urls:
        page = scrape_page(url, "hvs")
        if page:
            content = page.get("markdown","") or ""
            if len(content) > 200:
                log(f"  Got content from {url}: {len(content)} chars")
                records.extend(pages_to_records([page], "hvs"))
        time.sleep(2)

    # Also try crawling the reports section with a lower limit
    if len(records) < 5:
        log("  Trying crawl of hvs.com/article...")
        pages = crawl_site("https://www.hvs.com/article", 30, "hvs")
        records.extend(pages_to_records(pages, "hvs"))

    log(f"  HVS total: {len(records)} chunks")
    return records


def try_str():
    """STR - hotel performance data company."""
    log("STR: Trying press releases and reports...")
    records = []

    str_urls = [
        "https://str.com/press-release",
        "https://str.com/data-insights-hub",
        "https://str.com/media-resources",
        "https://str.com/us-hotel-industry-performance",
        "https://str.com/blog",
    ]

    # Try crawling main content sections
    for url in str_urls[:2]:
        pages = crawl_site(url, 20, "str")
        if pages:
            records.extend(pages_to_records(pages, "str"))
            if records:
                break
        time.sleep(3)

    # Try individual page scrapes
    if not records:
        for url in str_urls[2:]:
            page = scrape_page(url, "str")
            if page:
                content = page.get("markdown","") or ""
                if len(content) > 200:
                    records.extend(pages_to_records([page], "str"))
            time.sleep(2)

    log(f"  STR total: {len(records)} chunks")
    return records


def try_globest():
    """GlobeSt - commercial real estate news."""
    log("GlobeSt: Trying hotel and hospitality sections...")
    records = []

    globest_urls = [
        "https://www.globest.com/hotels",
        "https://www.globest.com/category/hotels",
        "https://www.globest.com/2025/",
        "https://www.globest.com/2024/",
    ]

    for url in globest_urls:
        pages = crawl_site(url, 25, "globest")
        if pages:
            recs = pages_to_records(pages, "globest")
            records.extend(recs)
            if len(records) > 20:
                break
        time.sleep(3)

    log(f"  GlobeSt total: {len(records)} chunks")
    return records


def try_hospitalitynet():
    """Hospitalitynet - hotel industry news and analysis."""
    log("HospitalityNet: Trying specific news categories...")
    records = []

    # Try different URL patterns
    hnet_urls = [
        "https://www.hospitalitynet.org/news/4hotel_investment",
        "https://www.hospitalitynet.org/opinion/",
        "https://www.hospitalitynet.org/news/",
        "https://www.hospitalitynet.org/file/",         # white papers
        "https://www.hospitalitynet.org/news/4technology",
        "https://www.hospitalitynet.org/news/4renovation",
    ]

    for url in hnet_urls:
        page = scrape_page(url, "hospitalitynet")
        if page:
            content = page.get("markdown","") or ""
            if len(content) > 300:
                log(f"  Got {len(content)} chars from {url}")
                records.extend(pages_to_records([page], "hospitalitynet"))
        time.sleep(2)

    # Try crawl if scrape worked
    if len(records) > 0:
        pages = crawl_site("https://www.hospitalitynet.org/news", 40, "hospitalitynet")
        records.extend(pages_to_records(pages, "hospitalitynet"))

    log(f"  HospitalityNet total: {len(records)} chunks")
    return records


# ── Also retry some good PM sites that returned 0 pages ──────────────────────

def try_bonus_sites():
    """A few more quality PM sites worth trying with the right approach."""
    records = []

    bonus = [
        ("https://www.mpug.com/articles", 40, "mpug"),
        ("https://www.girlsguidetopm.com/blog", 40, "girlsguidepm"),
        ("https://www.projectsmart.co.uk/articles.php", 30, "projectsmart"),
        ("https://hbr.org/topic/subject/project-management", 30, "hbr_pm"),
        ("https://www.mckinsey.com/capabilities/operations/our-insights", 30, "mckinsey_ops"),
        ("https://www.pwc.com/gx/en/industries/hospitality-leisure.html", 20, "pwc_hospitality"),
        ("https://www2.deloitte.com/us/en/pages/consumer-business/topics/hospitality-and-leisure.html", 20, "deloitte_hospitality"),
    ]

    for url, limit, label in bonus:
        log(f"Trying {label}...")
        pages = crawl_site(url, limit, label)
        recs = pages_to_records(pages, label)
        if recs:
            log(f"  {label}: {len(recs)} chunks from {len(pages)} pages")
            records.extend(recs)
        else:
            # Try single page scrape as fallback
            page = scrape_page(url, label)
            if page:
                recs = pages_to_records([page], label)
                if recs:
                    log(f"  {label}: {len(recs)} chunks (single page)")
                    records.extend(recs)
        time.sleep(3)

    return records


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not FIRECRAWL_API_KEY:
        print("ERROR: FIRECRAWL_API_KEY not set")
        exit(1)

    print("PMCore — Retrying blocked sites + bonus targets")
    print("=" * 60)

    all_new = []

    print("\n[HVS]")
    all_new.extend(try_hvs())

    print("\n[STR]")
    all_new.extend(try_str())

    print("\n[GlobeSt]")
    all_new.extend(try_globest())

    print("\n[HospitalityNet]")
    all_new.extend(try_hospitalitynet())

    print("\n[Bonus PM + Consulting Sites]")
    all_new.extend(try_bonus_sites())

    # Save new records
    out_path = RAW_DIR / "retry_corpus.jsonl"
    with open(out_path, "w") as f:
        for r in all_new:
            f.write(json.dumps(r) + "\n")

    print(f"\n{'='*60}")
    print(f"New records gathered: {len(all_new):,}")
    print(f"Saved to: {out_path}")

    # Merge into combined_v2
    combined_path = Path("./corpus/combined_v2.jsonl")
    existing = []
    if combined_path.exists():
        with open(combined_path) as f:
            existing = [json.loads(l) for l in f if l.strip()]

    # Deduplicate
    seen = set()
    merged = []
    for r in existing + all_new:
        key = __import__('hashlib').md5(r.get("input","")[:200].lower().encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            merged.append(r)

    with open(combined_path, "w") as f:
        for r in merged:
            f.write(json.dumps(r) + "\n")

    print(f"Combined v2 total: {len(merged):,} unique examples")

    from collections import Counter
    sources = Counter(r["source"].split("_")[0] for r in merged)
    for src, count in sources.most_common():
        print(f"  {src:25s}: {count:,}")
