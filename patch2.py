import os

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

block_to_move = """    
        media_selection = st.selectbox(
            "Media Type Preference",
            options=["Mixed (Videos + Images)", "Videos Only", "Images Only"],
            index=0,
            help="Select preference for source assets: Mixed (videos first, images fallback), Videos Only, or Images Only (useful for vintage photos)."
        )
    
        pref_mapping = {
            "Mixed (Videos + Images)": "mixed",
            "Videos Only": "videos",
            "Images Only": "images"
        }
        config.MEDIA_PREFERENCE = pref_mapping[media_selection]

        quality_selection = st.selectbox(
            "Media Quality Profile",
            options=["Balanced (recommended)", "High quality (slower, stricter)"],
            index=0,
            help="Filters out low-resolution source videos before download. High quality may return fewer results for niche topics."
        )
        config.MEDIA_QUALITY_PROFILE = "high" if quality_selection.startswith("High") else "balanced"
        config.MIN_MEDIA_DIMENSION = 720 if config.MEDIA_QUALITY_PROFILE == "high" else 480
    
        st.markdown("**Allowed Media Sources**", help="Check the stock sites you want to fetch media from.")
        sources_list = ["Pexels (Videos)", "Pixabay (Videos)", "Storyblocks (Videos)", "Google/Bing (Images)", "Wikimedia Commons (Images)", "NASA (Images)", "Internet Archive (Videos)", "Unsplash (Images)"]
        default_sources = ["Pexels (Videos)", "Pixabay (Videos)", "Google/Bing (Images)", "Wikimedia Commons (Images)"]
        allowed_sources = []
        
        cols = st.columns(2)
        for i, source in enumerate(sources_list):
            with cols[i % 2]:
                if st.checkbox(source, value=(source in default_sources)):
                    allowed_sources.append(source)
    
        source_mapping = {
            "Pexels (Videos)": "pexels",
            "Pixabay (Videos)": "pixabay",
            "Storyblocks (Videos)": "storyblocks",
            "Google/Bing (Images)": "google",
            "Wikimedia Commons (Images)": "wikimedia_image",
            "NASA (Images)": "nasa_image",
            "Internet Archive (Videos)": "archive",
            "Unsplash (Images)": "unsplash"
        }
        config.ALLOWED_SOURCES = [source_mapping[s] for s in allowed_sources]"""

target_insertion = """    with st.expander("🎬 Visuals & Transitions", expanded=False):"""

if block_to_move in content and target_insertion in content:
    content = content.replace(block_to_move, "")
    content = content.replace(target_insertion, target_insertion + "\n" + block_to_move + "\n        st.markdown('---')")
    
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('SUCCESS')
else:
    print('FAILED: Could not find blocks')
