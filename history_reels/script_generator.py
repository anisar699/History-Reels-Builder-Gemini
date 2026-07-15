import json
import re
import requests
from typing import List
from pydantic import BaseModel, Field, field_validator
from history_reels import config

def parse_json_response(content):
    if not content:
        raise ValueError("Model returned an empty response.")
    content_str = content.strip()
    try:
        return json.loads(content_str)
    except Exception as primary_err:
        cleaned = content_str
        if cleaned.startswith("```"):
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s*```$', '', cleaned)
        try:
            return json.loads(cleaned)
        except Exception:
            pass
            
        start = content_str.find('{')
        end = content_str.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                content_str = content_str[start:end+1]
                return json.loads(content_str)
            except Exception:
                pass
                
        raise ValueError(f"Failed to decode JSON from model response. Error: {primary_err}. Raw output: {content_str[:300]}")

class ScriptConfig(BaseModel):
    title: str = Field(default="")
    year: str = Field(default="")
    bg_music_vibe: str = Field(default="mystery")
    captions: List[str] = Field(default_factory=list)
    narrations: List[str] = Field(default_factory=list)
    queries: List[str] = Field(default_factory=list)
    seo_title: str = Field(default="")
    seo_description: str = Field(default="")
    seo_hashtags: str = Field(default="")
    seo_short_caption: str = Field(default="")

    @field_validator("bg_music_vibe")
    @classmethod
    def validate_vibe(cls, v):
        val = str(v).lower().strip()
        allowed = ["mystery", "epic", "sad", "ancient", "modern", "intense"]
        if val not in allowed:
            return "mystery"
        return val

    @field_validator("queries")
    @classmethod
    def validate_queries(cls, v):
        if not isinstance(v, list):
            v = []
        cleaned = []
        for q in v:
            val = str(q).strip()
            if val:
                cleaned.append(val)
        while len(cleaned) < 8:
            cleaned.append("cinematic")
        return cleaned

def fetch_ai_script(topic, provider="gemini", is_raw_script=False):
    provider = str(provider).strip().lower()
    schema_details = (
        "{\n"
        "  \"title\": \"Short English Title (e.g., AI Revolution, Giza Pyramids)\",\n"
        "  \"year\": \"Context or Era (e.g., 2024, Cyberpunk, 2560 BCE)\",\n"
        "  \"bg_music_vibe\": \"One of: mystery, epic, sad, ancient, modern, intense\",\n"
        "  \"captions\": [\"Urdu text for Slide 1...\", \"Urdu text for Slide 2...\", \"...generate as many as needed to reach target duration\"],\n"
        "  \"narrations\": [\"Urdu narration for Slide 1...\", \"Urdu narration for Slide 2...\", \"...must match number of captions\"],\n"
        "  \"queries\": [\n"
        "    \"specific search queries for stock video/images matching the script flow, e.g. ['giza plateau', 'neon city', 'hacker typing', 'space shuttle', 'pharaoh statue', 'cyber security', 'ancient map', 'cinematic landscape']\"\n"
        "  ],\n"
        "  \"seo_title\": \"Hook/Title for social media (e.g., Pyramids of Giza — Secrets of the Pharaohs 🏺✨)\",\n"
        "  \"seo_description\": \"Detailed social media caption containing Roman Urdu narrative summary and Urdu script summary\",\n"
        "  \"seo_hashtags\": \"Space-separated string of 8-12 relevant hashtags (e.g., '#History #GizaPyramids #Egypt #UrduMysteries')\",\n"
        "  \"seo_short_caption\": \"A short punchy caption for quick copy-paste\"\n"
        "}"
    )

    target_dur = getattr(config, "TARGET_DURATION", None)
    if target_dur:
        num_slides = int(target_dur / 5.0)
        duration_instruction = f"IMPORTANT: The user requested a target video duration of {target_dur} seconds. You MUST generate approximately {num_slides} items in the captions, narrations, and queries arrays."
    else:
        duration_instruction = "IMPORTANT: Generate exactly as many captions, narrations, and queries as needed."

    if is_raw_script:
        system_prompt = (
            "You are an expert short-form viral video producer. Your task is to take the provided raw narrative script (which can be in Urdu, English, or Roman Urdu) "
            "and format/split it into logical slides matching the required JSON format. Ensure captions are in Nastaliq-friendly Urdu. "
            f"{duration_instruction} The output must strictly follow this JSON schema:\n{schema_details}"
        )
        user_prompt = f"Structure this raw script text into the JSON format:\n{topic}"
    else:
        system_prompt = (
            "You are an expert short-form viral video producer and scriptwriter. Generate a highly engaging script configuration for Urdu short reels on ANY given topic (e.g. Tech, Facts, Horror, Motivation, History, etc.) in JSON format. "
            f"{duration_instruction} The output must strictly follow this JSON schema:\n{schema_details}"
        )
        user_prompt = f"Generate script configuration in valid JSON format for topic: {topic}"

    if provider == "auto":
        print("\n[Auto Fallback Mode] Attempting to find the best available AI provider...")
        chain = ["gemini", "groq", "openrouter", "openai", "ollama"]
        last_error = None
        for p in chain:
            if p == "gemini" and not config.GEMINI_API_KEY: continue
            if p == "groq" and not config.GROQ_API_KEY: continue
            if p == "openrouter" and not config.OPENROUTER_API_KEY: continue
            if p == "openai" and not config.OPENAI_API_KEY: continue
            
            try:
                print(f"--> Trying {p.upper()}...")
                return fetch_ai_script(topic, provider=p, is_raw_script=is_raw_script)
            except Exception as e:
                print(f"    [X] {p.upper()} failed: {e}")
                last_error = e
        raise RuntimeError(f"All Auto-Fallback providers failed. Last error: {last_error}")

    if provider == "gemini":
        print(f"Calling Google Gemini 2.0 Flash to auto-generate script...")
        if not config.GEMINI_API_KEY:
            raise ValueError("Error: GEMINI_API_KEY environment variable is not set. Please set it in your .env file.")
        
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        headers = {
            "x-goog-api-key": config.GEMINI_API_KEY,
            "Content-Type": "application/json"
        }
        prompt_text = f"{system_prompt}\n\n{user_prompt}"
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
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error: {e}")
        result = response.json()
        
        try:
            raw_text = result["candidates"][0]["content"]["parts"][0]["text"]
            parsed = parse_json_response(raw_text)
            validated = ScriptConfig(**parsed)
            return validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()
        except Exception as e:
            raise ValueError(f"Failed to parse or validate Gemini API response: {e}. Raw response: {result}")
            
    elif provider == "openai":
        print(f"Calling OpenAI GPT-4o-mini to auto-generate script...")
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
                {"role": "user", "content": user_prompt}
            ]
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error: {e}")
        result = response.json()
        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Unexpected API response from {provider}: {e}")
        parsed = parse_json_response(content)
        validated = ScriptConfig(**parsed)
        return validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()

    elif provider == "groq":
        print(f"Calling Groq llama-3.3-70b-versatile to auto-generate script...")
        if not config.GROQ_API_KEY:
            raise ValueError("Error: GROQ_API_KEY environment variable is not set. Please set it in your .env file.")
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "llama-3.3-70b-versatile",
            "response_format": { "type": "json_object" },
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error: {e}")
        result = response.json()
        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Unexpected API response from {provider}: {e}")
        parsed = parse_json_response(content)
        validated = ScriptConfig(**parsed)
        return validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()

    elif provider == "ollama":
        ollama_model = getattr(config, "OLLAMA_MODEL", "qwen2.5:3b")
        print(f"Calling Local Ollama ({ollama_model}) to auto-generate script...")
        url = "http://localhost:11434/api/chat"
        payload = {
            "model": ollama_model,
            "format": "json",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False
        }
        try:
            response = requests.post(url, json=payload, timeout=300)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error: {e}")
        result = response.json()
        try:
            content = result["message"]["content"]
        except (KeyError, TypeError) as e:
            raise RuntimeError(f"Unexpected API response from Ollama: {e}. Raw: {result}")
        parsed = parse_json_response(content)
        validated = ScriptConfig(**parsed)
        return validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()

    elif provider == "openrouter":
        print(f"Calling OpenRouter Llama 3.3 70B to auto-generate script...")
        if not config.OPENROUTER_API_KEY:
            raise ValueError("Error: OPENROUTER_API_KEY environment variable is not set. Please set it in your .env file.")
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://github.com/anisar699/History-Reels-Builder-Gemini",
            "X-Title": "History Reels Builder",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "meta-llama/llama-3.3-70b-instruct",
            "response_format": { "type": "json_object" },
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error: {e}")
        result = response.json()
        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Unexpected API response from {provider}: {e}")
        parsed = parse_json_response(content)
        validated = ScriptConfig(**parsed)
        return validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()

    else:
        raise ValueError(f"Unknown AI content provider: {provider}")
