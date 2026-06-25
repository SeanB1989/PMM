"""
Scraper module for Vantage PMM Intelligence Tool
Real review content from Reddit, G2, Capterra, Product Hunt, and the open web.
"""

import requests
from bs4 import BeautifulSoup
import time
import re
import json
from urllib.parse import urljoin, urlparse, quote_plus

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

REDDIT_HEADERS = {
    "User-Agent": "VantagePMM/1.0 (market research tool; contact: user@example.com)",
    "Accept": "application/json",
}


# ─────────────────────────────────────────────
#  Utilities
# ─────────────────────────────────────────────

def clean_text(text):
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def safe_get(url, headers=None, timeout=12, retries=2):
    """HTTP GET with retries and polite delay."""
    h = headers or HEADERS
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=h, timeout=timeout)
            if resp.status_code == 200:
                return resp
            if resp.status_code in (403, 429):
                time.sleep(2 * (attempt + 1))
        except Exception:
            time.sleep(1)
    return None


def extract_text(resp, char_limit=6000):
    """Parse HTML response and return clean text."""
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header",
                     "aside", "form", "iframe", "noscript", "svg"]):
        tag.decompose()
    return clean_text(soup.get_text(separator=" "))[:char_limit]


# ─────────────────────────────────────────────
#  DuckDuckGo search
# ─────────────────────────────────────────────

def duckduckgo_search(query, max_results=8):
    results = []
    try:
        params = {"q": query, "kl": "us-en", "kp": "-2"}
        resp = safe_get("https://html.duckduckgo.com/html/", headers={**HEADERS, **{"Content-Type": "application/x-www-form-urlencoded"}})
        # POST is more reliable for DDG
        r = requests.post(
            "https://html.duckduckgo.com/html/",
            data=params,
            headers=HEADERS,
            timeout=15,
        )
        soup = BeautifulSoup(r.text, "html.parser")
        for result in soup.select(".result")[:max_results]:
            title_el = result.select_one(".result__title")
            snippet_el = result.select_one(".result__snippet")
            url_el = result.select_one(".result__url")
            href_el = result.select_one("a.result__a")
            title = title_el.get_text(strip=True) if title_el else ""
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            url = url_el.get_text(strip=True) if url_el else ""
            href = href_el.get("href", "") if href_el else ""
            if title or snippet:
                results.append({"title": title, "snippet": snippet, "url": url, "href": href})
    except Exception as e:
        results.append({"title": "Search error", "snippet": str(e), "url": "", "href": ""})
    return results


# ─────────────────────────────────────────────
#  Reddit — JSON API (no auth needed)
# ─────────────────────────────────────────────

def search_reddit(query, limit=8):
    """Search Reddit and return thread summaries with actual comment content."""
    results = []
    try:
        url = f"https://www.reddit.com/search.json?q={quote_plus(query)}&type=link&sort=relevance&limit={limit}&t=year"
        resp = safe_get(url, headers=REDDIT_HEADERS, timeout=15)
        if not resp:
            return results

        data = resp.json()
        posts = data.get("data", {}).get("children", [])

        for post in posts[:6]:
            p = post.get("data", {})
            title = p.get("title", "")
            selftext = p.get("selftext", "")[:800]
            subreddit = p.get("subreddit", "")
            score = p.get("score", 0)
            permalink = p.get("permalink", "")
            num_comments = p.get("num_comments", 0)

            # Fetch top comments for high-signal posts
            comments_text = ""
            if score > 5 and num_comments > 2 and permalink:
                comments_text = fetch_reddit_comments(permalink, max_comments=8)
                time.sleep(0.5)

            results.append({
                "platform": "Reddit",
                "subreddit": subreddit,
                "title": title,
                "body": selftext,
                "comments": comments_text,
                "score": score,
                "url": f"https://reddit.com{permalink}",
            })
    except Exception as e:
        results.append({"platform": "Reddit", "title": "Error", "body": str(e), "comments": "", "url": ""})

    return results


def fetch_reddit_comments(permalink, max_comments=8):
    """Fetch top comments from a Reddit thread."""
    try:
        url = f"https://www.reddit.com{permalink}.json?limit={max_comments}&sort=top"
        resp = safe_get(url, headers=REDDIT_HEADERS, timeout=12)
        if not resp:
            return ""

        data = resp.json()
        if len(data) < 2:
            return ""

        comments = []
        children = data[1].get("data", {}).get("children", [])
        for child in children[:max_comments]:
            c = child.get("data", {})
            body = c.get("body", "")
            score = c.get("score", 0)
            if body and body != "[deleted]" and body != "[removed]" and score > 0:
                comments.append(f"[+{score}] {body[:400]}")

        return "\n\n".join(comments)
    except Exception:
        return ""


