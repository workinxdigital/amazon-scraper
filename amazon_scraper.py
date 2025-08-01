#!/usr/bin/env python3
import json, logging, random, re, time
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# ─── CONFIG ────────────────────────────────────────────────────────────────────
PROXY_HOST = "gate.decodo.com"
PROXY_PORTS = [10001, 10002, 10003, 10004, 10005, 10006, 10007]
USERNAME = "spbb3v1soa"
PASSWORD = "=rY9v15mUg2AkrbEbk"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

PRICE_SELECTORS = [
    ".a-price .a-offscreen", "#priceblock_ourprice", "#priceblock_dealprice",
    "#priceblock_saleprice", "#priceblock_businessprice", "#priceblock_pospromoprice",
]

# ─── HELPERS ───────────────────────────────────────────────────────────────────
def get_proxy_url():
    port = random.choice(PROXY_PORTS)
    return f"http://{USERNAME}:{PASSWORD}@{PROXY_HOST}:{port}"

def get_text(el):
    return el.get_text(strip=True) if el else None

def extract_asin(url_or_asin):
    if re.match(r"^[A-Z0-9]{10}$", url_or_asin):
        return url_or_asin
    for pattern in [
        r"/dp/([A-Z0-9]{10})", r"/gp/product/([A-Z0-9]{10})",
        r"/product-reviews/([A-Z0-9]{10})", r"/([A-Z0-9]{10})(?:[/?]|$)"
    ]:
        m = re.search(pattern, url_or_asin)
        if m:
            return m.group(1)
    return None

def normalize_url(asin_or_url):
    asin = extract_asin(asin_or_url)
    if not asin:
        raise ValueError("Could not extract ASIN from input.")
    return f"https://www.amazon.com/dp/{asin}", asin

# ─── FETCHERS ──────────────────────────────────────────────────────────────────
def fetch_static(url):
    try:
        headers = {
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": url,
            "User-Agent": random.choice(USER_AGENTS)
        }
        proxies = {"http": get_proxy_url(), "https": get_proxy_url()}
        resp = requests.get(url, headers=headers, proxies=proxies, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logging.warning("Static fetch failed for %s: %s", url, e)
        return None

def fetch_full_page(url):
    driver = None
    try:
        opts = Options()
        opts.add_argument(f"--proxy-server={get_proxy_url()}")
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
        driver = webdriver.Chrome(options=opts)
        driver.get(url)
        time.sleep(2)
        last_h = driver.execute_script("return document.body.scrollHeight")
        while True:
            driver.execute_script("window.scrollTo(0,document.body.scrollHeight);")
            time.sleep(1)
            new_h = driver.execute_script("return document.body.scrollHeight")
            if new_h == last_h:
                break
            last_h = new_h
        html = driver.page_source
        driver.quit()
        return html
    except Exception as e:
        logging.warning("Full-page fetch failed for %s: %s", url, e)
        if driver:
            driver.quit()
        return None

# ─── PARSERS ───────────────────────────────────────────────────────────────────
def parse_listing(soup): return {"title": get_text(soup.select_one("#productTitle"))}
def parse_brand(soup): return {"brand": get_text(soup.select_one("#bylineInfo"))}

def parse_price(soup):
    price_str = next((get_text(soup.select_one(sel)) for sel in PRICE_SELECTORS if get_text(soup.select_one(sel))), None)
    value, currency = None, None
    if price_str:
        m = re.match(r"([$\£₹€])\s*([\d,]+\.?\d*)", price_str)
        if m:
            currency, value = m.group(1), float(m.group(2).replace(",", ""))
    return {"price": {"value": value, "currency": currency}}

def parse_rating(soup):
    txt = get_text(soup.select_one("i.a-icon-star span.a-icon-alt"))
    return {"rating": float(txt.split()[0]) if txt else None}

def parse_review_count(soup):
    rc = get_text(soup.select_one("#acrCustomerReviewText"))
    return {"review_count": int(rc.split()[0].replace(",", "")) if rc else 0}

def parse_images(soup):
    thumb = soup.select_one("#landingImage")
    gallery = [img.get("src") or img.get("data-src") for img in soup.select("#altImages img") if img.get("src") or img.get("data-src")]
    return {
        "thumbnail": thumb["src"] if thumb else None,
        "images": gallery
    }

def parse_features(soup):
    feats = [get_text(li) for li in soup.select("#feature-bullets li") if get_text(li)]
    return {"features": feats}

def parse_top_review(soup):
    top_review = soup.select_one("div[data-hook='review']")
    if not top_review:
        return {"review": None}
    return {
        "review": {
            "title": get_text(top_review.select_one("a[data-hook='review-title'] span")),
            "rating": get_text(top_review.select_one("i[data-hook='review-star-rating'] span")),
            "content": get_text(top_review.select_one("span[data-hook='review-body'] span"))
        }
    }

# ─── FINAL WRAPPER ─────────────────────────────────────────────────────────────
def scrape_product(url):
    html = fetch_static(url) or fetch_full_page(url)
    if not html:
        raise Exception("Failed to load page")
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "url": url,
        **parse_listing(soup),
        **parse_brand(soup),
        **parse_price(soup),
        **parse_rating(soup),
        **parse_review_count(soup),
        **parse_images(soup),
        **parse_features(soup),
        **parse_top_review(soup)
    }
    return result

def to_openai_payload(scraped, asin):
    return {
        "asin": asin,
        "url": scraped.get("url"),
        "title": scraped.get("title"),
        "brand": scraped.get("brand"),
        "price": scraped.get("price", {}).get("value"),
        "currency": scraped.get("price", {}).get("currency"),
        "features": scraped.get("features"),
        "description": (scraped.get("review") or {}).get("content"),  # Fallback
        "images": scraped.get("images", []),
        "thumbnail": scraped.get("thumbnail"),
        "rating": scraped.get("rating"),
        "review_count": scraped.get("review_count"),
        "review_summary": scraped.get("review", {})
    }

# ─── SERVICE CLASS ─────────────────────────────────────────────────────────────
class AmazonScraperService:
    def scrape_amazon_product(self, asin_or_url):
        url, asin = normalize_url(asin_or_url)
        raw = scrape_product(url)
        return to_openai_payload(raw, asin)

# Example usage
# scraper = AmazonScraperService()
# data = scraper.scrape_amazon_product("B09XXXXXXX")
# print(json.dumps(data, indent=2))
