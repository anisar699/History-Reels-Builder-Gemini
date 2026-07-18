import os
import sys
import argparse
import random
import shutil
import requests

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass
from history_reels import config
from history_reels.font_manager import is_usable_font, prepare_caption_font
from history_reels.music_library import ensure_local_music_track
from history_reels.jobs import GenerationJob, create_generation_job
from history_reels.job_store import JobCancelledError, JobStore
from history_reels.script_generator import fetch_ai_script
from history_reels.script_generator import fetch_ai_script
from history_reels.stock_media import download_clip_for_query
from history_reels.voiceover import generate_voiceover
from history_reels.renderer import build_video_frames, run_ffmpeg
from history_reels.seo import write_seo_package
from history_reels.verification import verify_deliverable

def download_file(url, path):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, stream=True, timeout=30)
        r.raise_for_status()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        part_path = path + ".part"
        with open(part_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        os.rename(part_path, path)
    except Exception as e:
        print(f"Network error downloading {url}: {e}")

def ensure_assets(job: GenerationJob):
    # Make sure target directories exist
    os.makedirs(job.ASSETS_DIR, exist_ok=True)
    os.makedirs(job.MUSIC_DIR, exist_ok=True)
    
    # 1. Resolve the selected language font. A valid uploaded custom font is
    # preserved instead of being overwritten by a default font path.
    prepare_caption_font(job, download_file)
    # 2. Provision the selected reusable local original track.
    ensure_local_music_track(job)

def check_inputs(job: GenerationJob):
    os.makedirs(job.TOPIC_TEMP_DIR, exist_ok=True)
    os.makedirs(job.OUTPUT_DIR, exist_ok=True)

    captions = list(getattr(job, "CAPTIONS", []) or [])
    narrations = list(getattr(job, "NARRATIONS", []) or [])
    if not captions:
        captions = [getattr(job, f"CAPTION_TEXT_{index}", "") for index in range(1, 21)]
    if not narrations:
        narrations = [getattr(job, f"NARRATION_TEXT_{index}", "") for index in range(1, 21)]
    captions = [str(value).strip() for value in captions if str(value).strip()]
    narrations = [str(value).strip() for value in narrations if str(value).strip()]
    if len(captions) != len(narrations):
        print("Error: Captions and narrations must contain the same number of slides.")
        return False
    queries = [str(value).strip() for value in (getattr(job, "QUERIES", []) or []) if str(value).strip()]
    if not captions or not narrations or not queries:
        print("Error: At least one caption, narration, and media query is required.")
        return False
    job.CAPTIONS = captions
    job.NARRATIONS = narrations
    job.QUERIES = queries
    
    ensure_assets(job)
    
    if not is_usable_font(job.FONT_PATH):
        print(f"Error: Caption font not found or invalid at {job.FONT_PATH}")
        return False
        
    music_mp3 = os.path.join(job.MUSIC_DIR, f"{job.BG_MUSIC_VIBE}_{job.BG_MUSIC_TRACK_INDEX}.mp3")
    if not os.path.exists(music_mp3):
        print("Error: Local background music track could not be created.")
        return False

    return True

def download_visuals(job: GenerationJob, voice_dur):
    print(f"\n--- Downloading Media based on Voice Duration ({voice_dur:.1f}s) ---")
    pacing = getattr(job, "CLIP_DURATION_TARGET", 5.0)
    
    import math
    required_clips = math.ceil(voice_dur / max(pacing, 0.1))
    
    expanded_queries = []
    while len(expanded_queries) < required_clips:
        if not job.QUERIES:
            break
        expanded_queries.extend(job.QUERIES)
    job.QUERIES = expanded_queries[:required_clips]
    
    clip_idx = 1
    successful_queries = []
    for q in job.QUERIES:
        if download_clip_for_query(q, clip_idx, job):
            successful_queries.append(q)
            clip_idx += 1
        else:
            print(f"Warning: Could not retrieve video clip for query '{q}'")
    if not successful_queries:
        raise RuntimeError(
            "No usable media could be downloaded from the selected sources. "
            "Check media-source keys or choose another source profile and retry."
        )
    if len(successful_queries) < required_clips:
        print(
            f"Warning: Retrieved {len(successful_queries)}/{required_clips} media assets. "
            "The renderer will reuse valid assets instead of producing blank frames."
        )
    job.QUERIES = successful_queries

def copy_deliverables(job: GenerationJob):
    final_video = job.video_path
    final_txt = job.seo_path
    
    target_dir = os.path.dirname(final_video)
    os.makedirs(target_dir, exist_ok=True)
    print(f"Copying final files to {target_dir}...")
    
    src_video = os.path.join(job.TOPIC_TEMP_DIR, "output.mp4")
    src_txt = os.path.join(job.TOPIC_TEMP_DIR, "output.txt")
    
    if not os.path.exists(src_video):
        print(f"Error: output.mp4 not found in {job.TOPIC_TEMP_DIR}. Pipeline may have failed.")
        return False
    if not os.path.exists(src_txt):
        raise FileNotFoundError("SEO package was not created; final deliverables were not copied.")
    
    import subprocess
    intro_path = getattr(job, "INTRO_BUMPER", None)
    outro_path = getattr(job, "OUTRO_BUMPER", None)
    
    if intro_path or outro_path:
        print("Stitching Intro/Outro Bumpers...")
        concat_list = []
        
        def format_bumper(bumper_path, suffix):
            tmp_bumper = os.path.join(job.TOPIC_TEMP_DIR, f"scaled_bumper_{suffix}.mp4")
            vf = f"scale={job.VIDEO_WIDTH}:{job.VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,pad={job.VIDEO_WIDTH}:{job.VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2"
            
            # Ensure the bumper matches output.mp4 properties EXACTLY to prevent concat failures
            cmd = [
                "ffmpeg", "-y", "-i", bumper_path, 
                "-vf", vf, "-r", str(job.FPS),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", 
                "-c:a", "aac", "-ar", "44100", "-b:a", "192k", 
                tmp_bumper
            ]
            subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL)
            return tmp_bumper

        if intro_path and os.path.exists(intro_path):
            concat_list.append(format_bumper(intro_path, "intro"))
        
        concat_list.append(src_video)
        
        if outro_path and os.path.exists(outro_path):
            concat_list.append(format_bumper(outro_path, "outro"))
            
        list_txt = os.path.join(job.TOPIC_TEMP_DIR, "concat_list.txt")
        with open(list_txt, "w") as f:
            for item in concat_list:
                item_clean = item.replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{item_clean}'\n")
                
        stitched_video = os.path.join(job.TOPIC_TEMP_DIR, "stitched_output.mp4")
        cmd_concat = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_txt, "-c", "copy", stitched_video]
        subprocess.run(cmd_concat, check=True, stdin=subprocess.DEVNULL)
        
        shutil.copy2(stitched_video, final_video)
    else:
        shutil.copy2(src_video, final_video)
        
    if os.path.exists(src_txt):
        shutil.copy2(src_txt, final_txt)
    if not os.path.exists(final_video) or not os.path.exists(final_txt):
        raise RuntimeError("Final deliverables could not be copied to the output folder.")
    print("Deliverables copied.")
    return True

