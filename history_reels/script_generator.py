import json
import re
import requests
from typing import List
from pydantic import BaseModel, Field, field_validator, model_validator
from history_reels import config


def build_api_request_error(provider, response, error):
    """Build a useful API error without exposing request headers or credentials."""
    status = getattr(response, "status_code", None)
    error_code = ""
    if response is not None:
        try:
            payload = response.json()
            detail = payload.get("error", payload) if isinstance(payload, dict) else {}
            if isinstance(detail, dict):
                error_code = str(detail.get("code") or detail.get("type") or "").strip()
        except (ValueError, TypeError):
            pass

    safe_code = re.sub(r"[^A-Za-z0-9_.-]", "", error_code)[:80]
    request_id = ""
    if response is not None:
        request_id = re.sub(
            r"[^A-Za-z0-9_-]", "", str(response.headers.get("x-request-id", ""))
        )[:128]
    request_suffix = f" Request ID: {request_id}." if request_id else ""
    provider_name = str(provider).strip().title() or "Provider"

    if safe_code == "insufficient_quota":
        return RuntimeError(
            f"{provider_name} API request failed (HTTP {status}, insufficient_quota): "
            f"API credits/quota are unavailable; check billing and project usage limits.{request_suffix}"
        )
    if status == 429:
        code_label = safe_code or "rate_limit_exceeded"
        return RuntimeError(
            f"{provider_name} API request failed (HTTP 429, {code_label}): "
            f"rate limit reached; retry after the limit resets.{request_suffix}"
        )
    if status is not None:
        code_label = f", {safe_code}" if safe_code else ""
        return RuntimeError(
            f"{provider_name} API request failed (HTTP {status}{code_label}): "
            f"the provider rejected the request.{request_suffix}"
        )
    return RuntimeError(f"{provider_name} network request failed: {type(error).__name__}.")

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

    @model_validator(mode="after")
    def validate_script_alignment(self):
        self.captions = [str(value).strip() for value in self.captions if str(value).strip()]
        self.narrations = [str(value).strip() for value in self.narrations if str(value).strip()]
        if not self.captions:
            raise ValueError("At least one caption is required.")
        if not self.narrations:
            raise ValueError("At least one narration is required.")
        if len(self.captions) != len(self.narrations):
            raise ValueError("Captions and narrations must contain the same number of slides.")
        while len(self.queries) < len(self.captions):
            self.queries.append("cinematic")
        if len(self.queries) > len(self.captions):
            self.queries = self.queries[:len(self.captions)]
        return self


def _creative_preference(settings, name: str, default: str) -> str:
    """Return a compact, single-line creative preference from a job snapshot."""
    value = str(getattr(settings, name, default) or default)
    return " ".join(value.split())[:100] or default


