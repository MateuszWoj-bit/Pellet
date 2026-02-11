#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pylint: disable=invalid-name
"""Track pellet prices from target shop pages and persist snapshots."""

from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ================= CONFIG =================

URLS = [
    "https://pellet4future.com/pellet-drzewny-freetime-2010-llc-solid-teploenergo.html",
    "https://pellet4future.com/pellet-drzewny-granulita.html",
    "https://wolebio.pl/produkt/pellet-gold/",
    "https://wolebio.pl/produkt/pellet-olimp-6-mm-5/",
    "https://wolebio.pl/produkt/pellet-lava-premium/"
]

# OUTPUT FILES
OUT_JSONL = Path("pellet_prices.jsonl")
OUT_LATEST_JSON = Path("pellet_prices_latest.json")
OUT_CSV = Path("pellet_prices.csv")
OUT_LOG = Path("runs.txt")

TZ = ZoneInfo("Europe/Warsaw")

# ================= PELLET4FUTURE CONSTANTS =================

P4F_POSTAL_CODE = "40-000"
P4F_PALLETS = 1


# ================= MODELS =================

@dataclass
class VariantResult:
    """One parsed variant with optional weight and price metrics."""

    label: str
    weight_kg: Optional[float]
    price_pln_total: Optional[float]
    price_pln_per_kg: Optional[float]
    raw_weight: Optional[str] = None
    raw_price: Optional[str] = None
    source: Optional[str] = None


@dataclass
class PageResult:
    """Parsed output for one source URL, including optional variants."""

    url: str
    title: Optional[str]
    currency: str = "PLN"

    price_pln_total: Optional[float] = None
    weight_kg_total: Optional[float] = None
    price_pln_per_kg: Optional[float] = None

    variants: List[VariantResult] = field(default_factory=list)

    raw_price: Optional[str] = None
    price_method: Optional[str] = None
    raw_weight: Optional[str] = None
    weight_method: Optional[str] = None
    error: Optional[str] = None

    http_status: Optional[int] = None
    final_url: Optional[str] = None
    content_type: Optional[str] = None


# ================= HELPERS =================

def now_iso() -> str:
    """Return local Warsaw timestamp in ISO format with seconds precision."""

    return datetime.now(TZ).isoformat(timespec="seconds")


def _norm(s: str) -> str:
    """Normalize whitespace and NBSP characters in extracted text."""

    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def _to_float_pl(s: str) -> Optional[float]:
    """Parse first decimal number from a Polish-formatted numeric string."""

    if not s:
        return None
    s = s.replace(" ", "").replace(",", ".")
    m = re.search(r"\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def _decode_html_bytes(raw: bytes, declared: Optional[str]) -> str:
    """
    Try to decode HTML bytes with the declared/apparent encoding,
    then fall back to common Polish encodings if replacement chars appear.
    """
    candidates = []
    if declared:
        candidates.append(declared)
    candidates += ["utf-8", "cp1250", "iso-8859-2"]

    best_text = None
    best_bad = None
    for enc in candidates:
        try:
            text = raw.decode(enc, errors="replace")
        except LookupError:
            continue
        bad = text.count("�")
        if best_bad is None or bad < best_bad:
            best_bad = bad
            best_text = text
        if bad == 0:
            break

    return best_text or raw.decode("utf-8", errors="replace")


# ================= WOO PRICE FALLBACK =================

def extract_price_pln_fallback(soup: BeautifulSoup):
    """Extract WooCommerce price text and parsed PLN value from the page."""

    for n in soup.select(".woocommerce-Price-amount"):
        raw = n.get_text(" ", strip=True)
        m = re.search(r"(\d[\d\s.,]*)\s*(zł|zl)", raw, re.I)
        if m:
            return _to_float_pl(m.group(1)), raw, "woocommerce"
    return None, None, None


# ================= PLAYWRIGHT (PELLET4FUTURE) =================

def fetch_pellet4future_rendered_html(url: str) -> str:
    """Render Pellet4Future page with Playwright and return resulting HTML."""

    from playwright.sync_api import sync_playwright  # pylint: disable=import-outside-toplevel

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="pl-PL")
        page.set_default_timeout(30000)

        page.goto(url, wait_until="networkidle")

        # Postal code
        postal_candidates = [
            "input[name*='postal' i]",
            "input[name*='postcode' i]",
            "input[placeholder*='Kod' i]",
            "input[placeholder*='poczt' i]",
            "input[type='text']",
        ]
        for sel in postal_candidates:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.fill(P4F_POSTAL_CODE)
                break

        # Quantity
        qty = page.locator("input[type='number']")
        if qty.count() > 0:
            qty.first.fill(str(P4F_PALLETS))

        # Click "Sprawdź cenę"
        btn = page.locator("button:has-text('Sprawdź cenę')")
        if btn.count() > 0:
            btn.first.click()

        page.wait_for_function(
            "() => document.body.innerText.match(/ID\\s*Produktu\\s*\\d+/)"
        )

        html = page.content()
        browser.close()
        return html