def cleanup(job: GenerationJob):
    print("Cleaning up temporary topic files...")
    if os.path.exists(job.TOPIC_TEMP_DIR) and job.TOPIC_TEMP_DIR != job.TEMP_DIR:
        try:
            shutil.rmtree(job.TOPIC_TEMP_DIR)
            print("Cleanup complete.")
        except Exception as e:
            print(f"Cleanup warning: {e}")


def _job_request(job, topic, provider, manual_script_data, is_raw_script):
    if isinstance(topic, dict):
        label = topic.get("title") or topic.get("link") or "Imported article"
    elif isinstance(topic, str) and topic.strip():
        label = topic.strip()
    elif manual_script_data:
        label = manual_script_data.get("title", "Manual script")
    else:
        label = "Universal creator demo"
    return {
        "label": str(label)[:500],
        "provider": provider,
        "is_raw_script": bool(is_raw_script),
        "manual_script_data": manual_script_data,
        "topic": topic,
        "retry_of": getattr(job, "RETRY_OF", ""),
    }


def _start_job_lifecycle(job: GenerationJob, request):
    """Persist a local lifecycle record without storing API credentials."""
    try:
        if not job.history_store:
            job.history_store = JobStore(job.OUTPUT_DIR)
            job.history_store.create_job(job, request)
        job.history_store.mark_running(job.job_id)
        job.status = "running"
        _report_job(job, "starting", 1, "Preparing isolated job workspace.")
    except Exception as error:
        # A history write failure should not make an otherwise valid local
        # render unusable; surface it in logs and continue without persistence.
        job.history_store = None
        print(f"Job history warning: {error}")


