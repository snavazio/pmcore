"""
PMCore — Targeted Deloitte + Premium Hospitality Research Scrape
=================================================================
Now that we have exact URLs from search, we hit them directly
instead of crawling — much more reliable against bot detection.

Sources:
  - Deloitte: 2026 Travel Outlook, AI in Hospitality, European Hotel Survey,
               Future of Hospitality, all Insights articles
  - CBRE: Hotel Investor Intentions Survey, Operating Costs report
  - Lodging Econometrics: Hotel Development Pipeline reports
  - Hospitality Investor: capex articles
  - Matthews: Hotel Development Trends
  - Horwath HTL: Hotel market reports (PDF)
  - 2024 Deloitte Travel PDF (direct)
"""

import os, json, time, requests, hashlib
from pathlib import Path

FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
RAW_DIR  = Path("./corpus/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

headers = {
    "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
    "Content-Type": "application/json",
}

PM_KEYWORDS = [
    "project", "capital", "renovation", "investment", "hotel", "construction",
    "budget", "timeline", "management", "strategy", "revenue", "reit",
    "asset", "property", "development", "market", "technology", "ai",
    "workforce", "operations", "cost", "schedule", "plan", "implementation",
    "transformation", "digital", "infrastructure", "capex", "pipeline",
]

def log(msg): print(f"  {msg}", flush=True)


def scrape_url(url: str, wait_ms: int = 3000) -> dict | None:
    """Scrape a single URL via Firecrawl."""
    try:
        r = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers=headers,
            json={
                "url": url,
                "formats": ["markdown"],
                "onlyMainContent": True,
                "waitFor": wait_ms,
                "timeout": 45000,
                "actions": [
                    {"type": "wait", "milliseconds": 2000},
                    {"type": "scroll", "direction": "down", "amount": 800},
                    {"type": "wait", "milliseconds": 1000},
                ],
            },
            timeout=90,
        )
        if r.status_code == 200 and r.json().get("success"):
            return r.json().get("data", {})
        log(f"    HTTP {r.status_code}: {r.text[:120]}")
    except Exception as e:
        log(f"    Exception: {e}")
    return None


def crawl_site(url: str, limit: int) -> list:
    """Crawl a site section."""
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
                    "excludeTags": ["nav","footer","header","aside","script","style","form"],
                },
                "excludePaths": ["/login","/subscribe","/cart","/register","/search","/tag/"],
            },
            timeout=30,
        )
        if r.status_code != 200:
            log(f"    Crawl start failed: {r.status_code}")
            return []

        crawl_id = r.json().get("id","")
        for attempt in range(90):
            time.sleep(6)
            sr = requests.get(
                f"https://api.firecrawl.dev/v1/crawl/{crawl_id}",
                headers=headers, timeout=20
            )
            if sr.status_code != 200: break
            status = sr.json()
            if attempt % 5 == 0:
                log(f"    {status.get('status','?')}: {status.get('completed',0)} pages")
            if status.get("status") == "completed":
                return status.get("data", [])
            if status.get("status") in ["failed","cancelled"]:
                break
    except Exception as e:
        log(f"    Crawl exception: {e}")
    return []


def content_to_records(content: str, title: str, url: str, source_label: str, topic: str) -> list[dict]:
    """Convert scraped content to PMCore training records."""
    if not content or len(content) < 200:
        return []

    kw_hits = sum(1 for kw in PM_KEYWORDS if kw in content.lower())
    if kw_hits < 2:
        return []

    # Split into meaningful chunks
    paragraphs = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 80]
    records, chunk = [], ""

    for para in paragraphs:
        if len(chunk) + len(para) > 1400 and chunk:
            records.append(_make_record(chunk, title, url, source_label, topic))
            chunk = para
        else:
            chunk = (chunk + "\n\n" + para).strip()
    if chunk and len(chunk) > 100:
        records.append(_make_record(chunk, title, url, source_label, topic))

    return records


