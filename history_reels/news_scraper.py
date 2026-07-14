import re
import xml.etree.ElementTree as ET
import requests

def clean_html(html_text):
    # Remove script and style elements
    html_text = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', html_text, flags=re.IGNORECASE)
    html_text = re.sub(r'<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>', '', html_text, flags=re.IGNORECASE)
    # Extract text from p tags
    paragraphs = re.findall(r'<p\b[^>]*>(.*?)</p>', html_text, flags=re.IGNORECASE | re.DOTALL)
    cleaned_paragraphs = []
    for p in paragraphs:
        # Strip all inner html tags
        p_clean = re.sub(r'<[^>]+>', '', p)
        # Decode common HTML entities
        p_clean = (p_clean.replace("&nbsp;", " ")
                           .replace("&amp;", "&")
                           .replace("&quot;", '"')
                           .replace("&apos;", "'")
                           .replace("&#39;", "'")
                           .replace("&lt;", "<")
                           .replace("&gt;", ">")
                           .replace("\r", "")
                           .replace("\n", " "))
        p_clean = re.sub(r'\s+', ' ', p_clean).strip()
        if len(p_clean) > 20:  # ignore very short snippets/headers
            cleaned_paragraphs.append(p_clean)
            
    # Fallback to general tag stripping if no paragraphs found
    if not cleaned_paragraphs:
        plain = re.sub(r'<[^>]+>', ' ', html_text)
        plain = re.sub(r'\s+', ' ', plain).strip()
        if len(plain) > 100:
            return plain[:2000] # Limit size
            
    return "\n\n".join(cleaned_paragraphs[:15]) # limit to first 15 paragraphs for token safety

def fetch_rss_feed(rss_url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.get(rss_url, headers=headers, timeout=15)
        r.raise_for_status()
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
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        return clean_html(r.text)
    except Exception as e:
        print(f"Error scraping article URL: {e}")
        return ""