def _finish_job(job: GenerationJob, status: str, error_message: str = ""):
    job.status = status
    if not job.history_store:
        return
    try:
        if status == "succeeded":
            job.history_store.mark_succeeded(job)
        elif status == "cancelled":
            job.history_store.mark_cancelled(job, error_message)
        else:
            job.history_store.mark_failed(job, error_message)
    except Exception as error:
        print(f"Job history warning: {error}")


def _report_job(job: GenerationJob, stage: str, progress: int, message: str):
    job.current_stage = stage
    job.progress = progress
    print(f"[{progress:03d}%] {stage}: {message}")
    if job.history_store:
        try:
            job.history_store.update_progress(job.job_id, stage, progress, message)
        except Exception as error:
            print(f"Job history warning: {error}")


def _check_cancellation(job: GenerationJob):
    if job.history_store and job.history_store.cancellation_requested(job.job_id):
        raise JobCancelledError("Generation cancelled at a safe pipeline checkpoint.")

def generate_video_for_topic(topic, provider="gemini", manual_script_data=None, is_raw_script=False, job=None):
    """Generate one reel using only the supplied job's state and workspace."""
    job = job or create_generation_job(config)
    job.reset_runtime_state()
    _start_job_lifecycle(job, _job_request(job, topic, provider, manual_script_data, is_raw_script))
    try:
        _report_job(job, "workspace", 5, "Creating isolated workspace.")
        job.prepare_workspace()
    except FileExistsError:
        job.last_error = f"Job workspace already exists: {job.TOPIC_TEMP_DIR}"
        print(job.last_error)
        _finish_job(job, "failed", job.last_error)
        return False

    is_valid_topic = False
    if isinstance(topic, str) and topic.strip() != "":
        is_valid_topic = True
    elif isinstance(topic, dict) and topic:
        is_valid_topic = True

    if is_valid_topic or manual_script_data:
        print(f"\n--- Generating Video (Manual/API Mode) ---")
        try:
            _report_job(job, "script", 12, "Preparing script configuration.")
            if manual_script_data:
                print("Using manually entered script configuration...")
                from history_reels.script_generator import ScriptConfig
                try:
                    validated = ScriptConfig(**manual_script_data)
                    ai_data = validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()
                except Exception as e:
                    print(f"Error: Invalid manual script data - {e}")
                    job.last_error = f"Validation Error: {e}"
                    _finish_job(job, "failed", job.last_error)
                    return False
            elif isinstance(topic, dict):
                print(f"Processing scraped article/news topic...")
                from history_reels.news_scraper import scrape_article_text
                target_url = topic.get("link", "")
                article_text = scrape_article_text(target_url) if target_url else ""
                if not article_text:
                    article_text = topic.get("desc", "")
                
                # Format into a string prompt for the AI
                prompt_text = f"News Headline: {topic.get('title')}\n\nArticle Body:\n{article_text[:4000]}"
                ai_data = fetch_ai_script(prompt_text, provider=provider, is_raw_script=False, settings=job)
            else:
                ai_data = fetch_ai_script(topic, provider=provider, is_raw_script=is_raw_script, settings=job)
            
            job.apply_script(ai_data, track_index=random.randint(1, 5))
            
            print("\n=== AI Generated Script & Config ===")
            print(f"Job: {job.job_id}")
            print(f"Title: {job.TOPIC_TITLE} ({job.TOPIC_YEAR})")
            print(f"Music Vibe: {job.BG_MUSIC_VIBE} (Track #{job.BG_MUSIC_TRACK_INDEX})")
            print(f"AI Music Suggestion: {job.AI_SUGGESTED_MUSIC_VIBE} (dashboard selection preserved)")
            print(f"Video Search Queries: {job.QUERIES}")
            print("====================================\n")
        except Exception as e:
            err_msg = f"Error fetching AI script: {e}"
            print(f"Error fetching AI script, skipping topic '{topic}'. Error: {e}")
            job.last_error = err_msg
            _finish_job(job, "failed", err_msg)
            cleanup(job)
            return False
    else:
        print("\n--- Running Fallback Mode (Universal Creator Demo) ---")
        _report_job(job, "script", 12, "Preparing fallback script configuration.")
        job.TOPIC_TITLE = "Universal Creator Demo"
        job.TOPIC_YEAR = "Demo"
        job.OUTPUT_NAME = job.build_output_name()
        job.QUERIES = ["creative workspace", "smartphone video creation", "social media content", "ideas notebook", "studio lights", "editing timeline", "audience engagement", "creator success"]
        
    try:
        _report_job(job, "validation", 20, "Validating local render inputs.")
        _check_cancellation(job)
        if not check_inputs(job):
            err_msg = "Input validation failed. Please ensure all required API keys are configured and local audio assets are downloaded."
            print("check_inputs failed. Skipping.")
            job.last_error = err_msg
            _finish_job(job, "failed", err_msg)
            return False
            
        _report_job(job, "voice", 35, "Generating voiceover.")
        voice_dur = generate_voiceover(job)
        _check_cancellation(job)
        _report_job(job, "media", 50, "Downloading source media.")
        download_visuals(job, voice_dur)
        _check_cancellation(job)
        
        _report_job(job, "frames", 65, "Building video frames.")
        build_video_frames(job, voice_dur)
        _check_cancellation(job)
        _report_job(job, "render", 80, "Rendering final video.")
        run_ffmpeg(job, voice_dur)
        _check_cancellation(job)
        _report_job(job, "seo", 90, "Writing SEO package.")
        write_seo_package(job)
        _report_job(job, "deliver", 95, "Copying deliverables.")
        copy_deliverables(job)
        _report_job(job, "verify", 97, "Verifying final video and SEO deliverables.")
        verify_deliverable(job)
        cleanup(job)
        _finish_job(job, "succeeded")
        print(f"SUCCESS! Created video: {job.OUTPUT_NAME}.mp4")
        return True
    except JobCancelledError as error:
        job.last_error = str(error)
        print(job.last_error)
        _finish_job(job, "cancelled", job.last_error)
        cleanup(job)
        return False
    except Exception as e:
        err_msg = f"Failed to generate video for topic. Error: {e}"
        print(err_msg)
        job.last_error = err_msg
        _finish_job(job, "failed", err_msg)
        try:
            cleanup(job)
        except Exception:
            pass
        return False