def format_reddit_results(results):
    lines = []
    for r in results:
        lines.append(f"## r/{r.get('subreddit','reddit')} — {r.get('title','')}")
        if r.get("body"):
            lines.append(f"Post: {r['body']}")
        if r.get("comments"):
            lines.append(f"Top comments:\n{r['comments']}")
        lines.append(f"Source: {r.get('url','')}\n")
    return "\n".join(lines)


# ─────────────────────────────────────────────
#  G2 Reviews
# ─────────────────────────────────────────────

def scrape_g2_reviews(company_name):
    """Try to fetch actual G2 review content."""
    slug = company_name.lower().replace(" ", "-").replace(".", "")
    reviews_text = []

    # Try the pros/cons page — most content-dense
    urls_to_try = [
        f"https://www.g2.com/products/{slug}/reviews?qs=pros-and-cons",
        f"https://www.g2.com/products/{slug}/reviews",
    ]

    for url in urls_to_try:
        resp = safe_get(url, timeout=14)
        if resp and resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract individual review blocks
            review_blocks = soup.select("[itemprop='review'], .review-text, [data-paper-variant='padded']")
            for block in review_blocks[:15]:
                text = block.get_text(separator=" ", strip=True)
                if len(text) > 80:
                    reviews_text.append(clean_text(text)[:500])

            # Fallback: grab all paragraph-ish text
            if not review_blocks:
                paras = soup.select("p, .formatted-text")
                for p in paras[:20]:
                    t = p.get_text(strip=True)
                    if len(t) > 60:
                        reviews_text.append(clean_text(t)[:400])

            if reviews_text:
                break
        time.sleep(0.8)

    # Supplement with DDG search for review snippets
    search_results = duckduckgo_search(f"{company_name} reviews g2 pros cons what users say", max_results=5)
    for r in search_results:
        if r.get("snippet"):
            reviews_text.append(r["snippet"])

    return "\n\n".join(reviews_text) if reviews_text else f"[G2 review data unavailable for {company_name}]"


# ─────────────────────────────────────────────
#  Capterra Reviews
# ─────────────────────────────────────────────

def scrape_capterra_reviews(company_name):
    """Fetch Capterra review content."""
    slug = company_name.lower().replace(" ", "-")
    reviews_text = []

    url = f"https://www.capterra.com/p/search/?query={quote_plus(company_name)}"
    resp = safe_get(url, timeout=12)

    # Try direct search
    search_results = duckduckgo_search(
        f"{company_name} capterra reviews pros cons complaints", max_results=6
    )
    for r in search_results:
        if r.get("snippet") and len(r["snippet"]) > 50:
            reviews_text.append(r["snippet"])
        # Try fetching the actual Capterra page
        href = r.get("href", "")
        if href and "capterra.com" in href and len(reviews_text) < 8:
            page_resp = safe_get(href, timeout=12)
            if page_resp:
                soup = BeautifulSoup(page_resp.text, "html.parser")
                for block in soup.select(".review-text, p")[:10]:
                    t = block.get_text(strip=True)
                    if len(t) > 60:
                        reviews_text.append(clean_text(t)[:400])
            time.sleep(0.5)

    return "\n\n".join(reviews_text[:12]) if reviews_text else f"[Capterra data unavailable for {company_name}]"


# ─────────────────────────────────────────────
#  Product Hunt
# ─────────────────────────────────────────────

def scrape_product_hunt(company_name):
    """Search Product Hunt for reviews and discussions."""
    reviews_text = []

    # DDG search for Product Hunt content
    results = duckduckgo_search(
        f"{company_name} site:producthunt.com reviews", max_results=5
    )
    for r in results:
        if r.get("snippet"):
            reviews_text.append(r["snippet"])
        href = r.get("href", "")
        if href and "producthunt.com" in href:
            resp = safe_get(href, timeout=12)
            if resp:
                soup = BeautifulSoup(resp.text, "html.parser")
                for block in soup.select("p, [data-test='review-text']")[:10]:
                    t = block.get_text(strip=True)
                    if len(t) > 60:
                        reviews_text.append(clean_text(t)[:400])
            time.sleep(0.5)

    return "\n\n".join(reviews_text[:8]) if reviews_text else ""


# ─────────────────────────────────────────────
#  Trustpilot
# ─────────────────────────────────────────────

def scrape_trustpilot(company_name):
    """Try Trustpilot for consumer-facing companies."""
    results = duckduckgo_search(
        f"{company_name} trustpilot reviews", max_results=4
    )
    text = []
    for r in results:
        if r.get("snippet"):
            text.append(r["snippet"])
    return "\n\n".join(text) if text else ""


