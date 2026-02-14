"""Omi Bridge Handler - Processes requests from Omi wearable device."""
import os
import httpx
from typing import Optional

# Configuration
OMI_SECRET_TOKEN = os.getenv("OMI_SECRET_TOKEN", "")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")
TOGETHER_MODEL = os.getenv("TOGETHER_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo")


def check_health() -> dict:
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "nanobot-bridge",
        "omi_token_configured": bool(OMI_SECRET_TOKEN),
        "api_key_configured": bool(TOGETHER_API_KEY),
    }


def verify_token(token: str) -> bool:
    """Verify the Omi secret token."""
    if not OMI_SECRET_TOKEN:
        return True  # No token configured, allow all
    return token == OMI_SECRET_TOKEN


async def process_omi_request(request: str, uid: str, callback_url: Optional[str] = None) -> dict:
    """
    Process a request from Omi device.
    
    Args:
        request: The voice/text request from Omi
        uid: User identifier
        callback_url: Optional URL to post the response
    
    Returns:
        dict with response text
    """
    if not TOGETHER_API_KEY:
        return {
            "status": "error",
            "message": "API key not configured"
        }
    
    # Call Together AI
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                "https://api.together.xyz/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {TOGETHER_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": TOGETHER_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are Nanobot, a helpful AI assistant. Keep responses concise and conversational since this is for a voice interface."},
                        {"role": "user", "content": request}
                    ],
                    "max_tokens": 500,
                    "temperature": 0.7
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                text = data["choices"][0]["message"]["content"]
                
                # If callback URL provided, post response there
                if callback_url:
                    try:
                        await client.post(callback_url, json={"response": text, "uid": uid})
                    except Exception as e:
                        print(f"Callback failed: {e}")
                
                return {
                    "status": "ok",
                    "response": text
                }
            else:
                return {
                    "status": "error",
                    "message": f"API error: {response.status_code}"
                }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
