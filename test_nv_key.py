import os
import io
import base64
import requests
from dotenv import load_dotenv
from PIL import Image

load_dotenv()
api_key = os.environ.get("NVIDIA_API_KEY")

print(f"Loaded NVIDIA_API_KEY: {api_key[:15]}...")

print("\n--- Testing Stable Diffusion 3 Medium (Image) ---")
url_img = "https://ai.api.nvidia.com/v1/genai/stabilityai/stable-diffusion-3-medium"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}
payload_img = {
    "prompt": "a futuristic city",
    "features": ["premium quality"], # Some keys if needed
}
headers_img = {
    "Authorization": f"Bearer {api_key}",
    "Accept": "application/json",
}
payload_img = {
    "prompt": "a red car",
    "steps": 10
}

response_img = requests.post(url_img, headers=headers, json=payload_img)
print(f"Status: {response_img.status_code}")
if response_img.status_code != 200:
    print(f"Error: {response_img.text[:500]}")
else:
    print("Success: Image API worked.")

print("\n--- Testing Stable Video Diffusion (Video) ---")
# Create dummy image
img = Image.new('RGB', (1024, 576), color='red')
img_bytes = io.BytesIO()
img.save(img_bytes, format='JPEG')
b64_img = base64.b64encode(img_bytes.getvalue()).decode('utf-8')

url_vid = "https://ai.api.nvidia.com/v1/genai/stabilityai/stable-video-diffusion"
payload_vid = {
    "image": f"data:image/jpeg;base64,{b64_img}",
    "seed": 0,
    "cfg_scale": 1.8,
    "motion_bucket_id": 127
}
response_vid = requests.post(url_vid, headers=headers, json=payload_vid)
print(f"Status: {response_vid.status_code}")
if response_vid.status_code != 200:
    print(f"Error: {response_vid.text[:500]}")
else:
    print("Success: Video API worked.")
