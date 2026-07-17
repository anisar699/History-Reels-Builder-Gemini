import os
import requests
import random
import time
import re
import json
from history_reels.jobs import GenerationJob

def download_file_with_retry(url, path, max_attempts=2):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    delay = 0.5
    for attempt in range(1, max_attempts + 1):
        try:
            r = requests.get(url, headers=headers, stream=True, timeout=(5, 30))
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            if os.path.getsize(path) == 0:
                if os.path.exists(path):
                    try: os.remove(path)
                    except: pass
                raise ValueError("Downloaded file is 0 bytes.")
                
            # Validate that the file is not an HTML error/captcha page
            with open(path, "rb") as f:
                header = f.read(20).lower()
                if header.startswith(b"<!doc") or header.startswith(b"<html"):
                    if os.path.exists(path):
                        try: os.remove(path)
                        except: pass
                    raise ValueError("Downloaded file is an HTML page (likely blocked by anti-bot).")
            return True
        except Exception as e:
            if os.path.exists(path):
                try: os.remove(path)
                except: pass
            print(f"Download attempt {attempt} failed: {e}")
            if attempt == max_attempts:
                break
            time.sleep(delay)
            delay *= 1.5
    return False

def search_google_images(query):
    # Queries Bing images behind the scenes as a high-quality, keyless proxy for Google images
    # CRITICAL: Added adlt=strict to ensure strictly safe family-friendly results
    url = f"https://www.bing.com/images/search?q={requests.utils.quote(query)}&first=1&adlt=strict"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        matches = re.findall(r'm="([^"]+)"', r.text)
        urls = []
        for m in matches:
            try:
                clean_m = m.replace("&quot;", '"').replace("&amp;", "&")
                data = json.loads(clean_m)
                murl = data.get("murl")
                if murl and murl.startswith("http"):
                    urls.append(murl)
            except Exception:
                pass
        return list(dict.fromkeys(urls))
    except Exception as e:
        print(f"Scraping Google/Bing search failed: {e}")
        return []

def search_pinterest_images(query):
    url = f"https://www.pinterest.com/search/pins/?q={requests.utils.quote(query)}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        urls = re.findall(r'https://i\.pinimg\.com/[^"\']+\.(?:jpg|png|jpeg)', r.text)
        return list(dict.fromkeys(urls))
    except Exception as e:
        print(f"Scraping Pinterest failed: {e}")
        return []

