from __future__ import annotations
import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
import trafilatura


def extract_title_bs4(html: str) -> str | None:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    # 1) <title> (gives "- Wikipedia" etc.)
    if soup.title and soup.title.string:
        t = soup.title.string.strip()
        if t:
            return t

    # 2) og:title / twitter:title
    ogt = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
    if ogt and ogt.get("content"):
        return ogt["content"].strip()

    # 3) Wikipedia h1 fallback
    h1 = soup.select_one("#firstHeading")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)

    return None


def extract_lead_image_bs4(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")

    img = soup.select_one(".infobox .image img")
    if img and img.get("src"):
        src = img["src"].strip()
        if src.startswith("//"):
            return "https:" + src
        return urljoin(base_url, src)

    og = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "twitter:image"})
    if og and og.get("content"):
        return og["content"].strip()

    first_img = soup.select_one("article img") or soup.find("img")
    if first_img and first_img.get("src"):
        return urljoin(base_url, first_img["src"].strip())

    return None

def _parse_iso(dt: str) -> str | None:
    try:
        d = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        return d.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return None

def extract_published_at(html: str) -> tuple[str | None, list[str]]:
    """
    Försök i ordning: JSON-LD Article/NewsArticle/BlogPosting, OG meta, <time>, generiska meta.
    Returnerar (published_at_iso, sources)
    """
    soup = BeautifulSoup(html, "html.parser")
    sources: list[str] = []

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if not isinstance(it, dict):
                continue
            t = it.get("@type")
            if isinstance(t, list):
                t = next((x for x in t if isinstance(x, str)), None)
            if t in {"Article", "NewsArticle", "BlogPosting"}:
                for k in ("datePublished", "dateCreated", "uploadDate"):
                    val = it.get(k)
                    if isinstance(val, str):
                        iso = _parse_iso(val) or val
                        sources.append(f"jsonld:{k}")
                        return (iso, sources)

    og = soup.find("meta", property="article:published_time")
    if og and og.get("content"):
        iso = _parse_iso(og["content"].strip()) or og["content"].strip()
        sources.append("meta:article:published_time")
        return (iso, sources)

    t = soup.find("time")
    if t and t.get("datetime"):
        iso = _parse_iso(t["datetime"].strip()) or t["datetime"].strip()
        sources.append("time:datetime")
        return (iso, sources)

    for name in ("date", "dc.date", "dc.date.issued", "publish_date", "pubdate"):
        m = soup.find("meta", attrs={"name": name})
        if m and m.get("content"):
            iso = _parse_iso(m["content"].strip()) or m["content"].strip()
            sources.append(f"meta:{name}")
            return (iso, sources)

    return (None, sources)


from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

async def fetch_html(url: str, timeout_s: float, user_agent: str) -> Tuple[str, Dict[str, str]]:
    """
    Fetch HTML content with retry logic and exponential backoff.
    Returns tuple of (html_content, response_headers).
    """
    headers = {"User-Agent": user_agent}
    timeout = httpx.Timeout(
        connect=timeout_s,
        read=timeout_s,
        write=timeout_s,
        pool=timeout_s
    )
    
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                headers=headers,
                follow_redirects=True
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                if response.status_code == 200 and "wikipedia.org" in str(response.url).lower():
                    # Try printable view if content seems sparse
                    html = response.text
                    if html.count("<p") < 5:  # simple heuristic
                        u = urlparse(str(response.url))
                        qs = dict(parse_qsl(u.query))
                        if "printable" not in qs:
                            qs["printable"] = "yes"
                            printable_url = urlunparse((u.scheme, u.netloc, u.path, u.params, urlencode(qs), u.fragment))
                            try:
                                r2 = await client.get(printable_url)
                                if r2.status_code == 200 and r2.text.count("<p") > html.count("<p"):
                                    return r2.text, dict(r2.headers)
                            except Exception:
                                pass
                    return html, dict(response.headers)
                
                return response.text, dict(response.headers)
                
        except (httpx.TimeoutException, httpx.HTTPError) as e:
            if attempt == 2:  # Last attempt
                raise
            
            # Exponential backoff: 0.5s, 1s, 2s
            await asyncio.sleep(0.5 * (2 ** attempt))


