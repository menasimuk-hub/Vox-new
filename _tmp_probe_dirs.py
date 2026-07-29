#!/usr/bin/env python3
"""Probe exhibitor directory pages for scrapeable contact sources."""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

import httpx

URLS = [
    "https://parcelandpostexpo.com/exhibitor-list",
    "https://www.wtm.com/london/en-gb/exhibitor-directory.html",
]

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def summarize(url: str) -> None:
    print("=" * 80)
    print("URL", url)
    with httpx.Client(timeout=45.0, follow_redirects=True, headers=UA) as client:
        r = client.get(url)
        print("status", r.status_code, "final", str(r.url)[:120], "len", len(r.text))
        html = r.text or ""
        print("title", re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S))
        # SPA hints
        print("root_divs", re.findall(r'<div[^>]+id=["\']([^"\']+)["\']', html, re.I)[:20])
        scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.I)
        print("script_count", len(scripts))
        for s in scripts[:15]:
            print("  script", s[:160])
        # API / data hints
        for pat, label in [
            (r"https://[a-z0-9.-]+\.supabase\.co", "supabase"),
            (r"eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}", "jwt"),
            (r"https?://[^\"'\s]+api[^\"'\s]*", "api_url"),
            (r"exhibitor[^\"'\s]{0,40}", "exhibitor_token"),
            (r"mapyourshow|swapcard|eventsair|expocad|mapitic|gtr|easyfairs|explori", "platform"),
            (r"mailto:([^\"'\s>]+)", "mailto"),
            (r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "emails_in_html"),
        ]:
            hits = re.findall(pat, html, re.I)
            uniq = sorted(set(hits))[:12]
            print(label, "n=", len(hits), "sample=", uniq[:8])

        # links that look like exhibitor profiles
        hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, re.I)
        profileish = []
        for h in hrefs:
            low = h.lower()
            if any(t in low for t in ("exhibitor", "stand", "company", "directory", "booth")):
                full = urljoin(url, h)
                if urlparse(full).netloc:
                    profileish.append(full.split("#")[0])
        profileish = sorted(set(profileish))[:25]
        print("profileish_links", len(profileish))
        for p in profileish[:15]:
            print("  ", p)

        # JSON-LD / embedded JSON blobs
        for m in re.finditer(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.I | re.S):
            blob = (m.group(1) or "")[:200]
            print("jsonld", blob.replace("\n", " ")[:180])
        for m in re.finditer(r'<script[^>]*>\s*(window\.[A-Za-z0-9_]+)\s*=\s*(\{.*?\});?\s*</script>', html, re.S):
            print("window_assign", m.group(1), "len", len(m.group(2)))

        # Fetch first large JS asset for API endpoints
        js_candidates = [s for s in scripts if s.endswith(".js") and ("asset" in s or "chunk" in s or "main" in s or "app" in s)]
        if not js_candidates:
            js_candidates = [s for s in scripts if s.endswith(".js")][:3]
        for src in js_candidates[:2]:
            js_url = urljoin(url, src)
            try:
                jr = client.get(js_url)
                js = jr.text or ""
                print("JS", js_url[:120], "len", len(js), "status", jr.status_code)
                for pat, label in [
                    (r"https://[a-z0-9.-]+\.supabase\.co", "supabase"),
                    (r"https://[^\"'\s]{10,120}", "https"),
                    (r"/api/[^\"'\s]{3,80}", "api_path"),
                    (r"exhibitor[^\"'\s]{0,60}", "exhibitor"),
                    (r"mapyourshow|swapcard|eventsair|expocad|explori|mapitic", "platform"),
                ]:
                    hits = re.findall(pat, js, re.I)
                    uniq = sorted(set(hits))
                    if label == "https":
                        uniq = [u for u in uniq if any(k in u.lower() for k in ("api", "exhibitor", "graphql", "supabase", "mapyourshow", "swapcard", "cdn"))][:20]
                    print("  js_"+label, "n=", len(hits), "sample=", uniq[:10])
            except Exception as e:
                print("JS fail", src, e)


if __name__ == "__main__":
    for u in URLS:
        try:
            summarize(u)
        except Exception as e:
            print("FAIL", u, e)
