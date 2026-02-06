---
name: text-to-speech
description: Generate speech from text using Together AI's Cartesia Sonic-3 TTS API. Supports multiple voices and outputs OGG format for Telegram voice messages.
---

# Text-to-Speech

Generate speech from text using Together AI's Cartesia Sonic-3 TTS API.

## Quick Start

Generate speech from text:

```bash
python3 /Nano/workspace/skills/text-to-speech/scripts/tts.py "Hello, I am Donna." /tmp/output.ogg
```

## Requirements

- `TOGETHER_API_KEY` environment variable must be set
- Python 3 with `requests` library (`pip install requests`)

## Supported Voices

- `sarah` - Natural conversational (default)
- `maria` - Warm professional
- `tessa` - Young, energetic
- `arianna` - Clear, articulate
- `john` - Natural male
- `british_lady` - Sophisticated British accent
- And 100+ more...

## Usage Examples

```python
# In Python code
import sys
sys.path.insert(0, '/Nano/workspace/skills/text-to-speech/scripts')
from tts import generate_speech

# Generate speech
output_file = generate_speech(
    text="Hello, I'm Donna.",
    output_path="/tmp/output.ogg",
    voice="sarah"
)
print(f"Audio saved to: {output_file}")
```

## CLI Usage

```bash
# Basic usage with default voice (sarah)
python3 /Nano/workspace/skills/text-to-speech/scripts/tts.py "Hello world" output.ogg

# With specific voice
python3 /Nano/workspace/skills/text-to-speech/scripts/tts.py "Hello world" output.ogg --voice tessa

# List available voices
python3 /Nano/workspace/skills/text-to-speech/scripts/tts.py --list-voices
```

## Default Model

- `cartesia/sonic-3` - High quality, low latency, multiple voices

## API Endpoint

```
POST https://api.together.xyz/v1/audio/generations
```

## Response

Returns OGG audio file suitable for Telegram voice messages.
