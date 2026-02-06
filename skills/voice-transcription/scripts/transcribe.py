#!/usr/bin/env python3
"""
Transcribe audio files using Together AI's Whisper API.
Supports .ogg, .mp3, .wav, .m4a, and other audio formats.
"""

import os
import sys
import requests


def transcribe_audio(audio_path: str, api_key: str = None, model: str = "openai/whisper-large-v3") -> str:
    """
    Transcribe an audio file using Together AI's Whisper API.
    
    Args:
        audio_path: Path to the audio file
        api_key: Together API key (defaults to TOGETHER_API_KEY env var)
        model: Model to use for transcription
    
    Returns:
        Transcribed text
    """
    api_key = api_key or os.environ.get("TOGETHER_API_KEY")
    if not api_key:
        raise ValueError("Together API key required. Set TOGETHER_API_KEY env var or pass api_key parameter.")
    
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    url = "https://api.together.xyz/v1/audio/transcriptions"
    
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    
    with open(audio_path, "rb") as audio_file:
        files = {
            "file": (os.path.basename(audio_path), audio_file),
            "model": (None, model)
        }
        
        response = requests.post(url, headers=headers, files=files)
    
    if response.status_code != 200:
        raise RuntimeError(f"Transcription failed: {response.status_code} - {response.text}")
    
    result = response.json()
    return result.get("text", "")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: transcribe.py <audio_file> [model]")
        print("Example: transcribe.py /path/to/audio.ogg")
        print("\nEnvironment variable TOGETHER_API_KEY must be set.")
        sys.exit(1)
    
    audio_path = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else "openai/whisper-large-v3"
    
    try:
        text = transcribe_audio(audio_path, model=model)
        print(text)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
