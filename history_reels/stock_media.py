import os
import requests
import random
import time
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

def download_clip_for_query(query, index):
    save_path = os.path.join(config.TOPIC_TEMP_DIR, f"raw_clip{index}.mp4")
    if os.path.exists(save_path):
        print(f"Clip {index} already exists. Skipping download.")
        return True

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
                
                # 1. Duplicate detection
                if v_id in config.DOWNLOADED_VIDEO_IDS:
                    continue
                # 2. Minimum duration check (at least 5s)
                if v_dur < 5:
                    continue
                    
                # 3. Orientation scoring (prefer vertical)
                if width < height:
                    score = 10
                elif width == height:
                    score = 5
                else:
                    score = 2
                    
                candidates.append((score, v))
                
            if candidates:
                # Sort by score descending
                candidates.sort(key=lambda x: x[0], reverse=True)
                top_group_size = min(3, len(candidates))
                selected_score, selected_v = random.choice(candidates[:top_group_size])
                
                video_files = selected_v.get("video_files", [])
                link = None
                for vf in video_files:
                    if vf.get("width") == 720 or vf.get("width") == 1080:
                        link = vf.get("link")
                        break
                if not link and video_files:
                    link = video_files[0].get("link")
                    
                if link:
                    print(f"Selected Pexels video ID: {selected_v.get('id')} (Score: {selected_score}, Duration: {selected_v.get('duration')}s)")
                    if download_file_with_retry(link, save_path):
                        config.DOWNLOADED_VIDEO_IDS.add(str(selected_v.get("id")))
                        user_info = selected_v.get("user", {})
                        credit = f"Pexels Video by {user_info.get('name', 'Unknown')} ({selected_v.get('url', '')})"
                        config.VIDEO_ATTRIBUTIONS.append(credit)
                        return True
    except Exception as e:
        print(f"Pexels query failed: {e}")

    # Pixabay Fallback
    print(f"Searching Pixabay for '{query}'...")
    url = f"https://pixabay.com/api/videos/?key={config.PIXABAY_API_KEY}&q={requests.utils.quote(query)}&per_page=15"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            hits = data.get("hits", [])
            
            candidates = []
            for h in hits:
                h_id = str(h.get("id"))
                h_dur = h.get("duration", 0)
                
                if h_id in config.DOWNLOADED_VIDEO_IDS:
                    continue
                if h_dur < 5:
                    continue
                    
                candidates.append(h)
                
            if candidates:
                top_group_size = min(3, len(candidates))
                selected_h = random.choice(candidates[:top_group_size])
                
                videos = selected_h.get("videos", {})
                link = None
                video_obj = videos.get("medium") or videos.get("large") or videos.get("tiny")
                if video_obj:
                    link = video_obj.get("url")
                    
                if link:
                    print(f"Selected Pixabay video ID: {selected_h.get('id')} (Duration: {selected_h.get('duration')}s)")
                    if download_file_with_retry(link, save_path):
                        config.DOWNLOADED_VIDEO_IDS.add(str(selected_h.get("id")))
                        credit = f"Pixabay Video by {selected_h.get('user', 'Unknown')} (ID: {selected_h.get('id')})"
                        config.VIDEO_ATTRIBUTIONS.append(credit)
                        return True
    except Exception as e:
        print(f"Pixabay query failed: {e}")

    # Ultimate fallback
    if query != "astrology":
        return download_clip_for_query("astrology", index)

    return False
