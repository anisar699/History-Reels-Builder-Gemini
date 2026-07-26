import os
import requests
import time
import re
import json
from history_reels.jobs import GenerationJob


# Pinterest is intentionally excluded even from saved/retried job settings:
# its scraped results can be generic social-media artwork instead of footage
# related to the requested topic.
BLOCKED_MEDIA_SOURCES = {"pinterest"}


def _safe_error_message(error: BaseException) -> str:
    """Redact query-string credentials before printing provider failures."""
    text = str(error)
    text = re.sub(
        r"(?i)([?&](?:key|api_?key|token|hmac|signature|expires|apikey)=)[^&\s\"']+",
        r"\1***",
        text,
    )
    text = re.sub(
        r"(?i)(authorization\s*[:=]\s*)(\S+)",
        r"\1***",
        text,
    )
    return text


def media_quality_score(width, height, job: GenerationJob, duration=0) -> int:
    """Rank source metadata for a clean crop without accepting tiny clips."""
    try:
        width, height = int(width or 0), int(height or 0)
    except (TypeError, ValueError):
        return -1
    minimum = effective_min_media_dimension(job)
    if min(width, height) < minimum:
        return -1
    target_ratio = float(getattr(job, "VIDEO_WIDTH", 720)) / max(float(getattr(job, "VIDEO_HEIGHT", 1280)), 1.0)
    source_ratio = width / max(height, 1)
    orientation_score = max(0, 12 - int(abs(source_ratio - target_ratio) * 12))
    resolution_score = min(12, int(min(width, height) / 180))
    duration_score = min(4, int(float(duration or 0) / 8))
    profile = str(getattr(job, "MEDIA_QUALITY_PROFILE", "balanced") or "balanced").lower()
    # High profile requires stronger resolution before ranking bonus.
    if profile == "high" and min(width, height) < 900:
        resolution_score = max(0, resolution_score - 3)
    return orientation_score + resolution_score + duration_score


def effective_min_media_dimension(job: GenerationJob) -> int:
    """Resolve the real minimum short-side dimension from profile + job setting."""
    profile = str(getattr(job, "MEDIA_QUALITY_PROFILE", "balanced") or "balanced").lower()
    configured = int(getattr(job, "MIN_MEDIA_DIMENSION", 0) or 0)
    profile_floor = 720 if profile == "high" else 480
    return max(configured, profile_floor)


def accept_downloaded_image(path: str, job: GenerationJob) -> bool:
    """Reject undersized stills after download so Ken Burns never uses junk assets."""
    from history_reels.ffmpeg_runner import get_media_dimensions

    width, height = get_media_dimensions(path)
    minimum = effective_min_media_dimension(job)
    if width <= 0 or height <= 0 or min(width, height) < minimum:
        print(
            f"Rejected image {os.path.basename(path)}: "
            f"{width}x{height} below quality floor {minimum}px "
            f"(profile={getattr(job, 'MEDIA_QUALITY_PROFILE', 'balanced')})."
        )
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
        return False
    return True

