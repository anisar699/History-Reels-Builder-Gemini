import os
import sys
import shutil
import argparse
import random
import requests

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass
from history_reels import config
from history_reels.jobs import GenerationJob, create_generation_job
from history_reels.script_generator import fetch_ai_script
from history_reels.stock_media import download_clip_for_query
from history_reels.voiceover import generate_voiceover
from history_reels.renderer import build_video_frames, run_ffmpeg
from history_reels.seo import write_seo_package

def download_file(url, path):
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, stream=True, timeout=30)
    r.raise_for_status()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)

def ensure_assets(job: GenerationJob):
    # Make sure target directories exist
    os.makedirs(os.path.dirname(job.FONT_PATH), exist_ok=True)
    os.makedirs(job.MUSIC_DIR, exist_ok=True)
    
    # 1. Ensure Urdu Font exists
    font_name = getattr(job, "URDU_FONT_NAME", "Jameel Noori Nastaleeq")
    job.FONT_PATH = os.path.join(job.ASSETS_DIR, f"{font_name}.ttf")
    
    if not os.path.exists(job.FONT_PATH):
        print(f"Urdu Font '{font_name}' not found at {job.FONT_PATH}. Auto-downloading...")
        font_urls = {
            "Noto Nastaliq Urdu": "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoNastaliqUrdu/NotoNastaliqUrdu-Bold.ttf",
            "Jameel Noori Nastaleeq": "https://raw.githubusercontent.com/abid-mujtaba/ttf-jameel-noori-nastaleeq/master/Jameel%20Noori%20Nastaleeq.ttf"
        }
        font_url = font_urls.get(font_name, font_urls["Jameel Noori Nastaleeq"])
        try:
            download_file(font_url, job.FONT_PATH)
            print(f"Successfully downloaded {font_name} Font!")
        except Exception as e:
            print(f"Failed to download Urdu font: {e}")
    # 2. Ensure Background Music pool exists
    track_name = f"{job.BG_MUSIC_VIBE}_{job.BG_MUSIC_TRACK_INDEX}"
    target_music_path = os.path.join(job.MUSIC_DIR, f"{track_name}.mp3")
    
    if not os.path.exists(target_music_path):
        print(f"Background music track '{track_name}.mp3' not found. Auto-downloading...")
        music_urls = {
            f"{vibe}_{i}": f"https://archive.org/download/ambient-cinematic-music-royalty-free/Cinematic_Ambient_Music_{i}.mp3"
            for vibe in ["mystery", "epic", "sad", "ancient"] for i in range(1, 6)
        }
        download_url = music_urls.get(track_name)
        if download_url:
            try:
                download_file(download_url, target_music_path)
                print(f"Successfully downloaded background music: {track_name}.mp3")
            except Exception as e:
                print(f"Failed to download music track: {e}")
        
        # If download failed or no URL was available for this vibe, generate silent fallback
        if not os.path.exists(target_music_path):
            print(f"Generating silent fallback music for {track_name} to prevent crashes...")
            try:
                import subprocess
                subprocess.run([
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-t", "60", "-q:a", "9", "-acodec", "libmp3lame", target_music_path
                ], check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as ex:
                print(f"Failed to generate silent fallback: {ex}")

def check_inputs(job: GenerationJob):
    os.makedirs(job.TOPIC_TEMP_DIR, exist_ok=True)
    os.makedirs(job.OUTPUT_DIR, exist_ok=True)
    
    ensure_assets(job)
    
    if not os.path.exists(job.FONT_PATH):
        print(f"Error: Urdu Font not found at {job.FONT_PATH}")
        return False
        
    music_mp3 = os.path.join(job.MUSIC_DIR, f"{job.BG_MUSIC_VIBE}_{job.BG_MUSIC_TRACK_INDEX}.mp3")
    if not os.path.exists(music_mp3):
        existing_tracks = [f for f in os.listdir(job.MUSIC_DIR) if f.endswith(".mp3")]
        if existing_tracks:
            fallback_track = os.path.join(job.MUSIC_DIR, existing_tracks[0])
            print(f"Warning: Selected music track not found. Using fallback: {existing_tracks[0]}")
            shutil.copy2(fallback_track, music_mp3)
        else:
            print(f"Error: Music file {music_mp3} not found and no fallbacks available!")
            return False

    return True

def download_visuals(job: GenerationJob, voice_dur):
    print(f"\n--- Downloading Media based on Voice Duration ({voice_dur:.1f}s) ---")
    pacing = getattr(job, "CLIP_DURATION_TARGET", 5.0)
    
    import math
    required_clips = math.ceil(voice_dur / pacing)
    
    expanded_queries = []
    while len(expanded_queries) < required_clips:
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
    job.QUERIES = successful_queries

def copy_deliverables(job: GenerationJob):
    final_video = job.video_path
    final_txt = job.seo_path
    
    print(f"Copying final files to {job.OUTPUT_DIR}...")
    
    src_video = os.path.join(job.TOPIC_TEMP_DIR, "output.mp4")
    src_txt = os.path.join(job.TOPIC_TEMP_DIR, "output.txt")
    
    if not os.path.exists(src_video):
        print(f"Error: output.mp4 not found in {job.TOPIC_TEMP_DIR}. Pipeline may have failed.")
        return False
    
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
                item_clean = item.replace("\\", "/")
                f.write(f"file '{item_clean}'\n")
                
        stitched_video = os.path.join(job.TOPIC_TEMP_DIR, "stitched_output.mp4")
        cmd_concat = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_txt, "-c", "copy", stitched_video]
        subprocess.run(cmd_concat, check=True, stdin=subprocess.DEVNULL)
        
        shutil.copy2(stitched_video, final_video)
    else:
        shutil.copy2(src_video, final_video)
        
    if os.path.exists(src_txt):
        shutil.copy2(src_txt, final_txt)
    print("Deliverables copied.")

