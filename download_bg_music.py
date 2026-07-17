import os
import subprocess

HOME = os.path.expanduser("~")
MUSIC_DIR = os.path.join(HOME, "Pictures", "history videos", "bg_music")

CATEGORIES = {
    "mystery": "cinematic mystery background music no copyright",
    "epic": "epic orchestral cinematic background music no copyright",
    "sad": "sad emotional cinematic background music no copyright",
    "ancient": "traditional acoustic cinematic background music no copyright"
}

def download_music():
    os.makedirs(MUSIC_DIR, exist_ok=True)
    print(f"Target background music directory: {MUSIC_DIR}")
    
    for category, query in CATEGORIES.items():
        print(f"\n==================================================")
        print(f"SEARCHING & DOWNLOADING FOR CATEGORY: {category.upper()}")
        print(f"==================================================")
        
        # Search for top 5 videos in this category and download as audio
        # Using yt-dlp
        for i in range(1, 6):
            output_file = os.path.join(MUSIC_DIR, f"{category}_{i}.mp3")
            if os.path.exists(output_file):
                print(f"{category}_{i}.mp3 already exists. Skipping.")
                continue
                
            print(f"Searching and downloading track {i} for '{category}'...")
            
            # Search query with index filter
            # Using yt-dlp to search and download
            try:
                cmd_item = [
                    "yt-dlp",
                    "--extractor-args", "youtube:player_client=android",
                    "-f", "best",
                    "--match-filter", "duration < 600",
                    "--extract-audio",
                    "--audio-format", "mp3",
                    "--audio-quality", "0",
                    "--playlist-items", str(i),
                    "-o", os.path.join(MUSIC_DIR, f"{category}_{i}.%(ext)s"),
                    f"ytsearch5:{query}"
                ]
                subprocess.run(cmd_item, check=True)
                print(f"Successfully downloaded {category}_{i}.mp3")
            except Exception as e:
                print(f"Failed to download track {i} for {category}: {e}")

if __name__ == "__main__":
    download_music()