_GENERIC_QUERY_WORDS = {
    "cinematic", "concept", "footage", "futuristic", "image",
    "scene", "stock", "technology", "video",
}
_QUERY_STOP_WORDS = {
    "a", "an", "and", "at", "by", "for", "from", "in", "into", "of",
    "on", "or", "the", "to", "with",
}
_SHOT_VARIANTS = (
    "wide environment",
    "human interaction",
    "close up detail",
    "real world activity",
    "equipment and objects",
)
_RELEVANCE_SYNONYMS = {
    "ai": "ai",
    "automation": "ai",
    "automated": "ai",
    "chatbot": "ai",
    "chatgpt": "ai",
    "deepmind": "ai",
    "intelligence": "ai",
    "machine": "ai",
    "robot": "ai",
    "robotic": "ai",
    "robots": "ai",
    "smart": "ai",
    "healthcare": "health",
    "hospital": "health",
    "medical": "health",
    "surgeon": "health",
    "surgery": "health",
    "education": "education",
    "learning": "education",
    "student": "education",
    "students": "education",
    "studying": "education",
    "teacher": "education",
    "cooking": "cooking",
    "food": "cooking",
    "kitchen": "cooking",
    "exercise": "fitness",
    "fitness": "fitness",
    "gym": "fitness",
    "car": "transport",
    "cars": "transport",
    "highway": "transport",
    "traffic": "transport",
    "transportation": "transport",
    "vehicle": "transport",
    "vehicles": "transport",
    "artist": "creative",
    "artistic": "creative",
    "arts": "creative",
    "creative": "creative",
    "research": "research",
    "science": "research",
    "scientist": "research",
    "service": "service",
    "support": "service",
}
_UNSAFE_MEDIA_PHRASES = {
    "dirty finger",
    "middle finger",
    "obscene gesture",
    "explicit nudity",
    "gore",
    "porn",
}


def _query_fingerprint(query: str) -> set[str]:
    text = re.sub(r"\bartificial intelligence\b", " ai ", str(query).lower())
    tokens = re.findall(r"[a-z0-9]+", text)
    normalized = []
    for token in tokens:
        if token in _GENERIC_QUERY_WORDS:
            continue
        if token in {"robotics", "robotic", "robots"}:
            token = "robot"
        normalized.append(token)
    return set(normalized)


def diversify_media_queries(queries: list[str]) -> list[str]:
    """Keep slide order while giving repeated concepts different shot intent."""
    output = []
    seen: list[set[str]] = []
    variant_index = 0
    for raw_query in queries or []:
        query = str(raw_query).strip()
        if not query:
            continue
        fingerprint = _query_fingerprint(query)
        similarity = 0.0
        for previous in seen:
            union = fingerprint | previous
            similarity = max(similarity, len(fingerprint & previous) / len(union) if union else 1.0)
        if similarity >= 0.34:
            query = f"{query} {_SHOT_VARIANTS[variant_index % len(_SHOT_VARIANTS)]}"
            variant_index += 1
        output.append(query)
        seen.append(fingerprint)
    return output


def media_text_relevance_score(query: str, metadata: str) -> int:
    """Score how directly provider metadata describes the requested subject."""
    query_text = re.sub(r"\bartificial intelligence\b", " ai ", str(query).lower())
    metadata_text = re.sub(r"\bartificial intelligence\b", " ai ", str(metadata).lower())
    raw_query_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", query_text)
        if token not in _GENERIC_QUERY_WORDS and token not in _QUERY_STOP_WORDS
    }
    raw_metadata_tokens = set(re.findall(r"[a-z0-9]+", metadata_text))
    query_tokens = {_RELEVANCE_SYNONYMS.get(token, token) for token in raw_query_tokens}
    metadata_tokens = {_RELEVANCE_SYNONYMS.get(token, token) for token in raw_metadata_tokens}
    if not query_tokens or not metadata_tokens:
        return 0
    overlap = len(query_tokens & metadata_tokens)
    coverage = overlap / len(query_tokens)
    phrase_bonus = 6 if query_text.strip() and query_text.strip() in metadata_text else 0
    score = min(30, int(round(coverage * 24)) + phrase_bonus)
    # "AI teacher", "AI cooking", etc. must visibly describe AI, not merely
    # the secondary activity. This prevents generic lifestyle footage from
    # winning on resolution alone.
    if "ai" in query_tokens and "ai" not in metadata_tokens:
        score = min(score, 3)
    return score


def minimum_media_relevance_score(job: GenerationJob) -> int:
    try:
        return max(0, int(getattr(job, "MIN_MEDIA_RELEVANCE_SCORE", 6) or 6))
    except (TypeError, ValueError):
        return 6


def is_safe_media_metadata(metadata: str) -> bool:
    normalized = re.sub(r"[_-]+", " ", str(metadata or "").lower())
    return not any(phrase in normalized for phrase in _UNSAFE_MEDIA_PHRASES)