def cleanup(job: GenerationJob):
    print("Cleaning up temporary topic files...")
    if os.path.exists(job.TOPIC_TEMP_DIR) and job.TOPIC_TEMP_DIR != job.TEMP_DIR:
        try:
            shutil.rmtree(job.TOPIC_TEMP_DIR)
            print("Cleanup complete.")
        except Exception as e:
            print(f"Cleanup warning: {e}")

def generate_video_for_topic(topic, provider="gemini", manual_script_data=None, is_raw_script=False, job=None):
    """Generate one reel using only the supplied job's state and workspace."""
    job = job or create_generation_job(config)
    job.reset_runtime_state()
    try:
        job.prepare_workspace()
    except FileExistsError:
        job.last_error = f"Job workspace already exists: {job.TOPIC_TEMP_DIR}"
        print(job.last_error)
        return False

    is_valid_topic = False
    if isinstance(topic, str) and topic.strip() != "":
        is_valid_topic = True
    elif isinstance(topic, dict) and topic:
        is_valid_topic = True

    if is_valid_topic or manual_script_data:
        print(f"\n--- Generating Video (Manual/API Mode) ---")
        try:
            if manual_script_data:
                print("Using manually entered script configuration...")
                from history_reels.script_generator import ScriptConfig
                try:
                    validated = ScriptConfig(**manual_script_data)
                    ai_data = validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()
                except Exception as e:
                    print(f"Error: Invalid manual script data - {e}")
                    job.last_error = f"Validation Error: {e}"
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
            print(f"Video Search Queries: {job.QUERIES}")
            print("====================================\n")
        except Exception as e:
            err_msg = f"Error fetching AI script: {e}"
            print(f"Error fetching AI script, skipping topic '{topic}'. Error: {e}")
            job.last_error = err_msg
            return False
    else:
        print("\n--- Running Fallback Mode (Baghdad Battery) ---")
        job.TOPIC_TITLE = "Baghdad Battery"
        job.TOPIC_YEAR = "250 BC"
        job.OUTPUT_NAME = f"Baghdad Battery 250 BC Asad Voice {job.short_id}"
        job.QUERIES = ["ancient mesopotamia", "parthian empire", "ancient battery", "archaeology discovery", "ancient electricity", "clay jar", "copper cylinder", "iron rod"]
        
    try:
        if not check_inputs(job):
            err_msg = "Input validation failed. Please ensure all required API keys are configured and local audio assets are downloaded."
            print("check_inputs failed. Skipping.")
            job.last_error = err_msg
            return False
            
        voice_dur = generate_voiceover(job)
        download_visuals(job, voice_dur)
        
        build_video_frames(job, voice_dur)
        run_ffmpeg(job, voice_dur)
        write_seo_package(job)
        copy_deliverables(job)
        cleanup(job)
        print(f"SUCCESS! Created video: {job.OUTPUT_NAME}.mp4")
        return True
    except Exception as e:
        err_msg = f"Failed to generate video for topic. Error: {e}"
        print(err_msg)
        job.last_error = err_msg
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
        import pandas as pd
        csv_path = args.csv
        if not os.path.exists(csv_path):
            print(f"Error: Batch file '{csv_path}' not found.")
            sys.exit(1)
        if csv_path.endswith(".csv"):
            df = pd.read_csv(csv_path)
        else:
            df = pd.read_excel(csv_path)
            
        cols = [c.lower() for c in df.columns]
        has_script_cols = ("title" in cols and "caption_text_1" in cols and "narration_text_1" in cols)
        
        print(f"Loaded {len(df)} rows from file. Starting batch generation...")
        for idx, row in df.iterrows():
            row_dict = {k.lower(): v for k, v in row.to_dict().items()}
            if has_script_cols:
                queries_val = row_dict.get("queries", "")
                if pd.isna(queries_val):
                    queries_val = ""
                queries_list = [q.strip() for q in str(queries_val).split(",") if q.strip()]
                while len(queries_list) < 8:
                    queries_list.append("history")
                queries_list = queries_list[:8]
                
                script_data = {
                    "title": str(row_dict.get("title", "")).strip(),
                    "year": str(row_dict.get("year", "Unknown")).strip(),
                    "bg_music_vibe": str(row_dict.get("bg_music_vibe", "mystery")).strip(),
                    "caption_text_1": str(row_dict.get("caption_text_1", "")).strip(),
                    "caption_text_2": str(row_dict.get("caption_text_2", "")).strip(),
                    "caption_text_3": str(row_dict.get("caption_text_3", "")).strip(),
                    "caption_text_4": str(row_dict.get("caption_text_4", "")).strip(),
                    "narration_text_1": str(row_dict.get("narration_text_1", "")).strip(),
                    "narration_text_2": str(row_dict.get("narration_text_2", "")).strip(),
                    "narration_text_3": str(row_dict.get("narration_text_3", "")).strip(),
                    "narration_text_4": str(row_dict.get("narration_text_4", "")).strip(),
                    "queries": queries_list,
                    "seo_title": str(row_dict.get("seo_title", f"{row_dict.get('title', '')} — Secrets of the Past 🏺✨")).strip(),
                    "seo_description": str(row_dict.get("seo_description", "")).strip(),
                    "seo_hashtags": str(row_dict.get("seo_hashtags", "#History #Urdu")).strip(),
                    "seo_short_caption": str(row_dict.get("seo_short_caption", "")).strip()
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
                    topic_col = df.columns[0].lower()
                
                def safe_str(val):
                    if pd.isna(val): return ""
                    return str(val).strip()
                topic_val = safe_str(row_dict.get(topic_col))
                if not topic_val or topic_val.lower() == "nan": continue
                
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
        print("         WELCOME TO HISTORY REELS BUILDER AUTO-PILOT")
        print("="*60)
        print("Select Generation Mode:")
        print("1. Single Video Generation")
        print("2. Batch Video Generation (Multiple Topics)")
        print("3. Run Fallback Mode (Baghdad Battery Demo)")
        
        choice = input("Enter choice (1-3): ").strip()
        
        if choice == "1":
            topic = input("Enter the topic for your video (e.g. Titanic): ").strip()
            if topic == "":
                print("Error: Topic cannot be empty.")
                sys.exit(1)
            generate_video_for_topic(topic, provider=provider)
        elif choice == "2":
            print("\nEnter multiple topics separated by commas (e.g. Taj Mahal, Pyramids, Titanic):")
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