def _make_record(chunk: str, title: str, url: str, source: str, topic: str) -> dict:
    questions = {
        "deloitte_travel":      "What are the key strategic trends shaping the travel and hospitality industry?",
        "deloitte_ai":          "How is AI transforming hospitality operations and project management?",
        "deloitte_european":    "What do European hotel investors prioritize in capital allocation and project selection?",
        "deloitte_future":      "What does the future of hospitality look like from a strategic and operational perspective?",
        "deloitte_insights":    "What are Deloitte's strategic insights for hospitality industry leaders?",
        "cbre_hotel":           "What are the latest hotel investment and capital expenditure trends according to CBRE?",
        "cbre_costs":           "How are operating costs and capital expenditures trending in the hotel industry?",
        "lodging_econ":         "What is the current hotel development pipeline and construction outlook?",
        "hospitality_investor": "What do hotel investors think about capital expenditure and renovation in 2025?",
        "matthews_hotel":       "What are the development trends and strategic shifts in the hotel industry?",
        "horwath":              "What are the key hotel market metrics and investment insights?",
    }
    q = questions.get(source, f"What are the key insights about {topic}?")
    return {
        "source": f"fc_{source}",
        "input": q,
        "output": chunk,
        "url": url,
        "title": title,
        "format": "research_report",
    }


def pages_to_records(pages: list, source_label: str, topic: str) -> list[dict]:
    records = []
    for page in pages:
        content = page.get("markdown","") or ""
        title   = (page.get("metadata") or {}).get("title","") or ""
        url     = page.get("url","")
        records.extend(content_to_records(content, title, url, source_label, topic))
    return records


# ── Deloitte ──────────────────────────────────────────────────────────────────

DELOITTE_URLS = [
    # Direct article URLs we found from search
    ("https://www.deloitte.com/us/en/insights/industry/transportation/travel-hospitality-industry-outlook.html",
     "2026 Travel Industry Outlook"),
    ("https://www.deloitte.com/us/en/Industries/consumer/articles/travel-hospitality-industry-outlook.html",
     "2025 Travel Industry Outlook"),
    ("https://www.deloitte.com/us/en/Industries/consumer/articles/future-of-hospitality-ai-innovation.html",
     "Future of Hospitality: AI Innovation"),
    ("https://www.deloitte.com/uk/en/Industries/consumer/research/european-hotel-industry-and-investment-survey-2024.html",
     "European Hotel Industry & Investment Survey 2024"),
    ("https://www2.deloitte.com/uk/en/blog/consumer-business/2024/the-hospitality-guest-of-the-future.html",
     "Hospitality Guest of the Future"),
    ("https://www.deloitte.com/us/en/Industries/consumer/about/hospitality-perspectives-insights-analysis.html",
     "Deloitte Hospitality Hub"),
    ("https://www.deloitte.com/nl/en/Industries/transportation/research/european-hotel-industry-and-investment-survey-2024.html",
     "European Hotel Survey (Netherlands)"),
    # PDF — direct download
    ("https://www2.deloitte.com/content/dam/Deloitte/us/Documents/consumer-business/us-travel-hospitality-industry-outlook-2024.pdf",
     "2024 Travel Hospitality Outlook PDF"),
    # Broader Deloitte insights hub — crawl for more
]

DELOITTE_CRAWL_SECTIONS = [
    ("https://www.deloitte.com/us/en/Industries/consumer/about/hospitality-perspectives-insights-analysis.html", 40),
    ("https://www2.deloitte.com/us/en/pages/consumer-business/topics/hospitality-and-leisure.html", 40),
    ("https://www.deloitte.com/us/en/insights/industry/transportation.html", 30),
]


def get_deloitte() -> list[dict]:
    records = []
    log("Scraping known Deloitte article URLs directly...")

    for url, title in DELOITTE_URLS:
        log(f"  → {title}")
        page = scrape_url(url, wait_ms=5000)  # Extra wait for Deloitte JS
        if page:
            content = page.get("markdown","") or ""
            log(f"    {len(content):,} chars")
            recs = content_to_records(content, title, url, "deloitte_insights", "hospitality strategy")
            records.extend(recs)
            log(f"    → {len(recs)} training chunks")
        else:
            log(f"    No content returned")
        time.sleep(3)

    # Also crawl Deloitte's hospitality section for additional articles
    log("Crawling Deloitte hospitality section...")
    for crawl_url, limit in DELOITTE_CRAWL_SECTIONS:
        pages = crawl_site(crawl_url, limit)
        if pages:
            recs = pages_to_records(pages, "deloitte_insights", "hospitality strategy")
            log(f"  Crawl {crawl_url.split('/')[-1]}: {len(pages)} pages → {len(recs)} chunks")
            records.extend(recs)
        time.sleep(2)

    log(f"Deloitte total: {len(records)} chunks")
    return records