def extract_pellet4future_offers(html: str) -> List[VariantResult]:
    """Parse rendered Pellet4Future offer cards into structured variants."""

    # Cut related products completely
    m = re.search(r"Produkty\s+powiązane", html, re.I)
    if m:
        html = html[:m.start()]

    soup = BeautifulSoup(html, "lxml")
    results = []

    for s in soup.find_all(string=re.compile(r"ID\s*Produktu\s*\d+", re.I)):
        block = s.parent
        for _ in range(6):
            if block and "Cena regularna" in block.get_text():
                break
            block = block.parent
        if not block:
            continue

        text = _norm(block.get_text(" ", strip=True))

        pid = re.search(r"ID\s*Produktu\s*(\d+)", text).group(1)
        price = _to_float_pl(re.search(r"(\d[\d\s.,]*)\s*zł", text).group(1))
        weight = _to_float_pl(re.search(r"Cena regularna.*?(\d+)\s*kg", text).group(1))

        results.append(
            VariantResult(
                label=f"ID {pid}",
                weight_kg=weight,
                price_pln_total=price,
                price_pln_per_kg=round(price / weight, 6),
                source="pellet4future:js"
            )
        )

    return results


def fetch_pellet4future_rendered_html_v2(url: str) -> str:
    """Render Pellet4Future page using more tolerant button detection."""

    from playwright.sync_api import sync_playwright  # pylint: disable=import-outside-toplevel

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="pl-PL")
        page.set_default_timeout(30000)

        page.goto(url, wait_until="networkidle")

        # Postal code
        postal_candidates = [
            "input[name*='postal' i]",
            "input[name*='postcode' i]",
            "input[placeholder*='Kod' i]",
            "input[placeholder*='poczt' i]",
            "input[type='text']",
        ]
        for sel in postal_candidates:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.fill(P4F_POSTAL_CODE)
                break

        # Quantity
        qty = page.locator("input[type='number']")
        if qty.count() > 0:
            qty.first.fill(str(P4F_PALLETS))

        # Click price check button (label variants)
        btn = page.locator("button").filter(has_text=re.compile(r"sprawd", re.I))
        if btn.count() > 0:
            btn.first.click()

        page.wait_for_function(
            "() => /ID\\s*Produktu\\s*\\d+/i.test(document.body.innerText) "
            "|| /Cena\\s*regularna/i.test(document.body.innerText)"
        )

        html = page.content()
        browser.close()
        return html


def extract_pellet4future_offers_v2(html: str) -> List[VariantResult]:
    """Parse Pellet4Future offers with resilient regex matching."""

    # Cut related products completely
    m = re.search(r"Produkty\s+powi[aą]zane", html, re.I)
    if m:
        html = html[:m.start()]

    soup = BeautifulSoup(html, "lxml")
    results: List[VariantResult] = []

    for s in soup.find_all(string=re.compile(r"ID\s*Produktu\s*\d+", re.I)):
        block = s.parent
        for _ in range(6):
            if block and re.search(r"Cena\s+regularna", block.get_text(), re.I):
                break
            block = block.parent
        if not block:
            continue

        text = _norm(block.get_text(" ", strip=True))

        pid_m = re.search(r"ID\s*Produktu\s*(\d+)", text)
        price_m = re.search(r"(\d[\d\s.,]*)\s*(?:zł|zl|PLN)\b", text, re.I)
        weight_m = re.search(r"Cena\s*regularna.*?(\d+)\s*kg", text, re.I)
        if not (pid_m and price_m and weight_m):
            continue

        pid = pid_m.group(1)
        price = _to_float_pl(price_m.group(1))
        weight = _to_float_pl(weight_m.group(1))
        if not (price and weight):
            continue

        results.append(
            VariantResult(
                label=f"ID {pid}",
                weight_kg=weight,
                price_pln_total=price,
                price_pln_per_kg=round(price / weight, 6),
                source="pellet4future:js"
            )
        )

    return results


