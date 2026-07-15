import os
import sys
import subprocess
import time

def run_command(cmd, shell=True):
    print(f"\n>>> Running: {cmd}")
    subprocess.run(cmd, shell=shell)

print("🚀 Starting Automatic Setup for History Reels Builder...")
print("======================================================")

# 1. Install FFmpeg if not present
try:
    subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    print("✅ FFmpeg is already installed.")
except Exception:
    print("⚠️ FFmpeg not found! Installing via winget (Please wait)...")
    run_command("winget install Gyan.FFmpeg --accept-source-agreements --accept-package-agreements")

# 2. Install Python Requirements
print("\n📦 Installing Python dependencies...")
run_command(f'"{sys.executable}" -m pip install -r requirements.txt')

# 3. Create required folders
print("\n📁 Creating Asset folders...")
user_profile = os.environ.get("USERPROFILE", "")
pictures_dir = os.path.join(user_profile, "Pictures", "history videos")
os.makedirs(os.path.join(pictures_dir, "bg_music"), exist_ok=True)
os.makedirs(os.path.join(pictures_dir, "fonts"), exist_ok=True)
print(f"✅ Created: {pictures_dir}")

# 4. Create Desktop Shortcut (Batch File)
print("\n🔗 Creating Desktop Shortcut...")
desktop_dir = os.path.join(user_profile, "Desktop")
shortcut_path = os.path.join(desktop_dir, "Start Reels Builder.bat")
current_dir = os.path.abspath(os.path.dirname(__file__))

bat_content = f\"\"\"@echo off
title AI Reels Builder
echo Starting AI Content Engine...
cd /d "{current_dir}"
python -m streamlit run app.py
pause
\"\"\"
with open(shortcut_path, "w", encoding="utf-8") as f:
    f.write(bat_content)
print(f"✅ Shortcut created at: {shortcut_path}")

# 5. Launch the App
print("\n🎉 Setup Complete! Launching the Dashboard now...")
print("If the browser does not open, double-click the 'Start Reels Builder' shortcut on your Desktop.")
time.sleep(3)
subprocess.Popen(f'"{sys.executable}" -m streamlit run app.py', shell=True)