import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("NVIDIA_API_KEY")

headers = {
    "Authorization": f"Bearer {api_key}",
    "Accept": "application/json",
}

urls = [
    "https://integrate.api.nvidia.com/v1/models",
    "https://ai.api.nvidia.com/v1/models"
]

print("Fetching available models from NVIDIA APIs...")

found_models = []

for url in urls:
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            models = response.json().get("data", [])
            for m in models:
                name = m.get("id", "").lower()
                if "cosmos" in name or "video" in name:
                    found_models.append(m.get("id"))
        else:
            print(f"Failed {url}: {response.status_code} - {response.text[:100]}")
    except Exception as e:
        print(f"Error {url}: {e}")

if found_models:
    print("\n✅ Found these related models in your NVIDIA account:")
    for m in set(found_models):
        print(f" - {m}")
else:
    print("\n❌ No models containing 'cosmos' or 'video' were found in the standard API endpoints.")
