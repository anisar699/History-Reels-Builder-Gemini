import os

with open('history_reels/script_generator.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_openrouter_block = """    elif provider == "openrouter":
        print(f"Calling OpenRouter Llama 3.3 70B to auto-generate script...")
        if not settings.OPENROUTER_API_KEY:
            raise ValueError("Error: OPENROUTER_API_KEY environment variable is not set. Please set it in your .env file.")
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://github.com/anisar699/History-Reels-Builder-Gemini",
            "X-Title": "AI Reels Studio",
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
        return validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()"""

new_openrouter_block = """    elif provider == "openrouter":
        if not settings.OPENROUTER_API_KEY:
            raise ValueError("Error: OPENROUTER_API_KEY environment variable is not set. Please set it in your .env file.")
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://github.com/anisar699/History-Reels-Builder-Gemini",
            "X-Title": "AI Reels Studio",
            "Content-Type": "application/json"
        }
        
        # Auto-fallback list for OpenRouter: Best -> Medium -> Free
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
                response_content = result["choices"][0]["message"]["content"]
                parsed = parse_json_response(response_content)
                validated = ScriptConfig(**parsed)
                return validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()
            except requests.exceptions.RequestException as e:
                print(f"    [X] Model {model} failed (Network/API Error): {e}")
                last_error = e
            except Exception as e:
                print(f"    [X] Model {model} failed (Processing Error): {e}")
                last_error = e
                
        raise RuntimeError(f"All OpenRouter auto-fallback models failed. Last error: {last_error}")"""

if old_openrouter_block in content:
    content = content.replace(old_openrouter_block, new_openrouter_block)
    with open('history_reels/script_generator.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('SUCCESS')
else:
    print('FAILED: Target block not found.')