def download_clip_for_query(query, index, job: GenerationJob):
    # Check if clip (video or image) already exists
    for ext in [".mp4", ".jpg", ".png"]:
        path = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{index}{ext}")
        if os.path.exists(path):
            print(f"Clip {index} already exists as {ext}. Skipping download.")
            return True

    save_path = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{index}.mp4")

    providers = []
    allowed = getattr(job, "ALLOWED_SOURCES", ["pexels", "pixabay", "google", "pinterest", "wikimedia_image"])
    
    if job.MEDIA_PREFERENCE in ["mixed", "videos"]:
        if "storyblocks" in allowed and getattr(job, "STORYBLOCKS_PUBLIC_KEY", None) and getattr(job, "STORYBLOCKS_PRIVATE_KEY", None):
            providers.append("storyblocks")
        if "pexels" in allowed and getattr(job, "PEXELS_API_KEY", None):
            providers.append("pexels")
        if "pixabay" in allowed and getattr(job, "PIXABAY_API_KEY", None):
            providers.append("pixabay")
        if "archive" in allowed:
            providers.append("archive")
            
    if job.MEDIA_PREFERENCE in ["mixed", "images"]:
        if "google" in allowed:
            providers.append("google")
        if "pinterest" in allowed:
            providers.append("pinterest")
        if "wikimedia_image" in allowed:
            providers.append("wikimedia_image")
        if "nasa_image" in allowed:
            providers.append("nasa_image")
        if "unsplash" in allowed:
            providers.append("unsplash")
        
    # Shuffle providers to ensure massive variety in every video!
    random.shuffle(providers)
    
    for provider in providers:
        if provider == "storyblocks":
            print(f"Searching Storyblocks for '{query}'...")
            try:
                import hmac
                import hashlib
                expires = int(time.time()) + 100
                hmac_input = f"/api/v2/videos/search?keywords={requests.utils.quote(query)}"
                sig = hmac.new(
                    job.STORYBLOCKS_PRIVATE_KEY.encode('utf-8'),
                    hmac_input.encode('utf-8'),
                    hashlib.sha256
                ).hexdigest()
                url = f"https://api.storyblocks.com/api/v2/videos/search?keywords={requests.utils.quote(query)}&APIKEY={job.STORYBLOCKS_PUBLIC_KEY}&EXPIRES={expires}&HMAC={sig}"
                r = requests.get(url, timeout=15)
                if r.status_code == 200:
                    results = r.json().get("results", [])
                    results = [r_item for r_item in results if str(r_item.get('id')) not in job.DOWNLOADED_VIDEO_IDS]
                    if results:
                        item = results[0]
                        preview_url = item.get("preview_url")
                        if preview_url and download_file_with_retry(preview_url, save_path):
                            job.DOWNLOADED_VIDEO_IDS.add(str(item.get('id')))
                            job.VIDEO_ATTRIBUTIONS.append(f"Storyblocks Video: {item.get('title')} (ID: {item.get('id')})")
                            return True
            except Exception as e:
                print(f"Storyblocks query failed: {e}")

        elif provider == "pexels":
            print(f"Searching Pexels for '{query}'...")
            url = f"https://api.pexels.com/videos/search?query={requests.utils.quote(query)}&per_page=15"
            headers = {"Authorization": job.PEXELS_API_KEY}
            try:
                r = requests.get(url, headers=headers, timeout=15)
                if r.status_code == 200:
                    videos = r.json().get("videos", [])
                    candidates = []
                    for v in videos:
                        v_id = str(v.get("id"))
                        v_dur = v.get("duration", 0)
                        width = v.get("width", 1)
                        height = v.get("height", 1)
                        if v_id in job.DOWNLOADED_VIDEO_IDS or v_dur < 5:
                            continue
                        score = 10 if width < height else (5 if width == height else 2)
                        candidates.append((score, v))
                    if candidates:
                        candidates.sort(key=lambda x: x[0], reverse=True)
                        selected_score, selected_v = random.choice(candidates[:min(3, len(candidates))])
                        video_files = selected_v.get("video_files", [])
                        link = next((vf.get("link") for vf in video_files if vf.get("width") in [720, 1080]), None)
                        if not link and video_files: link = video_files[0].get("link")
                        if link and download_file_with_retry(link, save_path):
                            job.DOWNLOADED_VIDEO_IDS.add(str(selected_v.get("id")))
                            user_info = selected_v.get("user", {})
                            job.VIDEO_ATTRIBUTIONS.append(f"Pexels Video by {user_info.get('name', 'Unknown')} ({selected_v.get('url', '')})")
                            return True
            except Exception as e:
                print(f"Pexels query failed: {e}")

        elif provider == "pixabay":
            print(f"Searching Pixabay for '{query}'...")
            url = f"https://pixabay.com/api/videos/?key={job.PIXABAY_API_KEY}&q={requests.utils.quote(query)}&per_page=15&safesearch=true"
            try:
                r = requests.get(url, timeout=15)
                if r.status_code == 200:
                    hits = r.json().get("hits", [])
                    candidates = [h for h in hits if str(h.get("id")) not in job.DOWNLOADED_VIDEO_IDS and h.get("duration", 0) >= 5]
                    if candidates:
                        selected_h = random.choice(candidates[:min(3, len(candidates))])
                        videos = selected_h.get("videos", {})
                        video_obj = videos.get("medium") or videos.get("large") or videos.get("tiny")
                        link = video_obj.get("url") if video_obj else None
                        if link and download_file_with_retry(link, save_path):
                            job.DOWNLOADED_VIDEO_IDS.add(str(selected_h.get("id")))
                            job.VIDEO_ATTRIBUTIONS.append(f"Pixabay Video by {selected_h.get('user', 'Unknown')} (ID: {selected_h.get('id')})")
                            return True
            except Exception as e:
                print(f"Pixabay query failed: {e}")

        elif provider == "google":
            print(f"Searching Google/Bing Images for '{query}'...")
            try:
                urls = search_google_images(query)
                for selected_url in urls[:10]:
                    if selected_url in job.DOWNLOADED_VIDEO_IDS:
                        continue
                    ext = ".png" if ".png" in selected_url.lower() else ".jpg"
                    img_save_path = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{index}{ext}")
                    if download_file_with_retry(selected_url, img_save_path):
                        job.DOWNLOADED_VIDEO_IDS.add(selected_url)
                        job.VIDEO_ATTRIBUTIONS.append(f"Google/Bing Image: {selected_url[:80]}...")
                        return True
            except Exception as e:
                print(f"Google/Bing Image query failed: {e}")

        elif provider == "pinterest":
            print(f"Searching Pinterest for '{query}'...")
            try:
                urls = search_pinterest_images(query)
                for selected_url in urls[:10]:
                    if selected_url in job.DOWNLOADED_VIDEO_IDS:
                        continue
                    ext = ".png" if ".png" in selected_url.lower() else ".jpg"
                    img_save_path = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{index}{ext}")
                    if download_file_with_retry(selected_url, img_save_path):
                        job.DOWNLOADED_VIDEO_IDS.add(selected_url)
                        job.VIDEO_ATTRIBUTIONS.append(f"Pinterest Image: {selected_url[:80]}...")
                        return True
            except Exception as e:
                print(f"Pinterest query failed: {e}")

        elif provider == "wikimedia_image":
            print(f"Searching Wikimedia Commons for '{query}'...")
            url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch={requests.utils.quote(query)}&gsrnamespace=6&gsrlimit=10&prop=imageinfo&iiprop=url&format=json"
            headers = {"User-Agent": "HistoryReelsBot/1.0"}
            try:
                r = requests.get(url, headers=headers, timeout=15)
                pages = r.json().get("query", {}).get("pages", {})
                for page_id, page_data in pages.items():
                    info = page_data.get("imageinfo", [])
                    if info:
                        img_url = info[0].get("url")
                        if img_url and img_url.lower().endswith(('.jpg', '.jpeg', '.png')):
                            if img_url in job.DOWNLOADED_VIDEO_IDS:
                                continue
                            ext = ".png" if ".png" in img_url.lower() else ".jpg"
                            img_save_path = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{index}{ext}")
                            if download_file_with_retry(img_url, img_save_path):
                                job.DOWNLOADED_VIDEO_IDS.add(img_url)
                                job.VIDEO_ATTRIBUTIONS.append(f"Wikimedia Commons Image: {page_data.get('title', '')}")
                                return True
            except Exception as e:
                print(f"Wikimedia Image query failed: {e}")

        elif provider == "unsplash":
            print(f"Searching Unsplash for '{query}'...")
            unsplash_key = getattr(job, "UNSPLASH_API_KEY", None)
            if unsplash_key:
                url = f"https://api.unsplash.com/search/photos?query={requests.utils.quote(query)}&per_page=10&orientation=portrait"
                headers = {"Authorization": f"Client-ID {unsplash_key}"}
                try:
                    r = requests.get(url, headers=headers, timeout=15)
                    results = r.json().get("results", [])
                    for item in results:
                        img_url = item.get("urls", {}).get("regular")
                        if img_url:
                            if img_url in job.DOWNLOADED_VIDEO_IDS:
                                continue
                            ext = ".jpg"
                            img_save_path = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{index}{ext}")
                            if download_file_with_retry(img_url, img_save_path):
                                job.DOWNLOADED_VIDEO_IDS.add(img_url)
                                author = item.get("user", {}).get("name", "Unknown")
                                job.VIDEO_ATTRIBUTIONS.append(f"Unsplash Image by {author}")
                                return True
                except Exception as e:
                    print(f"Unsplash query failed: {e}")
            else:
                print("Skipping Unsplash: API key not set in .env")
                
        elif provider == "nasa_image":
            print(f"Searching NASA API for '{query}'...")
            url = f"https://images-api.nasa.gov/search?q={requests.utils.quote(query)}&media_type=image"
            try:
                r = requests.get(url, timeout=15)
                items = r.json().get("collection", {}).get("items", [])
                for item in items[:10]:
                    links = item.get("links", [])
                    if links:
                        img_url = links[0].get("href")
                        if img_url:
                            if img_url in job.DOWNLOADED_VIDEO_IDS:
                                continue
                            ext = ".jpg"
                            img_save_path = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{index}{ext}")
                            if download_file_with_retry(img_url, img_save_path):
                                job.DOWNLOADED_VIDEO_IDS.add(img_url)
                                job.VIDEO_ATTRIBUTIONS.append(f"NASA Image")
                                return True
            except Exception as e:
                print(f"NASA Image query failed: {e}")
                
        elif provider == "archive":
            print(f"Searching Internet Archive for '{query}'...")
            url = f"https://archive.org/advancedsearch.php?q={requests.utils.quote(query)}+AND+mediatype:movies&fl[]=identifier,title&output=json&rows=10"
            try:
                r = requests.get(url, timeout=15)
                docs = r.json().get("response", {}).get("docs", [])
                for doc in docs:
                    identifier = doc.get("identifier")
                    if identifier:
                        meta_url = f"https://archive.org/metadata/{identifier}"
                        meta_r = requests.get(meta_url, timeout=10)
                        files = meta_r.json().get("files", [])
                        mp4_file = next((f for f in files if f.get("name", "").endswith(".mp4") and int(f.get("size", 999999999)) < 100_000_000), None)
                        if mp4_file:
                            video_url = f"https://archive.org/download/{identifier}/{mp4_file['name']}"
                            if video_url in job.DOWNLOADED_VIDEO_IDS:
                                continue
                            save_path = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{index}.mp4")
                            if download_file_with_retry(video_url, save_path):
                                job.DOWNLOADED_VIDEO_IDS.add(video_url)
                                job.VIDEO_ATTRIBUTIONS.append(f"Internet Archive Video: {doc.get('title', 'Unknown')}")
                                return True
            except Exception as e:
                print(f"Internet Archive query failed: {e}")

    # Ultimate fallback
    if query != "cinematic":
        print(f"Query '{query}' failed across all providers. Trying ultimate fallback 'cinematic'...")
        return download_clip_for_query("cinematic", index, job)

    return False