def fetch_ai_script(topic, provider="gemini", is_raw_script=False, settings=None):
    # A generation job passes a snapshot here; command-line callers without a
    # job retain the legacy configuration defaults.
    settings = settings or config
    provider = str(provider).strip().lower()
    niche = _creative_preference(settings, "CONTENT_NICHE", "General")
    language = _creative_preference(settings, "CONTENT_LANGUAGE", "Urdu")
    tone = _creative_preference(settings, "CONTENT_TONE", "Engaging & Clear")
    platform = _creative_preference(settings, "TARGET_PLATFORM", "Instagram Reels")
    visual_style = _creative_preference(settings, "VISUAL_STYLE", "Cinematic")
    schema_language = "the source script's original language" if is_raw_script else language
    schema_details = (
        "{\n"
        "  \"title\": \"Short English Title (e.g., Better Study Habits, Home Workout)\",\n"
        "  \"year\": \"Context or label (e.g., 2025, Beginner Guide, Fitness)\",\n"
        "  \"bg_music_vibe\": \"One of: mystery, epic, sad, ancient, modern, intense\",\n"
        f"  \"captions\": [\"{schema_language} text for Slide 1...\", \"{schema_language} text for Slide 2...\", \"...generate as many as needed to reach target duration\"],\n"
        f"  \"narrations\": [\"{schema_language} narration for Slide 1...\", \"{schema_language} narration for Slide 2...\", \"...must match number of captions\"],\n"
        "  \"queries\": [\n"
        "    \"specific search queries for stock video/images matching the script flow, e.g. ['student studying', 'morning routine', 'healthy meal prep', 'home workout', 'travel landscape', 'smartphone editing', 'creator desk', 'cinematic city']\"\n"
        "  ],\n"
        "  \"seo_title\": \"Hook/Title for social media (e.g., 3 Study Habits That Actually Work ✨)\",\n"
        f"  \"seo_description\": \"Detailed social media caption written in {language}\",\n"
        "  \"seo_hashtags\": \"Space-separated string of 8-12 topic-relevant hashtags (e.g., '#StudyTips #Productivity #Reels #ShortVideos')\",\n"
        "  \"seo_short_caption\": \"A short punchy caption for quick copy-paste\"\n"
        "}"
    )

    target_dur = getattr(settings, "TARGET_DURATION", None)
    if target_dur:
        num_slides = int(target_dur / 5.0)
        duration_instruction = f"IMPORTANT: The user requested a target video duration of {target_dur} seconds. You MUST generate approximately {num_slides} items in the captions, narrations, and queries arrays."
    else:
        duration_instruction = "IMPORTANT: Generate exactly as many captions, narrations, and queries as needed."

    creative_brief = (
        "CREATIVE BRIEF (follow every item): "
        f"Niche: {niche}. Content language: {language}. Tone: {tone}. "
        f"Target platform: {platform}. Visual style: {visual_style}. "
        f"Write captions and narrations exclusively in {language}; write media search queries in English; "
        "tailor the hook, SEO copy, hashtags, pacing, and visual queries to this brief."
    )
    raw_creative_brief = (
        "CREATIVE BRIEF: "
        f"Niche: {niche}. Tone: {tone}. Target platform: {platform}. Visual style: {visual_style}. "
        f"Preserve captions and narrations in the source script's original language; write SEO copy in {language}; "
        "write media search queries in English and tailor them to the selected visual style."
    )

    if is_raw_script:
        approx_slides = max(4, len(topic.split()) // 12)
        system_prompt = (
            "You are an expert short-form viral video producer. Your task is to take the provided raw narrative script (which may be in any supported language) "
            "and format/split it into logical slides matching the required JSON format. Preserve the raw narration verbatim in its original language; do not translate or omit it. "
            "CRITICAL STRICT SAFETY: The 'queries' you generate MUST be 100% strictly safe for work and family-friendly. NEVER generate any adult, NSFW, violent, or suggestive queries! "
            f"CRITICAL LENGTH RULE: You MUST divide the ENTIRE provided script into exactly {approx_slides} logical slides. Do NOT summarize or skip any part of it. Every single word of the script must be present in the narrations. "
            f"{raw_creative_brief} The output must strictly follow this JSON schema:\n{schema_details}"
        )
        user_prompt = f"Structure this ENTIRE raw script text into exactly {approx_slides} slides in JSON format without dropping a single sentence. Generate highly accurate, family-friendly English visual search queries for each slide. The text is:\n{topic}"
    else:
        system_prompt = (
            "You are an expert short-form viral video producer and scriptwriter. Generate a highly engaging script configuration for any niche in JSON format. "
            f"{creative_brief} {duration_instruction} The output must strictly follow this JSON schema:\n{schema_details}"
        )
        user_prompt = f"Generate script configuration in valid JSON format for topic: {topic}"

    if provider == "auto":
        print("\n[Auto Fallback Mode] Attempting to find the best available AI provider...")
        chain = ["gemini", "openai", "ollama", "openrouter", "groq"]
        last_error = None
        for p in chain:
            if p == "gemini" and not getattr(settings, "GEMINI_API_KEY", None): continue
            if p == "groq" and not getattr(settings, "GROQ_API_KEY", None): continue
            if p == "openrouter" and not getattr(settings, "OPENROUTER_API_KEY", None): continue
            if p == "openai" and not getattr(settings, "OPENAI_API_KEY", None): continue
            
            try:
                print(f"--> Trying {p.upper()}...")
                return fetch_ai_script(topic, provider=p, is_raw_script=is_raw_script, settings=settings)
            except Exception as e:
                print(f"    [X] {p.upper()} failed: {e}")
                last_error = e
        raise RuntimeError(f"All Auto-Fallback providers failed. Last error: {last_error}")

    if provider == "gemini":
        print(f"Calling Google Gemini 2.0 Flash to auto-generate script...")
        if not getattr(settings, "GEMINI_API_KEY", None):
            raise ValueError("Error: GEMINI_API_KEY environment variable is not set. Please set it in your .env file.")
        
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        headers = {
            "x-goog-api-key": getattr(settings, "GEMINI_API_KEY", None),
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
        try:
            result = response.json()
        except Exception as e:
            raise RuntimeError(f"Failed to decode JSON: {e}")
        
        try:
            raw_text = result["candidates"][0]["content"]["parts"][0]["text"]
            parsed = parse_json_response(raw_text)
            validated = ScriptConfig(**parsed)
            return validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()
        except Exception as e:
            raise ValueError(f"Failed to parse or validate Gemini API response: {e}. Raw response: {result}")
            
    elif provider == "openai":
        print(f"Calling OpenAI GPT-4o-mini to auto-generate script...")
        if not getattr(settings, "OPENAI_API_KEY", None):
            raise ValueError("Error: OPENAI_API_KEY environment variable is not set. Please set it in your .env file.")
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {getattr(settings, 'OPENAI_API_KEY', None)}",
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
        
        response = None
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            error_response = getattr(e, "response", None)
            if error_response is None:
                error_response = response
            raise build_api_request_error("OpenAI", error_response, e) from e
        try:
            result = response.json()
        except Exception as e:
            raise RuntimeError(f"Failed to decode JSON: {e}")
        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Unexpected API response from {provider}: {e}")
        parsed = parse_json_response(content)
        validated = ScriptConfig(**parsed)
        return validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()

    elif provider == "groq":
        print(f"Calling Groq llama-3.3-70b-versatile to auto-generate script...")
        if not getattr(settings, "GROQ_API_KEY", None):
            raise ValueError("Error: GROQ_API_KEY environment variable is not set. Please set it in your .env file.")
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {getattr(settings, 'GROQ_API_KEY', None)}",
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
        try:
            result = response.json()
        except Exception as e:
            raise RuntimeError(f"Failed to decode JSON: {e}")
        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Unexpected API response from {provider}: {e}")
        parsed = parse_json_response(content)
        validated = ScriptConfig(**parsed)
        return validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()

    elif provider == "ollama":
        ollama_model = getattr(settings, "OLLAMA_MODEL", "qwen2.5:7b")
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
        try:
            result = response.json()
        except Exception as e:
            raise RuntimeError(f"Failed to decode JSON: {e}")
        try:
            content = result["message"]["content"]
        except (KeyError, TypeError) as e:
            raise RuntimeError(f"Unexpected API response from Ollama: {e}. Raw: {result}")
        parsed = parse_json_response(content)
        validated = ScriptConfig(**parsed)
        return validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()

    elif provider == "openrouter":
        if not getattr(settings, "OPENROUTER_API_KEY", None):
            raise ValueError("Error: OPENROUTER_API_KEY environment variable is not set. Please set it in your .env file.")
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {getattr(settings, 'OPENROUTER_API_KEY', None)}",
            "HTTP-Referer": "https://github.com/anisar699/History-Reels-Builder-Gemini",
            "X-Title": "AI Reels Studio",
            "Content-Type": "application/json"
        }
        
        models_to_try = [
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "google/gemini-2.0-flash-exp:free",
            "meta-llama/llama-3.3-70b-instruct"
        ]
        
        last_error = None
        for model in models_to_try:
            print(f"Calling OpenRouter with model '{model}' to auto-generate script...")
            payload = {
                "model": model,
                "response_format": { "type": "json_object" },
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            }
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                response.raise_for_status()
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                parsed = parse_json_response(content)
                validated = ScriptConfig(**parsed)
                return validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()
            except requests.exceptions.RequestException as e:
                print(f"    [X] Model {model} failed (Network/API Error): {e}")
                last_error = e
            except Exception as e:
                print(f"    [X] Model {model} failed (Processing Error): {e}")
                last_error = e
                
        raise RuntimeError(f"All OpenRouter auto-fallback models failed. Last error: {last_error}")

    else:
        raise ValueError(f"Unknown AI content provider: {provider}")
