---
name: voice-transcription
description: Transcribe audio files (voice messages, recordings) to text using Together AI's Whisper API. Use when the agent receives voice messages, audio files, or needs to convert speech to text. Supports .ogg, .mp3, .wav, .m4a and other formats.
---

# Voice Transcription

Transcribe audio files to text using Together AI's Whisper API.

## Quick Start

Transcribe an audio file:

```bash
python3 /Nano/workspace/skills/voice-transcription/scripts/transcribe.py /path/to/audio.ogg
```

## Requirements

- `TOGETHER_API_KEY` environment variable must be set
- Python 3 with `requests` library (`pip install requests`)

## Supported Formats

- OGG (Telegram voice messages)
- MP3
- WAV
- M4A
- Most other audio formats

## Usage Examples

```python
# In Python code
import sys
sys.path.insert(0, '/Nano/workspace/skills/voice-transcription/scripts')
from transcribe import transcribe_audio

text = transcribe_audio("/path/to/audio.ogg")
print(text)
```

## CLI Usage

```bash
# Basic usage
python3 /Nano/workspace/skills/voice-transcription/scripts/transcribe.py audio.ogg

# With specific model
python3 /Nano/workspace/skills/voice-transcription/scripts/transcribe.py audio.ogg openai/whisper-large-v3
```

## Default Model

- `openai/whisper-large-v3` - High quality, supports multiple languages

## API Response Format

The Together AI API returns a JSON response:
```json
{
  "text": "Transcribed text here..."
}
```