def acceptable_media_metadata(query: str, metadata: str, job: GenerationJob) -> bool:
    return (
        is_safe_media_metadata(metadata)
        and media_text_relevance_score(query, metadata) >= minimum_media_relevance_score(job)
    )


def media_candidate_score(
    quality_score,
    result_index,
    creator,
    job: GenerationJob,
    query: str = "",
    metadata: str = "",
) -> int:
    """Combine crop quality, provider relevance order, and creator variety."""
    relevance_bonus = max(0, 18 - (int(result_index) * 2))
    metadata_relevance = media_text_relevance_score(query, metadata)
    used_creators = getattr(job, "MEDIA_CREATORS_USED", None)
    if not isinstance(used_creators, set):
        used_creators = set()
        job.MEDIA_CREATORS_USED = used_creators
    creator_key = str(creator or "").strip().casefold()
    repeat_penalty = 10 if creator_key and creator_key in used_creators else 0
    return int(quality_score) + relevance_bonus + metadata_relevance - repeat_penalty


def _remember_media_creator(job: GenerationJob, creator) -> None:
    creator_key = str(creator or "").strip().casefold()
    if not creator_key:
        return
    used_creators = getattr(job, "MEDIA_CREATORS_USED", None)
    if not isinstance(used_creators, set):
        used_creators = set()
        job.MEDIA_CREATORS_USED = used_creators
    used_creators.add(creator_key)


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
                is_html = header.startswith(b"<!doc") or header.startswith(b"<html")
            if is_html:
                raise ValueError("Downloaded file is an HTML page (likely blocked by anti-bot).")
            return True
        except Exception as e:
            if os.path.exists(path):
                try: os.remove(path)
                except: pass
            print(f"Download attempt {attempt} failed: {_safe_error_message(e)}")
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
        print(f"Scraping Google/Bing search failed: {_safe_error_message(e)}")
        return []

def search_pinterest_images(query):
    url = f"https://www.pinterest.com/search/pins/?q={requests.utils.quote(query)}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        urls = re.findall(r'https://i\.pinimg\.com/[^"\']+\.(?:jpg|png|jpeg)', r.text)
        return list(dict.fromkeys(urls))
    except Exception as e:
        print(f"Scraping Pinterest failed: {_safe_error_message(e)}")
        return []


def _report_media_event(job: GenerationJob, message: str) -> None:
    """Record provider-level media activity for the dashboard's live terminal."""
    history_store = getattr(job, "history_store", None)
    if not history_store:
        return
    try:
        history_store.update_progress(job.job_id, "media", 50, message)
    except Exception as error:
        print(f"Job history warning: {error}")