# ─────────────────────────────────────────────
#  Aggregated review intelligence
# ─────────────────────────────────────────────

def gather_review_intelligence(company_name, progress_cb=None):
    """
    Pull real review content from multiple sources for one company.
    Returns a structured dict of findings per platform.
    """
    def log(msg):
        if progress_cb:
            progress_cb(msg)

    findings = {"company": company_name, "sources": {}}

    log(f"  Reddit — searching threads about {company_name}...")
    reddit_data = search_reddit(f"{company_name} review experience pros cons")
    reddit_data += search_reddit(f"{company_name} problems complaints alternatives")
    findings["sources"]["reddit"] = format_reddit_results(reddit_data)

    log(f"  G2 — fetching reviews for {company_name}...")
    findings["sources"]["g2"] = scrape_g2_reviews(company_name)

    log(f"  Capterra — fetching reviews for {company_name}...")
    findings["sources"]["capterra"] = scrape_capterra_reviews(company_name)

    log(f"  Product Hunt — checking community feedback...")
    ph = scrape_product_hunt(company_name)
    if ph:
        findings["sources"]["product_hunt"] = ph

    log(f"  Trustpilot — checking general sentiment...")
    tp = scrape_trustpilot(company_name)
    if tp:
        findings["sources"]["trustpilot"] = tp

    return findings


def format_review_intelligence(all_findings):
    """Format multi-company review data for Claude."""
    output = []
    for company_findings in all_findings:
        name = company_findings["company"]
        output.append(f"\n{'='*60}")
        output.append(f"CUSTOMER VOICE: {name}")
        output.append(f"{'='*60}\n")
        for platform, content in company_findings["sources"].items():
            if content and "[unavailable]" not in content:
                output.append(f"--- {platform.upper()} ---")
                output.append(content[:3000])
                output.append("")
    return "\n".join(output)


# ─────────────────────────────────────────────
#  Competitor site scraping
# ─────────────────────────────────────────────

def find_subpages(base_url, keywords=("pricing", "features", "product", "solutions", "why", "platform")):
    pages = [base_url]
    try:
        resp = safe_get(base_url, timeout=12)
        if not resp:
            return pages
        soup = BeautifulSoup(resp.text, "html.parser")
        domain = urlparse(base_url).netloc
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            full = urljoin(base_url, a["href"])
            if urlparse(full).netloc == domain:
                if any(kw in href for kw in keywords):
                    if full not in pages:
                        pages.append(full)
                        if len(pages) >= 5:
                            break
    except Exception:
        pass
    return pages[:5]


def scrape_competitor(name, url):
    result = {"name": name, "url": url, "pages": {}}
    pages = find_subpages(url)
    labels = ["homepage", "subpage_1", "subpage_2", "subpage_3", "subpage_4"]
    for label, page_url in zip(labels, pages):
        resp = safe_get(page_url, timeout=12)
        if resp:
            result["pages"][label] = {"url": page_url, "content": extract_text(resp)}
        time.sleep(0.5)
    return result


def format_competitor_content(competitor_data):
    lines = [f"=== {competitor_data['name']} ({competitor_data['url']}) ===\n"]
    for label, page in competitor_data["pages"].items():
        lines.append(f"--- {label.upper()} ({page['url']}) ---")
        lines.append(page["content"][:3000])
        lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────────
#  Market intelligence
# ─────────────────────────────────────────────

def search_market_intel(product_description, target_market, progress_cb=None):
    """Deep market signal gathering: buyer discussions, trends, pain points."""
    def log(msg):
        if progress_cb:
            progress_cb(msg)

    results = []

    queries = [
        f"{target_market} biggest challenges pain points 2024 2025",
        f"{target_market} software buying criteria what matters most",
        f"{product_description} market trends analyst report",
        f"{target_market} what tools are you using reddit forum",
        f"best {product_description} for {target_market} comparison",
        f"{target_market} switching from OR replaced OR frustrated",
    ]

    log("  Searching market discussions and analyst content...")
    for q in queries:
        hits = duckduckgo_search(q, max_results=5)
        results.extend(hits)
        time.sleep(0.4)

    # Also pull Reddit market discussions
    log("  Pulling Reddit market discussions...")
    reddit_market = search_reddit(f"{target_market} {product_description} recommendations", limit=6)
    reddit_market += search_reddit(f"{target_market} pain points challenges tools", limit=6)

    reddit_text = format_reddit_results(reddit_market)
    market_text = format_search_results(results)

    return market_text + "\n\n=== REDDIT MARKET DISCUSSIONS ===\n" + reddit_text


def format_search_results(results):
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
        if r.get("url"):
            lines.append(f"   {r['url']}")
        lines.append("")
    return "\n".join(lines)