# ── CBRE ──────────────────────────────────────────────────────────────────────

CBRE_URLS = [
    ("https://www.cbre.com/insights/reports/global-hotel-investor-intentions-survey-2024",
     "Global Hotel Investor Intentions Survey 2024", "cbre_hotel"),
    ("https://www.cbre.com/insights/articles/all-eyes-on-operating-costs-in-2025-lessons-learned-in-2024",
     "All Eyes on Operating Costs 2025", "cbre_costs"),
    ("https://www.cbre.com/insights/reports/us-hotel-investor-intentions-survey",
     "US Hotel Investor Intentions Survey", "cbre_hotel"),
    ("https://www.cbre.com/insights/figures/hotel-horizons",
     "Hotel Horizons Outlook", "cbre_hotel"),
]

def get_cbre() -> list[dict]:
    records = []
    log("Scraping CBRE hotel research...")
    for url, title, label in CBRE_URLS:
        log(f"  → {title}")
        page = scrape_url(url, wait_ms=4000)
        if page:
            content = page.get("markdown","") or ""
            log(f"    {len(content):,} chars")
            recs = content_to_records(content, title, url, label, "hotel investment")
            records.extend(recs)
            log(f"    → {len(recs)} chunks")
        time.sleep(3)

    # Crawl CBRE hotel insights
    pages = crawl_site("https://www.cbre.com/insights/figures/hotel", 30)
    recs = pages_to_records(pages, "cbre_hotel", "hotel investment")
    log(f"  CBRE crawl: {len(pages)} pages → {len(recs)} chunks")
    records.extend(recs)

    log(f"CBRE total: {len(records)} chunks")
    return records


# ── Lodging Econometrics ──────────────────────────────────────────────────────

LODGING_ECON_URLS = [
    ("https://lodgingeconometrics.com/u-s-hotel-development-trends-projections-spring-2025/",
     "US Hotel Development Trends Spring 2025"),
    ("https://lodgingeconometrics.com/u-s-hotel-development-trends-projections-winter-2024/",
     "US Hotel Development Trends Winter 2024"),
    ("https://lodgingeconometrics.com/press-releases/",
     "Lodging Econometrics Press Releases"),
]

def get_lodging_econ() -> list[dict]:
    records = []
    log("Scraping Lodging Econometrics...")
    for url, title in LODGING_ECON_URLS[:2]:
        log(f"  → {title}")
        page = scrape_url(url)
        if page:
            content = page.get("markdown","") or ""
            log(f"    {len(content):,} chars")
            recs = content_to_records(content, title, url, "lodging_econ", "hotel development pipeline")
            records.extend(recs)
            log(f"    → {len(recs)} chunks")
        time.sleep(2)

    pages = crawl_site("https://lodgingeconometrics.com/press-releases/", 25)
    records.extend(pages_to_records(pages, "lodging_econ", "hotel development pipeline"))
    log(f"Lodging Econ total: {len(records)} chunks")
    return records


# ── Hospitality Investor ──────────────────────────────────────────────────────

def get_hospitality_investor() -> list[dict]:
    records = []
    log("Scraping Hospitality Investor (capex focus)...")

    urls = [
        ("https://www.hospitalityinvestor.com/investment/what-hotel-investors-think-about-capex-2025",
         "What Hotel Investors Think About Capex 2025"),
        ("https://www.hospitalityinvestor.com/investment", "Hotel Investment"),
        ("https://www.hospitalityinvestor.com/development", "Hotel Development"),
    ]

    for url, title in urls:
        log(f"  → {title}")
        page = scrape_url(url)
        if page:
            content = page.get("markdown","") or ""
            log(f"    {len(content):,} chars")
            recs = content_to_records(content, title, url, "hospitality_investor", "hotel capex")
            records.extend(recs)
        time.sleep(2)

    # Crawl
    pages = crawl_site("https://www.hospitalityinvestor.com/investment", 30)
    records.extend(pages_to_records(pages, "hospitality_investor", "hotel investment capex"))
    log(f"Hospitality Investor total: {len(records)} chunks")
    return records


