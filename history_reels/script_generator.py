import json
import requests
from typing import List
from pydantic import BaseModel, Field, field_validator
from history_reels import config

class ScriptConfig(BaseModel):
    title: str = Field(..., min_length=1)
    year: str = Field(..., min_length=1)
    bg_music_vibe: str = Field(..., min_length=1)
    caption_text_1: str = Field(..., min_length=1)
    caption_text_2: str = Field(..., min_length=1)
    caption_text_3: str = Field(..., min_length=1)
    caption_text_4: str = Field(..., min_length=1)
    narration_text_1: str = Field(..., min_length=1)
    narration_text_2: str = Field(..., min_length=1)
    narration_text_3: str = Field(..., min_length=1)
    narration_text_4: str = Field(..., min_length=1)
    queries: List[str] = Field(...)
    seo_title: str = Field(..., min_length=1)
    seo_description: str = Field(..., min_length=1)
    seo_hashtags: str = Field(..., min_length=1)
    seo_short_caption: str = Field(..., min_length=1)

    @field_validator("bg_music_vibe")
    @classmethod
    def validate_vibe(cls, v):
        allowed = ["mystery", "epic", "sad", "ancient"]
        if v.lower() not in allowed:
            raise ValueError(f"bg_music_vibe must be one of {allowed}")
        return v.lower()

    @field_validator("queries")
    @classmethod
    def validate_queries(cls, v):
        if len(v) != 8:
            raise ValueError("Exactly 8 queries must be provided.")
        for q in v:
            if not q or not q.strip():
                raise ValueError("Queries cannot contain empty strings.")
        return v

def fetch_ai_script(topic, provider="gemini"):
    system_prompt = (
        "You are an expert history documentary scriptwriter. Generate script configuration for Urdu short reels in JSON format. "
        "The output must strictly follow this JSON schema:\n"
        "{\n"
        "  \"title\": \"Short English Title (e.g., Giza Pyramids)\",\n"
        "  \"year\": \"Historical Era/Year (e.g., 2560 BCE)\",\n"
        "  \"bg_music_vibe\": \"One of: mystery, epic, sad, ancient\",\n"
        "  \"caption_text_1\": \"Urdu Nastaliq formatted text for Slide 1 (max 3 lines, use bold markdown **word** for key terms, use Zer diacritic like 'کِیا' for the word kiya)\",\n"
        "  \"caption_text_2\": \"Urdu Nastaliq formatted text for Slide 2 (max 3 lines, use bold markdown **word** for key terms)\",\n"
        "  \"caption_text_3\": \"Urdu Nastaliq formatted text for Slide 3 (max 3 lines, use bold markdown **word** for key terms)\",\n"
        "  \"caption_text_4\": \"Urdu Nastaliq formatted text for Slide 4 (max 3 lines, use bold markdown **word** for key terms)\",\n"
        "  \"narration_text_1\": \"Urdu narration text corresponding exactly to Slide 1 (approx 7-9 seconds long, use Zer diacritic like 'کِیا' for the word kiya)\",\n"
        "  \"narration_text_2\": \"Urdu narration text corresponding exactly to Slide 2 (approx 7-9 seconds long)\",\n"
        "  \"narration_text_3\": \"Urdu narration text corresponding exactly to Slide 3 (approx 7-9 seconds long)\",\n"
        "  \"narration_text_4\": \"Urdu narration text corresponding exactly to Slide 4 (approx 7-9 seconds long)\",\n"
        "  \"queries\": [\n"
        "    \"8 specific search queries (only list exactly 8 queries) for Pexels stock video matching the script flow, e.g. ['giza plateau', 'desert pyramids', 'ancient stone blocks', 'workers building', 'pharaoh statue', 'camel walking', 'ancient map', 'sunset pyramids']\"\n"
        "  ],\n"
        "  \"seo_title\": \"Hook/Title for social media (e.g., Pyramids of Giza — Secrets of the Pharaohs 🏺✨)\",\n"
        "  \"seo_description\": \"Detailed social media caption containing Roman Urdu narrative summary and Urdu script summary\",\n"
        "  \"seo_hashtags\": \"Space-separated string of 8-12 relevant hashtags (e.g., '#History #GizaPyramids #Egypt #UrduMysteries')\",\n"
        "  \"seo_short_caption\": \"A short punchy caption for quick copy-paste\"\n"
        "}"
    )

    if provider == "gemini":
        print(f"Calling Google Gemini 1.5 Flash to auto-generate script for topic: '{topic}'...")
        if not config.GEMINI_API_KEY:
            raise ValueError("Error: GEMINI_API_KEY environment variable is not set. Please set it in your .env file.")
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={config.GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        prompt_text = f"{system_prompt}\n\nGenerate script configuration in valid JSON format for topic: {topic}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt_text}
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        try:
            raw_text = result["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(raw_text)
            validated = ScriptConfig(**parsed)
            return validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()
        except Exception as e:
            raise ValueError(f"Failed to parse or validate Gemini API response: {e}. Raw response: {result}")
            
    else:
        print(f"Calling OpenAI GPT-4o-mini to auto-generate script for topic: '{topic}'...")
        if not config.OPENAI_API_KEY:
            raise ValueError("Error: OPENAI_API_KEY environment variable is not set. Please set it in your .env file.")
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "gpt-4o-mini",
            "response_format": { "type": "json_object" },
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Topic: {topic}"}
            ]
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        validated = ScriptConfig(**parsed)
        return validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()
