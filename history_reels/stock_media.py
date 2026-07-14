import os
import requests
import random
import time
import re
import json
from history_reels import config

def download_file_with_retry(url, path, max_attempts=3):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    delay = 1.0
    for attempt in range(1, max_attempts + 1):
        try:
            r = requests.get(url, headers=headers, stream=True, timeout=30)
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            print(f"Download attempt {attempt} failed: {e}")
            if attempt == max_attempts:
                raise
            time.sleep(delay)
            delay *= 2
    return False

def search_google_images(query):
    # Queries Bing images behind the scenes as a high-quality, keyless proxy for Google images
    url = f"https://www.bing.com/images/search?q={requests.utils.quote(query)}&first=1"
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

def download_clip_for_query(query, index):
    # Check if clip (video or image) already exists
    for ext in [".mp4", ".jpg", ".png"]:
        path = os.path.join(config.TOPIC_TEMP_DIR, f"raw_clip{index}{ext}")
        if os.path.exists(path):
            print(f"Clip {index} already exists as {ext}. Skipping download.")
            return True

    save_path = os.path.join(config.TOPIC_TEMP_DIR, f"raw_clip{index}.mp4")

    # 1. Video searches (if MEDIA_PREFERENCE is mixed or videos)
    if config.MEDIA_PREFERENCE in ["mixed", "videos"]:
        # Storyblocks Search
        if getattr(config, "STORYBLOCKS_PUBLIC_KEY", None) and getattr(config, "STORYBLOCKS_PRIVATE_KEY", None):
            print(f"Searching Storyblocks for '{query}'...")
            try:
                import hmac
                import hashlib
                expires = int(time.time()) + 100
                hmac_input = f"/api/v2/videos/search?keywords={requests.utils.quote(query)}"
                sig = hmac.new(
                    config.STORYBLOCKS_PRIVATE_KEY.encode('utf-8'),
                    hmac_input.encode('utf-8'),
                    hashlib.sha256
                ).hexdigest()
                url = f"https://api.storyblocks.com/api/v2/videos/search?keywords={requests.utils.quote(query)}&APIKEY={config.STORYBLOCKS_PUBLIC_KEY}&EXPIRES={expires}&HMAC={sig}"
                r = requests.get(url, timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    results = data.get("results", [])
                    if results:
                        item = results[0]
                        preview_url = item.get("preview_url")
                        if preview_url:
                            print(f"Selected Storyblocks video preview: {item.get('title')}")
                            if download_file_with_retry(preview_url, save_path):
                                credit = f"Storyblocks Video: {item.get('title')} (ID: {item.get('id')})"
                                config.VIDEO_ATTRIBUTIONS.append(credit)
                                return True
            except Exception as e:
                print(f"Storyblocks query failed: {e}")

        # Pexels Search
        print(f"Searching Pexels for '{query}'...")
        url = f"https://api.pexels.com/videos/search?query={requests.utils.quote(query)}&per_page=15"
        headers = {"Authorization": config.PEXELS_API_KEY}
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                videos = data.get("videos", [])
                candidates = []
                for v in videos:
                    v_id = str(v.get("id"))
                    v_dur = v.get("duration", 0)
                    width = v.get("width", 1)
                    height = v.get("height", 1)
                    if v_id in config.DOWNLOADED_VIDEO_IDS or v_dur < 5:
                        continue
                    score = 10 if width < height else (5 if width == height else 2)
                    candidates.append((score, v))
                if candidates:
                    candidates.sort(key=lambda x: x[0], reverse=True)
                    top_group_size = min(3, len(candidates))
                    selected_score, selected_v = random.choice(candidates[:top_group_size])
                    video_files = selected_v.get("video_files", [])
                    link = next((vf.get("link") for vf in video_files if vf.get("width") in [720, 1080]), None)
                    if not link and video_files:
                        link = video_files[0].get("link")
                    if link:
                        print(f"Selected Pexels video ID: {selected_v.get('id')} (Score: {selected_score})")
                        if download_file_with_retry(link, save_path):
                            config.DOWNLOADED_VIDEO_IDS.add(str(selected_v.get("id")))
                            user_info = selected_v.get("user", {})
                            credit = f"Pexels Video by {user_info.get('name', 'Unknown')} ({selected_v.get('url', '')})"
                            config.VIDEO_ATTRIBUTIONS.append(credit)
                            return True
        except Exception as e:
            print(f"Pexels query failed: {e}")

        # Pixabay Search
        print(f"Searching Pixabay for '{query}'...")
        url = f"https://pixabay.com/api/videos/?key={config.PIXABAY_API_KEY}&q={requests.utils.quote(query)}&per_page=15"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                hits = data.get("hits", [])
                candidates = [h for h in hits if str(h.get("id")) not in config.DOWNLOADED_VIDEO_IDS and h.get("duration", 0) >= 5]
                if candidates:
                    top_group_size = min(3, len(candidates))
                    selected_h = random.choice(candidates[:top_group_size])
                    videos = selected_h.get("videos", {})
                    video_obj = videos.get("medium") or videos.get("large") or videos.get("tiny")
                    link = video_obj.get("url") if video_obj else None
                    if link:
                        print(f"Selected Pixabay video ID: {selected_h.get('id')}")
                        if download_file_with_retry(link, save_path):
                            config.DOWNLOADED_VIDEO_IDS.add(str(selected_h.get("id")))
                            credit = f"Pixabay Video by {selected_h.get('user', 'Unknown')} (ID: {selected_h.get('id')})"
                            config.VIDEO_ATTRIBUTIONS.append(credit)
                            return True
        except Exception as e:
            print(f"Pixabay query failed: {e}")

    # 2. Image searches (if MEDIA_PREFERENCE is mixed or images)
    if config.MEDIA_PREFERENCE in ["mixed", "images"]:
        # Google/Bing Search
        print(f"Searching Google/Bing Images for '{query}'...")
        try:
            urls = search_google_images(query)
            if urls:
                selected_url = random.choice(urls[:3])
                ext = ".png" if ".png" in selected_url.lower() else ".jpg"
                img_save_path = os.path.join(config.TOPIC_TEMP_DIR, f"raw_clip{index}{ext}")
                print(f"Selected Google/Bing image: {selected_url[:60]}...")
                if download_file_with_retry(selected_url, img_save_path):
                    credit = f"Google/Bing Image: {selected_url[:80]}..."
                    config.VIDEO_ATTRIBUTIONS.append(credit)
                    return True
        except Exception as e:
            print(f"Google/Bing Image query failed: {e}")

        # Pinterest Search
        print(f"Searching Pinterest for '{query}'...")
        try:
            urls = search_pinterest_images(query)
            if urls:
                selected_url = random.choice(urls[:3])
                ext = ".png" if ".png" in selected_url.lower() else ".jpg"
                img_save_path = os.path.join(config.TOPIC_TEMP_DIR, f"raw_clip{index}{ext}")
                print(f"Selected Pinterest image: {selected_url[:60]}...")
                if download_file_with_retry(selected_url, img_save_path):
                    credit = f"Pinterest Image: {selected_url[:80]}..."
                    config.VIDEO_ATTRIBUTIONS.append(credit)
                    return True
        except Exception as e:
            print(f"Pinterest query failed: {e}")

    # Ultimate fallback
    if query != "astrology":
        return download_clip_for_query("astrology", index)

    return False