def main():
    if not config.check_system_dependencies():
        sys.exit(1)
        
    parser = argparse.ArgumentParser(description="AI Short Reel Generator")
    parser.add_argument("--topic", type=str, help="Single topic for the video")
    parser.add_argument("--batch", type=str, help="Path to batch topics txt file")
    parser.add_argument("--news-url", type=str, help="Scrape news/article URL or RSS feed to generate reel")
    parser.add_argument("--csv", type=str, help="Path to CSV or Excel batch file")
    parser.add_argument("--provider", type=str, choices=["auto", "openai", "gemini", "groq", "ollama", "openrouter"], default="auto", help="AI provider (auto, openai, gemini, groq, ollama, or openrouter)")
    args = parser.parse_args()

    provider = args.provider
    
    if args.csv:
        try:
            import pandas as pd
        except ImportError:
            print("Error: pandas is required for CSV processing.")
            sys.exit(1)
        csv_path = args.csv
        if not os.path.exists(csv_path):
            print(f"Error: Batch file '{csv_path}' not found.")
            sys.exit(1)
        if csv_path.endswith(".csv"):
            df = pd.read_csv(csv_path)
        else:
            df = pd.read_excel(csv_path)
            
        cols = [str(c).lower() for c in df.columns]
        has_script_cols = ("title" in cols and "caption_text_1" in cols and "narration_text_1" in cols)
        
        print(f"Loaded {len(df)} rows from file. Starting batch generation...")
        for idx, row in df.iterrows():
            row_dict = {k.lower(): v for k, v in row.to_dict().items()}
            def safe_str(value):
                if pd.isna(value):
                    return ""
                return str(value).strip()

            if has_script_cols:
                queries_val = safe_str(row_dict.get("queries", ""))
                queries_list = [q.strip() for q in str(queries_val).split(",") if q.strip()]
                while len(queries_list) < 8:
                    queries_list.append("general visual storytelling")
                queries_list = queries_list[:8]
                captions = [safe_str(row_dict.get(f"caption_text_{i}", "")) for i in range(1, 21)]
                narrations = [safe_str(row_dict.get(f"narration_text_{i}", "")) for i in range(1, 21)]
                captions = [value for value in captions if value]
                narrations = [value for value in narrations if value]
                
                script_data = {
                    "title": safe_str(row_dict.get("title", "")),
                    "year": safe_str(row_dict.get("year", "Unknown")),
                    "bg_music_vibe": safe_str(row_dict.get("bg_music_vibe", "mystery")),
                    "captions": captions,
                    "narrations": narrations,
                    "queries": queries_list,
                    "seo_title": safe_str(row_dict.get("seo_title", f"{safe_str(row_dict.get('title', ''))} — Watch This ✨")),
                    "seo_description": safe_str(row_dict.get("seo_description", "")),
                    "seo_hashtags": safe_str(row_dict.get("seo_hashtags", "#Reels #ShortVideos #ContentCreator")),
                    "seo_short_caption": safe_str(row_dict.get("seo_short_caption", ""))
                }
                print(f"\nProcessing manual script row {idx+1}/{len(df)}: '{script_data['title']}'")
                generate_video_for_topic(None, provider=provider, manual_script_data=script_data)
            else:
                topic_col = None
                for c in df.columns:
                    if c.lower() in ["topic", "topic_title", "title", "name"]:
                        topic_col = c.lower()
                        break
                if not topic_col:
                    if df.empty:
                        continue
                    topic_col = df.columns[0].lower()
                
                topic_val = safe_str(row_dict.get(topic_col))
                if not topic_val or topic_val.lower() == "nan":
                    continue
                
                print(f"\nProcessing topic row {idx+1}/{len(df)}: '{topic_val}'")
                generate_video_for_topic(topic_val, provider=provider)
    elif args.news_url:
        try:
            from history_reels.news_scraper import scrape_article_text, fetch_rss_feed
            # If XML/RSS, pick first link
            url_lower = args.news_url.lower()
            if "xml" in url_lower or "rss" in url_lower or "feed" in url_lower:
                print(f"Fetching RSS feed: {args.news_url}")
                feeds = fetch_rss_feed(args.news_url)
                if feeds:
                    target_url = feeds[0]["link"]
                    print(f"Selected latest article: '{feeds[0]['title']}' -> {target_url}")
                    article_text = scrape_article_text(target_url) or feeds[0]["description"]
                else:
                    raise ValueError("Could not fetch or parse RSS feed.")
            else:
                print(f"Scraping article web page: {args.news_url}")
                article_text = scrape_article_text(args.news_url)
                
            if not article_text or not article_text.strip():
                raise ValueError("Scraped article text is empty.")
                
            generate_video_for_topic(article_text, provider=provider, is_raw_script=True)
        except ValueError as e:
            print(f"News scraping error: {e}")
            return
        except Exception as e:
            print(f"Unexpected scraping error: {e}")
            return
    elif args.topic:
        # Command-line single topic
        generate_video_for_topic(args.topic, provider=provider)
    elif args.batch:
        # Command-line batch file
        batch_path = args.batch
        if not os.path.exists(batch_path):
            print(f"Error: Batch file '{batch_path}' not found.")
            sys.exit(1)
        with open(batch_path, "r", encoding="utf-8") as f:
            topics = [line.strip() for line in f if line.strip() != ""]
        print(f"Loaded {len(topics)} topics from file. Starting batch generation...")
        for idx, t in enumerate(topics, 1):
            print(f"\nProcessing batch topic {idx}/{len(topics)}: '{t}'")
            generate_video_for_topic(t, provider=provider)
    else:
        # Interactive mode
        print("="*60)
        print("         WELCOME TO AI REELS STUDIO")
        print("Select Generation Mode:")
        print("1. Single Video Generation")
        print("2. Batch Video Generation (Multiple Topics)")
        print("3. Run Fallback Mode (Universal Creator Demo)")
        
        choice = input("Enter choice (1-3): ").strip()
        
        if choice == "1":
            topic = input("Enter the topic for your video (e.g. 5 productivity tips): ").strip()
            if topic == "":
                print("Error: Topic cannot be empty.")
                sys.exit(1)
            generate_video_for_topic(topic, provider=provider)
        elif choice == "2":
            print("\nEnter multiple topics separated by commas (e.g. study tips, home workout, travel guide):")
            topics_input = input("Topics: ").strip()
            if topics_input == "":
                print("Error: Topics list cannot be empty.")
                sys.exit(1)
            topics = [t.strip() for t in topics_input.split(",") if t.strip() != ""]
            print(f"\nStarting batch generation of {len(topics)} videos...")
            for idx, t in enumerate(topics, 1):
                print(f"\n[Batch {idx}/{len(topics)}] Generation: '{t}'")
                generate_video_for_topic(t, provider=provider)
        elif choice == "3":
            generate_video_for_topic(None, provider=provider)
        else:
            print("Invalid choice. Exiting.")
            sys.exit(1)