def extract_pellet4future_fallback(
    rendered_html: str,
) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Fallback when offer cards are missing:
    try to read a single price + weight from rendered HTML.
    Returns (price_pln_total, weight_kg_total, raw_price).
    """
    text = _norm(BeautifulSoup(rendered_html, "lxml").get_text(" ", strip=True))

    # weight from "Cena regularna 975kg z VAT"
    weight_m = re.search(r"Cena\s+regularna\s+(\d+)\s*kg", text, re.I)
    weight_kg = _to_float_pl(weight_m.group(1)) if weight_m else None

    # price from "1 845,00 zł"
    price_m = re.search(r"(\d[\d\s.,]*)\s*(?:zł|zl|PLN)\b", text, re.I)
    price_pln = _to_float_pl(price_m.group(1)) if price_m else None
    raw_price = price_m.group(0) if price_m else None

    return price_pln, weight_kg, raw_price


# ================= FETCH =================

def make_session():
    """Create a requests session with retry and UA defaults."""

    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=Retry(total=3)))
    s.headers["User-Agent"] = "PelletTracker/FINAL"
    return s


# ================= PARSE =================

def parse_page(url: str, html: str, meta: dict) -> PageResult:
    """Parse one page into a normalized result record."""

    soup = BeautifulSoup(html, "lxml")
    title = soup.title.string.strip() if soup.title else None

    page = PageResult(
        url=url,
        title=title,
        http_status=meta["http_status"],
        final_url=meta["final_url"],
        content_type=meta["content_type"],
    )

    if "pellet4future.com" in url:
        rendered = fetch_pellet4future_rendered_html_v2(url)
        page.variants = extract_pellet4future_offers_v2(rendered)
        if not page.variants:
            price, weight, raw_price = extract_pellet4future_fallback(rendered)
            page.price_pln_total = price
            page.weight_kg_total = weight
            page.price_pln_per_kg = round(price / weight, 6) if (price and weight) else None
            page.raw_price = raw_price
            page.price_method = "pellet4future:fallback"
            page.error = "Pellet4Future: no offers after JS render"
        return page

    price, raw, method = extract_price_pln_fallback(soup)
    page.price_pln_total = price
    page.raw_price = raw
    page.price_method = method

    w = re.search(r"(\d+)\s*kg", soup.get_text())
    if price and w:
        page.weight_kg_total = float(w.group(1))
        page.price_pln_per_kg = round(price / page.weight_kg_total, 6)

    return page


# ================= SAVE =================

def save(run_time: str, results: List[PageResult]):
    """Persist current run output to JSON, JSONL, CSV and run log."""

    payload = {"fetched_at": run_time, "items": [asdict(r) for r in results]}

    OUT_LATEST_JSON.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    with OUT_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    write_header = not OUT_CSV.exists()
    with OUT_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "fetched_at", "url", "variant", "price", "kg", "pln_per_kg", "source"
            ],
        )
        if write_header:
            w.writeheader()
        for p in results:
            if p.variants:
                for v in p.variants:
                    w.writerow({
                        "fetched_at": run_time,
                        "url": p.url,
                        "variant": v.label,
                        "price": v.price_pln_total,
                        "kg": v.weight_kg,
                        "pln_per_kg": v.price_pln_per_kg,
                        "source": v.source,
                    })
            else:
                w.writerow({
                    "fetched_at": run_time,
                    "url": p.url,
                    "variant": "",
                    "price": p.price_pln_total,
                    "kg": p.weight_kg_total,
                    "pln_per_kg": p.price_pln_per_kg,
                    "source": p.price_method,
                })


# ================= MAIN =================

def main():
    """Fetch all configured URLs, parse results, then save snapshots."""

    run_time = now_iso()
    session = make_session()
    results = []

    for url in URLS:
        r = session.get(url, timeout=20)
        html = _decode_html_bytes(r.content, r.apparent_encoding)
        results.append(parse_page(url, html, {
            "http_status": r.status_code,
            "final_url": str(r.url),
            "content_type": r.headers.get("Content-Type"),
        }))
        time.sleep(0.3)

    save(run_time, results)
    ok_sources = sum(1 for p in results if p.variants or p.price_pln_total)
    log_line = f"{run_time} ok_sources={ok_sources}/{len(results)}\n"
    OUT_LOG.open("a", encoding="utf-8").write(log_line)
    print(f"OK - {ok_sources}/{len(results)} finished correctly")


if __name__ == "__main__":
    main()