def extract_trafilatura(html: str, url: str) -> dict:
    import trafilatura
    # Speed/precision tradeoff parameters
    kwargs = dict(
        include_comments=False,
        include_tables=False,
        favor_recall=True,   # Less aggressive filtering
        no_fallback=False    # Allow internal fallbacks
    )
    try:
        data = trafilatura.extract(html, url=url, output="json", **kwargs)
        if not data:
            return {}
        import json
        j = json.loads(data)
        return {
            "title": j.get("title"),
            "text": j.get("text") or "",
            "date": j.get("date"),
            "image": j.get("image")
        }
    except Exception:
        return {}


def fallback_body_text_bs4(html: str) -> str:
    """Simple and robust fallback: combine all reasonable <p> tags."""
    soup = BeautifulSoup(html, "html.parser")
    # Wikipedia/MDN/Blogs: get main content, otherwise all p
    root = soup.select_one("#mw-content-text") or soup.select_one("main") or soup.select_one("article")
    scope = root or soup
    ps = [p.get_text(" ", strip=True) for p in scope.find_all("p")]
    text = " ".join([p for p in ps if p and len(p.split()) >= 5])  # filter junk
    return text

def extract_meta_bs4(html: str) -> Dict[str, str]:
    """
    Extract metadata using BeautifulSoup.
    Returns dict with metadata fields.
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')
        meta: Dict[str, str] = {}
        
        # Extract OpenGraph and Twitter meta tags
        for tag in soup.find_all('meta'):
            property = tag.get('property', tag.get('name', ''))
            content = tag.get('content', '')
            
            if not property or not content:
                continue
                
            if property in {
                'og:title',
                'og:image',
                'twitter:image',
                'article:published_time'
            }:
                meta[property] = content
        
        # Extract <time> tag
        time_tag = soup.find('time')
        if time_tag and time_tag.get('datetime'):
            meta['time'] = time_tag['datetime']
            
        return meta
        
    except Exception:
        return {}


def merge_extraction(primary: Dict[str, Any], meta: Dict[str, str], html: str, url: str) -> tuple[Dict[str, Any], bool]:
    """
    Merge extracted content with metadata, using BS4 fallback if needed.
    Returns tuple of (merged_data, used_bs4_fallback).
    """
    result = primary.copy()
    used_bs4 = False
    
    # Fill gaps from meta
    for k in ("title", "date", "image"):
        if not result.get(k) and meta.get(k):
            result[k] = meta[k]

    # If text is missing or too short: BS4 fallback
    txt = (result.get("text") or "").strip()
    if len(txt.split()) < 20:
        result["text"] = fallback_body_text_bs4(html)
        used_bs4 = True

    # Try BS4 title if missing
    if not result.get("title"):
        if title := extract_title_bs4(html):
            result["title"] = title
            used_bs4 = True

    # Try BS4 image if missing
    if not result.get("image"):
        if image := extract_lead_image_bs4(html, url):
            result["image"] = image
            used_bs4 = True
    
    # Convert date if present
    if result.get('date'):
        try:
            result['date'] = datetime.fromisoformat(result['date'].replace('Z', '+00:00'))
        except ValueError:
            result['date'] = None
            
    return result, used_bs4


def find_lead_image(meta: Dict[str, str]) -> Optional[str]:
    """
    Find lead image URL from metadata.
    Returns URL string or None if not found.
    """
    for key in ('og:image', 'twitter:image'):
        if url := meta.get(key):
            return url
    return None

def extract_site_name(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    og = soup.find("meta", property="og:site_name")
    if og and og.get("content"):
        return og["content"].strip()
    p = urlparse(base_url)
    return p.netloc.lower() or None