def download_clip_for_query(query, index, job: GenerationJob):
    if not hasattr(job, "DOWNLOADED_VIDEO_IDS"):
        job.DOWNLOADED_VIDEO_IDS = set()

    # Check if clip (video or image) already exists
    for ext in [".mp4", ".jpg", ".png"]:
        path = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{index}{ext}")
        if os.path.exists(path):
            print(f"Clip {index} already exists as {ext}. Skipping download.")
            _report_media_event(job, f"Visual {index}: using an existing local {ext[1:].upper()} asset.")
            return True

    save_path = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{index}.mp4")

    providers = []
    allowed = list(getattr(job, "ALLOWED_SOURCES", ["pexels", "pixabay", "google", "wikimedia_image"]))
    blocked_sources = sorted(set(allowed) & BLOCKED_MEDIA_SOURCES)
    if blocked_sources:
        print(f"Skipping blocked media source(s): {', '.join(blocked_sources)}")
        allowed = [source for source in allowed if source not in BLOCKED_MEDIA_SOURCES]
    
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
        
    # Prefer configured licensed/API sources before scraped image providers.
    
    for provider in providers:
        provider_label = {
            "storyblocks": "Storyblocks",
            "pexels": "Pexels",
            "pixabay": "Pixabay",
            "google": "Google/Bing Images",
            "pinterest": "Pinterest",
            "wikimedia_image": "Wikimedia Commons",
            "nasa_image": "NASA Images",
            "unsplash": "Unsplash",
            "archive": "Internet Archive",
        }.get(provider, provider.title())
        _report_media_event(job, f"Visual {index}: searching {provider_label} for '{query}'.")
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
                    results = [r_item for r_item in results if str(r_item.get('id')) not in getattr(job, "DOWNLOADED_VIDEO_IDS", set())]
                    results = [
                        result
                        for result in results
                        if acceptable_media_metadata(
                            query,
                            f"{result.get('title', '')} {result.get('description', '')}",
                            job,
                        )
                    ]
                    if results:
                        item = max(
                            results,
                            key=lambda result: media_text_relevance_score(
                                query,
                                f"{result.get('title', '')} {result.get('description', '')}",
                            ),
                        )
                        preview_url = item.get("preview_url")
                        if preview_url and download_file_with_retry(preview_url, save_path):
                            getattr(job, "DOWNLOADED_VIDEO_IDS", set()).add(str(item.get('id')))
                            job.VIDEO_ATTRIBUTIONS.append(f"Storyblocks Video: {item.get('title')} (ID: {item.get('id')})")
                            _report_media_event(job, f"Visual {index}: Storyblocks video downloaded.")
                            return True
            except Exception as e:
                print(f"Storyblocks query failed: {_safe_error_message(e)}")

        elif provider == "pexels":
            print(f"Searching Pexels for '{query}'...")
            url = f"https://api.pexels.com/videos/search?query={requests.utils.quote(query)}&per_page=15"
            headers = {"Authorization": job.PEXELS_API_KEY}
            try:
                r = requests.get(url, headers=headers, timeout=15)
                if r.status_code == 200:
                    videos = r.json().get("videos", [])
                    candidates = []
                    for result_index, v in enumerate(videos):
                        v_id = str(v.get("id"))
                        v_dur = (v.get("duration") or 0)
                        width = v.get("width", 1)
                        height = v.get("height", 1)
                        quality_score = media_quality_score(width, height, job, v_dur)
                        if v_id in getattr(job, "DOWNLOADED_VIDEO_IDS", set()) or v_dur < 5 or quality_score < 0:
                            continue
                        creator = (v.get("user") or {}).get("name", "")
                        metadata = f"{v.get('url', '')} {v.get('title', '')} {v.get('description', '')}"
                        if not acceptable_media_metadata(query, metadata, job):
                            continue
                        score = media_candidate_score(
                            quality_score, result_index, creator, job, query, metadata
                        )
                        candidates.append((score, result_index, v))
                    if candidates:
                        candidates.sort(key=lambda item: (-item[0], item[1]))
                        _, _, selected_v = candidates[0]
                        video_files = selected_v.get("video_files", [])
                        video_files = [vf for vf in video_files if media_quality_score(vf.get("width"), vf.get("height"), job, selected_v.get("duration", 0)) >= 0]
                        link = next((vf.get("link") for vf in video_files if vf.get("width") in [720, 1080]), None)
                        if not link and video_files: link = video_files[0].get("link")
                        if link and download_file_with_retry(link, save_path):
                            getattr(job, "DOWNLOADED_VIDEO_IDS", set()).add(str(selected_v.get("id")))
                            user_info = selected_v.get("user", {})
                            _remember_media_creator(job, user_info.get("name", ""))
                            job.VIDEO_ATTRIBUTIONS.append(f"Pexels Video by {user_info.get('name', 'Unknown')} ({selected_v.get('url', '')})")
                            _report_media_event(job, f"Visual {index}: Pexels video downloaded.")
                            return True
            except Exception as e:
                print(f"Pexels query failed: {_safe_error_message(e)}")

        elif provider == "pixabay":
            print(f"Searching Pixabay for '{query}'...")
            url = f"https://pixabay.com/api/videos/?key={job.PIXABAY_API_KEY}&q={requests.utils.quote(query)}&per_page=15&safesearch=true"
            try:
                r = requests.get(url, timeout=15)
                if r.status_code == 200:
                    hits = r.json().get("hits", [])
                    candidates = []
                    for result_index, hit in enumerate(hits):
                        if str(hit.get("id")) in getattr(job, "DOWNLOADED_VIDEO_IDS", set()) or (hit.get("duration") or 0) < 5:
                            continue
                        quality_scores = [
                            media_quality_score(
                                video.get("width"),
                                video.get("height"),
                                job,
                                hit.get("duration") or 0,
                            )
                            for video in (hit.get("videos") or {}).values()
                        ]
                        usable_scores = [score for score in quality_scores if score >= 0]
                        if not usable_scores:
                            continue
                        if not acceptable_media_metadata(query, hit.get("tags", ""), job):
                            continue
                        score = media_candidate_score(
                            max(usable_scores),
                            result_index,
                            hit.get("user", ""),
                            job,
                            query,
                            hit.get("tags", ""),
                        )
                        candidates.append((score, result_index, hit))
                    if candidates:
                        candidates.sort(key=lambda item: (-item[0], item[1]))
                        _, _, selected_h = candidates[0]
                        videos = selected_h.get("videos") or {}
                        candidates_by_quality = [v for v in videos.values() if media_quality_score(v.get("width"), v.get("height"), job, (selected_h.get("duration") or 0)) >= 0]
                        candidates_by_quality.sort(key=lambda v: media_quality_score(v.get("width"), v.get("height"), job, (selected_h.get("duration") or 0)), reverse=True)
                        video_obj = candidates_by_quality[0] if candidates_by_quality else None
                        link = video_obj.get("url") if video_obj else None
                        if link and download_file_with_retry(link, save_path):
                            getattr(job, "DOWNLOADED_VIDEO_IDS", set()).add(str(selected_h.get("id")))
                            _remember_media_creator(job, selected_h.get("user", ""))
                            job.VIDEO_ATTRIBUTIONS.append(f"Pixabay Video by {selected_h.get('user', 'Unknown')} (ID: {selected_h.get('id')})")
                            _report_media_event(job, f"Visual {index}: Pixabay video downloaded.")
                            return True
            except Exception as e:
                print(f"Pixabay query failed: {_safe_error_message(e)}")

        elif provider == "google":
            print(f"Searching Google/Bing Images for '{query}'...")
            try:
                urls = search_google_images(query)
                for selected_url in urls[:10]:
                    if selected_url in getattr(job, "DOWNLOADED_VIDEO_IDS", set()):
                        continue
                    ext = ".png" if ".png" in selected_url.lower() else ".jpg"
                    img_save_path = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{index}{ext}")
                    if download_file_with_retry(selected_url, img_save_path) and accept_downloaded_image(img_save_path, job):
                        getattr(job, "DOWNLOADED_VIDEO_IDS", set()).add(selected_url)
                        job.VIDEO_ATTRIBUTIONS.append(f"Google/Bing Image: {selected_url[:80]}...")
                        _report_media_event(job, f"Visual {index}: Google/Bing image downloaded.")
                        return True
            except Exception as e:
                print(f"Google/Bing Image query failed: {_safe_error_message(e)}")

        elif provider == "pinterest":
            print(f"Searching Pinterest for '{query}'...")
            try:
                urls = search_pinterest_images(query)
                for selected_url in urls[:10]:
                    if selected_url in getattr(job, "DOWNLOADED_VIDEO_IDS", set()):
                        continue
                    ext = ".png" if ".png" in selected_url.lower() else ".jpg"
                    img_save_path = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{index}{ext}")
                    if download_file_with_retry(selected_url, img_save_path) and accept_downloaded_image(img_save_path, job):
                        getattr(job, "DOWNLOADED_VIDEO_IDS", set()).add(selected_url)
                        job.VIDEO_ATTRIBUTIONS.append(f"Pinterest Image: {selected_url[:80]}...")
                        _report_media_event(job, f"Visual {index}: Pinterest image downloaded.")
                        return True
            except Exception as e:
                print(f"Pinterest query failed: {_safe_error_message(e)}")

        elif provider == "wikimedia_image":
            print(f"Searching Wikimedia Commons for '{query}'...")
            url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch={requests.utils.quote(query)}&gsrnamespace=6&gsrlimit=10&prop=imageinfo&iiprop=url&format=json"
            headers = {"User-Agent": "HistoryReelsBot/1.0"}
            try:
                r = requests.get(url, headers=headers, timeout=15)
                pages = r.json().get("query", {}).get("pages", {})
                ranked_pages = sorted(
                    pages.items(),
                    key=lambda item: media_text_relevance_score(query, item[1].get("title", "")),
                    reverse=True,
                )
                for page_id, page_data in ranked_pages:
                    info = page_data.get("imageinfo", [])
                    if not acceptable_media_metadata(query, page_data.get("title", ""), job):
                        continue
                    if info:
                        img_url = info[0].get("url")
                        if img_url and img_url.lower().endswith(('.jpg', '.jpeg', '.png')):
                            if img_url in getattr(job, "DOWNLOADED_VIDEO_IDS", set()):
                                continue
                            ext = ".png" if ".png" in img_url.lower() else ".jpg"
                            img_save_path = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{index}{ext}")
                            if download_file_with_retry(img_url, img_save_path) and accept_downloaded_image(img_save_path, job):
                                getattr(job, "DOWNLOADED_VIDEO_IDS", set()).add(img_url)
                                job.VIDEO_ATTRIBUTIONS.append(f"Wikimedia Commons Image: {page_data.get('title', '')}")
                                _report_media_event(job, f"Visual {index}: Wikimedia Commons image downloaded.")
                                return True
            except Exception as e:
                print(f"Wikimedia Image query failed: {_safe_error_message(e)}")

        elif provider == "unsplash":
            print(f"Searching Unsplash for '{query}'...")
            unsplash_key = getattr(job, "UNSPLASH_API_KEY", None)
            if unsplash_key:
                url = f"https://api.unsplash.com/search/photos?query={requests.utils.quote(query)}&per_page=10&orientation=portrait"
                headers = {"Authorization": f"Client-ID {unsplash_key}"}
                try:
                    r = requests.get(url, headers=headers, timeout=15)
                    results = r.json().get("results", [])
                    results.sort(
                        key=lambda item: media_text_relevance_score(
                            query,
                            " ".join(
                                str(value or "")
                                for value in (
                                    item.get("description"),
                                    item.get("alt_description"),
                                    " ".join(tag.get("title", "") for tag in item.get("tags", [])),
                                )
                            ),
                        ),
                        reverse=True,
                    )
                    for item in results:
                        metadata = " ".join(
                            str(value or "")
                            for value in (
                                item.get("description"),
                                item.get("alt_description"),
                                " ".join(tag.get("title", "") for tag in item.get("tags", [])),
                            )
                        )
                        if not acceptable_media_metadata(query, metadata, job):
                            continue
                        img_url = (item.get("urls") or {}).get("regular")
                        if img_url:
                            if img_url in getattr(job, "DOWNLOADED_VIDEO_IDS", set()):
                                continue
                            ext = ".jpg"
                            img_save_path = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{index}{ext}")
                            if download_file_with_retry(img_url, img_save_path) and accept_downloaded_image(img_save_path, job):
                                getattr(job, "DOWNLOADED_VIDEO_IDS", set()).add(img_url)
                                author = item.get("user", {}).get("name", "Unknown")
                                job.VIDEO_ATTRIBUTIONS.append(f"Unsplash Image by {author}")
                                _report_media_event(job, f"Visual {index}: Unsplash image downloaded.")
                                return True
                except Exception as e:
                    print(f"Unsplash query failed: {_safe_error_message(e)}")
            else:
                print("Skipping Unsplash: API key not set in .env")
                
        elif provider == "nasa_image":
            print(f"Searching NASA API for '{query}'...")
            url = f"https://images-api.nasa.gov/search?q={requests.utils.quote(query)}&media_type=image"
            try:
                r = requests.get(url, timeout=15)
                items = r.json().get("collection", {}).get("items", [])
                for item in items[:10]:
                    item_data = (item.get("data") or [{}])[0]
                    metadata = f"{item_data.get('title', '')} {item_data.get('description', '')} {item_data.get('keywords', '')}"
                    if not acceptable_media_metadata(query, metadata, job):
                        continue
                    links = item.get("links", [])
                    if links:
                        img_url = links[0].get("href")
                        if img_url:
                            if img_url in getattr(job, "DOWNLOADED_VIDEO_IDS", set()):
                                continue
                            ext = ".jpg"
                            img_save_path = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{index}{ext}")
                            if download_file_with_retry(img_url, img_save_path) and accept_downloaded_image(img_save_path, job):
                                getattr(job, "DOWNLOADED_VIDEO_IDS", set()).add(img_url)
                                job.VIDEO_ATTRIBUTIONS.append(f"NASA Image")
                                _report_media_event(job, f"Visual {index}: NASA image downloaded.")
                                return True
            except Exception as e:
                print(f"NASA Image query failed: {_safe_error_message(e)}")
                
        elif provider == "archive":
            print(f"Searching Internet Archive for '{query}'...")
            url = f"https://archive.org/advancedsearch.php?q={requests.utils.quote(query)}+AND+mediatype:movies&fl[]=identifier,title&output=json&rows=10"
            try:
                r = requests.get(url, timeout=15)
                docs = r.json().get("response", {}).get("docs", [])
                docs.sort(
                    key=lambda doc: media_text_relevance_score(query, doc.get("title", "")),
                    reverse=True,
                )
                for doc in docs:
                    if not acceptable_media_metadata(query, doc.get("title", ""), job):
                        continue
                    identifier = doc.get("identifier")
                    if identifier:
                        meta_url = f"https://archive.org/metadata/{identifier}"
                        meta_r = requests.get(meta_url, timeout=10)
                        files = meta_r.json().get("files", [])
                        def _get_size(f_obj):
                            try:
                                return int(f_obj.get("size", 999999999))
                            except ValueError:
                                return float('inf')
                        mp4_file = next((f for f in files if f.get("name", "").endswith(".mp4") and _get_size(f) < 100_000_000), None)
                        if mp4_file:
                            video_url = f"https://archive.org/download/{identifier}/{mp4_file['name']}"
                            if video_url in getattr(job, "DOWNLOADED_VIDEO_IDS", set()):
                                continue
                            save_path = os.path.join(job.TOPIC_TEMP_DIR, f"raw_clip{index}.mp4")
                            if download_file_with_retry(video_url, save_path):
                                getattr(job, "DOWNLOADED_VIDEO_IDS", set()).add(video_url)
                                job.VIDEO_ATTRIBUTIONS.append(f"Internet Archive Video: {doc.get('title', 'Unknown')}")
                                _report_media_event(job, f"Visual {index}: Internet Archive video downloaded.")
                                return True
            except Exception as e:
                print(f"Internet Archive query failed: {_safe_error_message(e)}")

    # Keep fallback results tied to the requested subject. A bare "cinematic"
    # fallback frequently returned attractive but unrelated footage.
    fallback_suffix = "documentary footage"
    if not str(query).strip().lower().endswith(fallback_suffix):
        fallback_query = f"{str(query).strip()} {fallback_suffix}".strip()
        print(
            f"Query '{query}' failed across all providers. "
            f"Trying subject-preserving fallback '{fallback_query}'..."
        )
        return download_clip_for_query(fallback_query, index, job)

    return False
