"""
Omi Handler - Bridges Omi wearable requests to Nanobot.

This module provides HTTP endpoints that integrate with the main Nanobot gateway,
allowing Omi devices to send voice/text requests that get processed by the LLM.

Architecture:
    Omi Device → Omi App → Omi Cloud → /tools/ask → Nanobot LLM → Response

Usage:
    The handler is automatically registered when nanobot.gateway module is imported.
    Endpoints available at:
        - GET  /tools/ask/health  - Health check
        - POST /tools/ask         - Process Omi request
"""

import asyncio
import logging
import os
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Configuration
OMI_SECRET_TOKEN = os.getenv("OMI_SECRET_TOKEN", "")
QUICK_RESPONSE_TIMEOUT = int(os.getenv("OMI_QUICK_TIMEOUT", "8"))  # seconds


class OmiRequest(BaseModel):
    """Request model for Omi tool invocation."""

    request: str
    uid: str
    callback_url: Optional[str] = None


class OmiResponse(BaseModel):
    """Response model for Omi tool invocation."""

    result: str
    is_background: bool = False


class OmiHandler:
    """
    Handler for Omi requests.
    
    Integrates with the Nanobot gateway to process requests from Omi wearable devices.
    """

    def __init__(self, agent_loop=None):
        """
        Initialize the Omi handler.
        
        Args:
            agent_loop: The agent loop to use for processing requests
        """
        self.agent_loop = agent_loop
        self._token = OMI_SECRET_TOKEN

    def set_agent_loop(self, agent_loop):
        """Set the agent loop after initialization."""
        self.agent_loop = agent_loop

    def verify_token(self, token: str) -> bool:
        """
        Verify the token from the Omi app.
        
        Args:
            token: The X-Omi-Token header value
            
        Returns:
            True if token is valid, False otherwise
        """
        if not self._token:
            # No token configured - skip verification (development mode)
            logger.warning("OMI_SECRET_TOKEN not set - skipping token verification")
            return True

        if not token:
            return False

        # Constant-time comparison to prevent timing attacks
        return len(token) == len(self._token) and all(a == b for a, b in zip(token, self._token))

    async def handle_request(self, data: OmiRequest, token: str) -> OmiResponse:
        """
        Handle an Omi request.
        
        Args:
            data: The request data
            token: The verification token
            
        Returns:
            The response
        """
        if not self.verify_token(token):
            return OmiResponse(result="Error: Invalid or missing token", is_background=False)

        if not self.agent_loop:
            return OmiResponse(result="Error: Agent not initialized", is_background=False)

        logger.info(f"Omi request from user {data.uid}: {data.request[:100]}...")

        try:
            # Process through agent with quick timeout
            result = await asyncio.wait_for(
                self.agent_loop.process_direct(
                    data.request,
                    session_key=f"omi:{data.uid}",
                    channel="omi",
                    chat_id=data.uid,
                ),
                timeout=QUICK_RESPONSE_TIMEOUT,
            )
            return OmiResponse(result=result or "Done", is_background=False)

        except asyncio.TimeoutError:
            # Request timed out - run in background
            logger.info(f"Omi request timed out for user {data.uid}, running in background")
            
            # Start background task
            asyncio.create_task(self._background_task(data))
            
            return OmiResponse(
                result="I'm working on this. I'll let you know when it's done.",
                is_background=True,
            )

        except Exception as e:
            logger.error(f"Error processing Omi request: {e}")
            return OmiResponse(result=f"Error: {str(e)}", is_background=False)

    async def _background_task(self, data: OmiRequest):
        """Handle a request in the background."""
        try:
            result = await self.agent_loop.process_direct(
                data.request,
                session_key=f"omi:{data.uid}",
                channel="omi",
                chat_id=data.uid,
            )
            logger.info(f"Background task completed for user {data.uid}")
            
            # TODO: Send callback if callback_url provided
            if data.callback_url:
                logger.info(f"Would send callback to {data.callback_url}")
                
        except Exception as e:
            logger.error(f"Background task failed: {e}")

    def health_check(self) -> dict:
        """Return health check info."""
        return {
            "status": "ok",
            "service": "nanobot-bridge",
            "token_configured": bool(self._token),
            "agent_ready": self.agent_loop is not None,
        }


# Global handler instance
omi_handler = OmiHandler()


def register_routes(gateway_handler):
    """
    Register Omi routes with the gateway HTTP handler.
    
    This patches the WebHandler class to add Omi endpoints.
    
    Args:
        gateway_handler: The gateway command function from nanobot.cli.commands
    """
    import json
    from urllib.parse import urlparse
    
    # Store original do_POST method
    original_do_post = gateway_handler.__globals__['WebHandler'].do_POST
    original_do_get = gateway_handler.__globals__['WebHandler'].do_GET
    
    def new_do_post(self):
        path = urlparse(self.path).path
        
        if path == "/tools/ask":
            # Handle Omi request
            try:
                body = self._read_body()
                payload = json.loads(body or "{}")
                data = OmiRequest(**payload)
                token = self.headers.get("X-Omi-Token", "")
                
                # Run async handler
                import asyncio
                loop = asyncio.new_event_loop()
                try:
                    response = loop.run_until_complete(omi_handler.handle_request(data, token))
                    self._send_json(json.dumps(response.model_dump()), 200)
                finally:
                    loop.close()
                    
            except Exception as e:
                self._send_json(json.dumps({"result": f"Error: {str(e)}"}), 500)
            return
        
        # Fall through to original handler
        original_do_post(self)
    
    def new_do_get(self):
        path = urlparse(self.path).path
        
        if path in ("/tools/ask/health", "/tools/health"):
            self._send_json(json.dumps(omi_handler.health_check()), 200)
            return
        
        # Fall through to original handler
        original_do_get(self)
    
    # Patch the methods
    gateway_handler.__globals__['WebHandler'].do_POST = new_do_post
    gateway_handler.__globals__['WebHandler'].do_GET = new_do_get
    
    logger.info("Omi routes registered: /tools/ask, /tools/ask/health")