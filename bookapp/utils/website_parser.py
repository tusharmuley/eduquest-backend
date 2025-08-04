# utils/website_parser.py
import requests
from bs4 import BeautifulSoup

def extract_text_from_website(url: str) -> str:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }
        response = requests.get(url, timeout=10, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch page: {response.status_code}")

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        return text

    except Exception as e:
        print(f"❌ Error scraping website: {e}")
        return ""
