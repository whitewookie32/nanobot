#!/usr/bin/env python3
"""Text-to-Speech using Together AI's Cartesia Sonic-3"""

import os
import requests
import json

def generate_speech(text, output_path, voice="sarah", model="cartesia/sonic-3"):
    """Generate speech from text and save to file.
    
    Args:
        text: The text to convert to speech
        output_path: Where to save the audio file
        voice: Voice ID (default: sarah)
        model: TTS model (default: cartesia/sonic-3)
    
    Returns:
        Path to the generated audio file
    """
    api_key = os.environ.get("TOGETHER_API_KEY")
    if not api_key:
        raise ValueError("TOGETHER_API_KEY environment variable not set")
    
    url = "https://api.together.xyz/v1/audio/generations"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "input": text,
        "voice": voice
    }
    
    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code != 200:
        raise Exception(f"TTS API error: {response.status_code} - {response.text}")
    
    # Save the audio content
    with open(output_path, 'wb') as f:
        f.write(response.content)
    
    return output_path

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Text-to-Speech with Together AI')
    parser.add_argument('text', help='Text to convert to speech')
    parser.add_argument('output', help='Output file path')
    parser.add_argument('--voice', default='sarah', help='Voice ID (default: sarah)')
    
    args = parser.parse_args()
    
    try:
        result = generate_speech(args.text, args.output, args.voice)
        print(f"Audio saved to: {result}")
    except Exception as e:
        print(f"Error: {e}")
        exit(1)
