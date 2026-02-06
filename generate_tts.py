#!/usr/bin/env python3
"""Generate TTS using Together AI's Cartesia Sonic-3 API"""

import os
import requests

API_KEY = os.environ.get("TOGETHER_API_KEY")
if not API_KEY:
    raise ValueError("TOGETHER_API_KEY environment variable not set")

# Together AI TTS endpoint
url = "https://api.together.xyz/v1/audio/speech"

# Request payload - using correct parameter names from Together AI docs
payload = {
    "input": "I'm Donna, and I'm running this office.",
    "model": "cartesia/sonic-3",
    "voice": "professional woman"
}

# Headers
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Make the request
response = requests.post(url, json=payload, headers=headers)

if response.status_code == 200:
    # Save the audio file
    output_path = "/tmp/donna_professional_space.ogg"
    with open(output_path, "wb") as f:
        f.write(response.content)
    print(f"Audio saved to: {output_path}")
    print(f"File size: {len(response.content)} bytes")
else:
    print(f"Error: {response.status_code}")
    print(f"Response: {response.text}")