# ── Matthews + Other ──────────────────────────────────────────────────────────

def get_bonus_research() -> list[dict]:
    records = []

    targets = [
        ("https://www.matthews.com/market_insights/hotel-deep-dive-into-development-trends-and-strategic-shifts",
         "matthews_hotel", "Hotel Deep Dive Development Trends", "hotel development"),
        ("https://www.matthews.com/hotel-deep-dive-into-development-trends-and-strategic-shifts/",
         "matthews_hotel", "Hotel Development Strategic Shifts", "hotel development"),
        ("https://horwathhtl.com/publication/",
         "horwath", "Horwath HTL Publications", "hotel consulting"),
        ("https://www.jll.com/en/industries/hotels-and-hospitality",
         "jll_hospitality", "JLL Hotel Hospitality", "hotel investment"),
        ("https://www.cushmanwakefield.com/en/insights/hotels",
         "cushman_hotels", "Cushman Wakefield Hotels", "hotel investment"),
        ("https://www.pwc.com/gx/en/industries/hospitality-leisure/hospitality-outlook.html",
         "pwc_hospitality", "PwC Hospitality Outlook", "hospitality strategy"),
        ("https://www2.deloitte.com/us/en/insights/focus/human-capital-trends.html",
         "deloitte_hc", "Deloitte Human Capital Trends", "workforce management"),
        ("https://kpmg.com/us/en/articles/2024/hotel-industry-trends.html",
         "kpmg_hotel", "KPMG Hotel Industry Trends", "hotel strategy"),
    ]

    log("Scraping bonus research sources...")
    for url, label, title, topic in targets:
        log(f"  → {title}")
        page = scrape_url(url, wait_ms=4000)
        if page:
            content = page.get("markdown","") or ""
            if len(content) > 300:
                log(f"    {len(content):,} chars")
                recs = content_to_records(content, title, url, label, topic)
                records.extend(recs)
                log(f"    → {len(recs)} chunks")
            else:
                log(f"    Too short ({len(content)} chars)")
        time.sleep(3)

    log(f"Bonus research total: {len(records)} chunks")
    return records


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not FIRECRAWL_API_KEY:
        print("ERROR: FIRECRAWL_API_KEY not set. Run: source ~/.pmcore_env")
        exit(1)

    print("PMCore — Deloitte + Premium Hospitality Research")
    print("=" * 60)

    all_new = []

    print("\n[Deloitte Hospitality — Full Coverage]")
    all_new.extend(get_deloitte())

    print("\n[CBRE Hotel Research]")
    all_new.extend(get_cbre())

    print("\n[Lodging Econometrics — Pipeline Data]")
    all_new.extend(get_lodging_econ())

    print("\n[Hospitality Investor — CapEx Focus]")
    all_new.extend(get_hospitality_investor())

    print("\n[JLL, Cushman, PwC, KPMG, Matthews, Horwath]")
    all_new.extend(get_bonus_research())

    # Save
    out_path = RAW_DIR / "deloitte_premium_corpus.jsonl"
    with open(out_path, "w") as f:
        for r in all_new:
            f.write(json.dumps(r) + "\n")

    print(f"\n{'='*60}")
    print(f"New records: {len(all_new):,}")
    print(f"Saved to: {out_path}")

    # Merge into combined
    combined_path = Path("./corpus/combined_v2.jsonl")
    existing = []
    if combined_path.exists():
        with open(combined_path) as f:
            existing = [json.loads(l) for l in f if l.strip()]

    seen, merged = set(), []
    for r in existing + all_new:
        key = hashlib.md5(r.get("input","")[:200].lower().encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            merged.append(r)

    with open(combined_path, "w") as f:
        for r in merged:
            f.write(json.dumps(r) + "\n")

    print(f"Combined total: {len(merged):,} unique examples")

    from collections import Counter
    sources = Counter(r["source"].split("_")[0] for r in merged)
    for src, count in sources.most_common():
        print(f"  {src:25s}: {count:,}")
