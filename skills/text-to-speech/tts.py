"""Text-to-speech using Together AI's Cartesia Sonic-3 model."""

import os
import tempfile
from together import Together


def text_to_speech(text: str, output_path: str = None, voice: str = "sarah") -> str:
    """
    Convert text to speech using Together AI's Cartesia Sonic-3 model.
    
    Args:
        text: The text to convert to speech
        output_path: Optional path to save the audio file. If not provided,
                    a temporary file will be created.
        voice: Voice to use (default: "sarah"). Popular options: sarah, john, 
               maria, newsman, newslady, reading_man, reading_lady, calm_lady,
               helpful_woman, friendly_man, etc.
    
    Returns:
        Path to the generated audio file
    """
    api_key = os.environ.get("TOGETHER_API_KEY")
    if not api_key:
        raise ValueError("TOGETHER_API_KEY environment variable not set")
    
    client = Together(api_key=api_key)
    
    response = client.audio.speech.create(
        model="cartesia/sonic-3",
        input=text,
        voice=voice
    )
    
    if output_path is None:
        # Create a temporary file with .wav extension
        fd, output_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
    
    response.write_to_file(output_path)
    
    return output_path


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python tts.py 'Your text here'")
        sys.exit(1)
    
    text = sys.argv[1]
    audio_file = text_to_speech(text)
    print(f"Audio saved to: {audio_file}")
