import html
import re
import xml.etree.ElementTree as ET
import requests
from urllib.parse import urljoin

from history_reels.input_validation import validate_external_url


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3


def fetch_public_response(url, headers, timeout=15):
    """Fetch a bounded public URL while validating every redirect target."""
    current_url = url
    for redirect_count in range(MAX_REDIRECTS + 1):
        valid, reason = validate_external_url(current_url)
        if not valid:
            raise ValueError(reason)
        response = requests.get(
            current_url,
            headers=headers,
            timeout=timeout,
            stream=True,
            allow_redirects=False,
        )
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("Redirect response did not include a destination URL.")
            if redirect_count >= MAX_REDIRECTS:
                raise ValueError("Too many URL redirects.")
            current_url = urljoin(current_url, location)
            continue

        response.raise_for_status()
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > MAX_RESPONSE_BYTES:
                    response.close()
                    raise ValueError("Remote content exceeds the 2 MB safety limit.")
            except ValueError:
                pass
        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                response.close()
                raise ValueError("Remote content exceeds the 2 MB safety limit.")
            chunks.append(chunk)
        response._content = b"".join(chunks)
        response.close()
        return response
    raise ValueError("Too many URL redirects.")

def clean_html(html_text):
    # Remove script and style elements
    html_text = re.sub(r'<(script|style).*?>.*?</\1>', '', html_text, flags=re.DOTALL|re.IGNORECASE)
    # Extract text from p tags
    paragraphs = re.findall(r'<p\b[^>]*>(.*?)</p>', html_text, flags=re.IGNORECASE | re.DOTALL)
    cleaned_paragraphs = []
    for p in paragraphs:
        # Strip all inner html tags
        p_clean = re.sub(r'<[^>]+>', ' ', p)
        # Decode common HTML entities
        p_clean = html.unescape(p_clean)
        p_clean = re.sub(r'\s+', ' ', p_clean).strip()
        if len(p_clean) > 20:  # ignore very short snippets/headers
            cleaned_paragraphs.append(p_clean)
            
    # Fallback to general tag stripping if no paragraphs found
    if not cleaned_paragraphs:
        plain = re.sub(r'<[^>]+>', ' ', html_text)
        plain = re.sub(r'\s+', ' ', plain).strip()
        if len(plain) > 100:
            return plain[:2000] # Limit size
            
    result = "\n\n".join(cleaned_paragraphs[:15]) # limit to first 15 paragraphs for token safety
    return result if result else None

def fetch_rss_feed(rss_url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    valid, reason = validate_external_url(rss_url)
    if not valid:
        print(f"Rejected RSS URL: {reason}")
        return []
    try:
        r = fetch_public_response(rss_url, headers=headers, timeout=15)
    except Exception as e:
        print(f"Error fetching RSS URL: {e}")
        return []
    
    # Try parsing as XML RSS feed
    try:
        root = ET.fromstring(r.content)
        items = []
        # Support RSS 2.0
        for item in root.findall(".//item"):
            title = item.find("title")
            link = item.find("link")
            desc = item.find("description")
            items.append({
                "title": title.text.strip() if title is not None and title.text else "No Title",
                "link": link.text.strip() if link is not None and link.text else "",
                "description": desc.text.strip() if desc is not None and desc.text else ""
            })
        if items:
            return items
            
        # Support Atom
        for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
            title = entry.find("{http://www.w3.org/2005/Atom}title")
            link = entry.find("{http://www.w3.org/2005/Atom}link")
            link_url = link.attrib.get("href") if link is not None else ""
            desc = entry.find("{http://www.w3.org/2005/Atom}summary")
            if desc is None:
                desc = entry.find("{http://www.w3.org/2005/Atom}content")
            items.append({
                "title": title.text.strip() if title is not None and title.text else "No Title",
                "link": link_url,
                "description": desc.text.strip() if desc is not None and desc.text else ""
            })
        return items
    except Exception as e:
        print(f"Failed parsing RSS XML structure: {e}")
        return []

def scrape_article_text(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    valid, reason = validate_external_url(url)
    if not valid:
        print(f"Rejected article URL: {reason}")
        return ""
    try:
        r = fetch_public_response(url, headers=headers, timeout=15)
        r.encoding = r.apparent_encoding
        return clean_html(r.text)
    except Exception as e:
        print(f"Error scraping article URL: {e}")
        return ""
