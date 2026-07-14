import os
import subprocess
import requests
import shutil
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.environ.get("FISH_AUDIO_API_KEY")
TEMP_DIR = r"C:\Users\lenovo\Downloads\history_reels_tmp"
VOICE_ID_FILE = r"C:\Users\lenovo\Pictures\history videos\fish_voice_id.txt"

# Videos to extract samples from
VIDEOS = [
    ("https://www.youtube.com/watch?v=aHB1WaW70i8", [("chunk1.mp3", "30.0"), ("chunk2.mp3", "60.0"), ("chunk3.mp3", "90.0"), ("chunk4.mp3", "120.0")]),
    ("https://www.youtube.com/watch?v=j-XwFQWZZQo", [("chunk5.mp3", "40.0"), ("chunk6.mp3", "70.0")])
]

def main():
    os.makedirs(TEMP_DIR, exist_ok=True)
    sliced_files = []
    
    # Check if chunks 1-6 already exist in TEMP_DIR
    for i in range(1, 7):
        filepath = os.path.join(TEMP_DIR, f"chunk{i}.mp3")
        if os.path.exists(filepath):
            sliced_files.append(filepath)
            print(f"chunk{i}.mp3 already exists. Skipping extraction.")

    # Process videos
    for video_url, chunks_config in VIDEOS:
        # Check if we need to download this video (if at least one of its chunks is missing)
        need_download = False
        for filename, _ in chunks_config:
            if os.path.join(TEMP_DIR, filename) not in sliced_files:
                need_download = True
                break
                
        if not need_download:
            continue
            
        print(f"\nProcessing video: {video_url}...")
        raw_audio = os.path.join(TEMP_DIR, "temp_video.mp4")
        
        cmd_dl = [
            "yt-dlp",
            "--extractor-args", "youtube:player_client=android",
            "-f", "best",
            "-o", raw_audio,
            video_url
        ]
        
        try:
            subprocess.run(cmd_dl, check=True)
            print("Video downloaded successfully.")
        except Exception as e:
            print(f"Failed to download video: {e}")
            continue
            
        for filename, start in chunks_config:
            out_path = os.path.join(TEMP_DIR, filename)
            if os.path.exists(out_path):
                continue
                
            cmd_slice = [
                "ffmpeg", "-y", "-ss", start, "-i", raw_audio, "-t", "20.0",
                "-c:a", "libmp3lame", "-b:a", "192k", out_path
            ]
            try:
                subprocess.run(cmd_slice, check=True)
                sliced_files.append(out_path)
                print(f"Sliced {filename} starting at {start}s")
            except Exception as e:
                print(f"Failed to slice {filename}: {e}")
                
        if os.path.exists(raw_audio):
            os.remove(raw_audio)

    if len(sliced_files) < 4:
        print("Not enough voice chunks sliced. Aborting.")
        return
        
    print(f"\nUploading {len(sliced_files)} Urdu samples to Fish Audio...")
    url = "https://api.fish.audio/model"
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }
    
    files_payload = []
    opened_files = []
    try:
        for filepath in sliced_files:
            f = open(filepath, "rb")
            opened_files.append(f)
            files_payload.append(("voices", (os.path.basename(filepath), f, "audio/mpeg")))
            
        data = {
            "title": "ZemTV Ultra Cloned Voice",
            "visibility": "private",
            "type": "tts",
            "train_mode": "fast"
        }
        
        response = requests.post(url, headers=headers, files=files_payload, data=data)
        
        if response.status_code in [200, 201]:
            res_data = response.json()
            voice_id = res_data.get("_id") or res_data.get("id")
            print(f"SUCCESS! Advanced Voice model created.")
            print(f"Voice ID: {voice_id}")
            print(f"Response: {res_data}")
            
            with open(VOICE_ID_FILE, "w", encoding="utf-8") as f_id:
                f_id.write(voice_id)
            print(f"Saved new voice ID to {VOICE_ID_FILE}")
        else:
            print(f"Failed to create model. Status code: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"Error during API request: {e}")
    finally:
        for f in opened_files:
            f.close()

if __name__ == "__main__":
    main()
