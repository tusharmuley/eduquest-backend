import httpx
import os

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

headers = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "http://localhost",
}

def generate_answer(prompt: str):
    url = "https://openrouter.ai/api/v1/chat/completions"

    data = {
        "model": "mistralai/mistral-7b-instruct",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that answers based on provided text."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0,
    }

    try:
        response = httpx.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print("LLM Error:", e)
        return "Sorry, something went wrong."
