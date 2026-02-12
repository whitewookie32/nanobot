"""Telegram channel implementation using python-telegram-bot."""

import asyncio
import re
import subprocess

from loguru import logger
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import TelegramConfig


def _markdown_to_telegram_html(text: str) -> str:
    """
    Convert markdown to Telegram-safe HTML.
    """
    if not text:
        return ""
    
    # 1. Extract and protect code blocks (preserve content from other processing)
    code_blocks: list[str] = []
    def save_code_block(m: re.Match) -> str:
        code_blocks.append(m.group(1))
        return f"\x00CB{len(code_blocks) - 1}\x00"
    
    text = re.sub(r'```[\w]*\n?([\s\S]*?)```', save_code_block, text)
    
    # 2. Extract and protect inline code
    inline_codes: list[str] = []
    def save_inline_code(m: re.Match) -> str:
        inline_codes.append(m.group(1))
        return f"\x00IC{len(inline_codes) - 1}\x00"
    
    text = re.sub(r'`([^`]+)`', save_inline_code, text)
    
    # 3. Headers # Title -> just the title text
    text = re.sub(r'^#{1,6}\s+(.+)$', r'\1', text, flags=re.MULTILINE)
    
    # 4. Blockquotes > text -> just the text (before HTML escaping)
    text = re.sub(r'^>\s*(.*)$', r'\1', text, flags=re.MULTILINE)
    
    # 5. Escape HTML special characters
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # 6. Links [text](url) - must be before bold/italic to handle nested cases
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    
    # 7. Bold **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    
    # 8. Italic _text_ (avoid matching inside words like some_var_name)
    text = re.sub(r'(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])', r'<i>\1</i>', text)
    
    # 9. Strikethrough ~~text~~
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)
    
    # 10. Bullet lists - item -> • item
    text = re.sub(r'^[-*]\s+', '• ', text, flags=re.MULTILINE)
    
    # 11. Restore inline code with HTML tags
    for i, code in enumerate(inline_codes):
        # Escape HTML in code content
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00IC{i}\x00", f"<code>{escaped}</code>")
    
    # 12. Restore code blocks with HTML tags
    for i, code in enumerate(code_blocks):
        # Escape HTML in code content
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00CB{i}\x00", f"<pre><code>{escaped}</code></pre>")
    
    return text


class TelegramChannel(BaseChannel):
    """
    Telegram channel using long polling.
    
    Simple and reliable - no webhook/public IP needed.
    """
    
    name = "telegram"
    
    def __init__(self, config: TelegramConfig, bus: MessageBus, groq_api_key: str = ""):
        super().__init__(config, bus)
        self.config: TelegramConfig = config
        self.groq_api_key = groq_api_key
        self._app: Application | None = None
        self._chat_ids: dict[str, int] = {}  # Map sender_id to chat_id for replies
    
    async def start(self) -> None:
        """Start the Telegram bot with long polling."""
        if not self.config.token:
            logger.error("Telegram bot token not configured")
            return
        
        self._running = True
        
        # Build the application
        self._app = (
            Application.builder()
            .token(self.config.token)
            .build()
        )
        
        # Add message handler for text, photos, voice, documents
        self._app.add_handler(
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.VOICE | filters.AUDIO | filters.Document.ALL) 
                & ~filters.COMMAND, 
                self._on_message
            )
        )
        
        # Add command handlers
        from telegram.ext import CommandHandler
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("codexlogin", self._on_codex_login))
        self._app.add_handler(CommandHandler("codexlogout", self._on_codex_logout))
        self._app.add_handler(CommandHandler("codexstatus", self._on_codex_status))
        
        logger.info("Starting Telegram bot (polling mode)...")
        
        # Initialize and start polling
        await self._app.initialize()
        await self._app.start()
        
        # Get bot info
        bot_info = await self._app.bot.get_me()
        logger.info(f"Telegram bot @{bot_info.username} connected")
        
        # Start polling (this runs until stopped)
        await self._app.updater.start_polling(
            allowed_updates=["message"],
            drop_pending_updates=True  # Ignore old messages on startup
        )
        
        # Keep running until stopped
        while self._running:
            await asyncio.sleep(1)
    
    async def stop(self) -> None:
        """Stop the Telegram bot."""
        self._running = False
        
        if self._app:
            logger.info("Stopping Telegram bot...")
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None
    
    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through Telegram."""
        if not self._app:
            logger.warning("Telegram bot not running")
            return
        
        try:
            # chat_id should be the Telegram chat ID (integer)
            chat_id = int(msg.chat_id)
            # Convert markdown to Telegram HTML
            html_content = _markdown_to_telegram_html(msg.content)
            await self._app.bot.send_message(
                chat_id=chat_id,
                text=html_content,
                parse_mode="HTML"
            )
        except ValueError:
            logger.error(f"Invalid chat_id: {msg.chat_id}")
        except Exception as e:
            # Fallback to plain text if HTML parsing fails
            logger.warning(f"HTML parse failed, falling back to plain text: {e}")
            try:
                await self._app.bot.send_message(
                    chat_id=int(msg.chat_id),
                    text=msg.content
                )
            except Exception as e2:
                logger.error(f"Error sending Telegram message: {e2}")
    
    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not update.message or not update.effective_user:
            return
        
        user = update.effective_user
        await update.message.reply_text(
            f"👋 Hi {user.first_name}! I'm nanobot.\n\n"
            "Send me a message and I'll respond!\n\n"
            "🤖 **Available Commands:**\n"
            "• `/codexlogin` - Authenticate with OpenAI Codex\n"
            "• `/codexstatus` - Check Codex auth status\n"
            "• `/codexlogout` - Logout from Codex",
            parse_mode="Markdown"
        )
    
    async def _on_codex_login(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /codexlogin command - Start Codex OAuth flow."""
        if not update.message or not update.effective_user:
            return
        
        await update.message.reply_text(
            "🚀 Starting Codex authentication...\n"
            "This may take a moment..."
        )
        
        try:
            # Start codex login to get the URL and code
            proc = subprocess.Popen(
                ["codex", "login", "--device-auth"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            
            await update.message.reply_text(
                "🔐 **Codex Authentication Required**\n\n"
                "1️⃣ Visit: **https://auth.openai.com/device/login**\n"
                "2️⃣ Sign in with your OpenAI account\n"
                "3️⃣ Wait for code to appear...",
                parse_mode="Markdown"
            )
            
            # Read output line by line
            url = None
            code = None
            
            for line in iter(proc.stdout.readline, ''):
                line = line.strip()
                if line:
                    # Log for debugging
                    logger.info(f"Codex output: {line}")
                    
                    # Look for device code pattern
                    if 'code:' in line.lower() or '-' in line:
                        parts = line.split('code:')
                        if len(parts) > 1:
                            code = parts[1].strip()
                        elif '-' in line and len(line) < 20:
                            # Extract code like "ABCD-EFGH"
                            import re
                            match = re.search(r'([A-Z0-9]{4}-[A-Z0-9]{4})', line)
                            if match:
                                code = match.group(1)
                    
                    # Look for URL
                    if 'http' in line:
                        import re
                        match = re.search(r'https?://[^\s\)]+', line)
                        if match:
                            url = match.group(0)
            
            proc.wait(timeout=300)  # Wait up to 5 minutes
            
            if code:
                await update.message.reply_text(
                    f"🔑 **Your Device Code:** `{code}`\n\n"
                    f"Enter this code at: https://auth.openai.com/device/login\n\n"
                    f"Or open: {url if url else 'https://auth.openai.com/device/login'}\n\n"
                    f"⚠️  Code expires in 10 minutes!",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    "Please visit: https://auth.openai.com/device/login\n\n"
                    "Then run `/codexstatus` to check if authenticated.",
                    parse_mode="Markdown"
                )
                
        except subprocess.TimeoutExpired:
            proc.kill()
            await update.message.reply_text(
                "⏱️ Authentication timed out. Please try again with `/codexlogin`"
            )
        except FileNotFoundError:
            await update.message.reply_text(
                "❌ **Codex CLI not found**\n\n"
                "Install with: `pip install codex`\n"
                "Then restart nanobot."
            )
        except Exception as e:
            logger.error(f"Codex login error: {e}")
            await update.message.reply_text(
                f"❌ Error starting authentication: {str(e)}\n\n"
                "Try again with `/codexlogin`"
            )

    async def _on_codex_logout(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /codexlogout command - Logout from Codex."""
        if not update.message:
            return
        
        try:
            result = subprocess.run(
                ["codex", "logout"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                await update.message.reply_text(
                    "✅ **Logged out of Codex successfully**",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    "ℹ️ Already logged out or no session found."
                )
        except Exception as e:
            logger.error(f"Codex logout error: {e}")
            await update.message.reply_text(
                f"❌ Error during logout: {str(e)}"
            )

    async def _on_codex_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /codexstatus command - Check authentication status."""
        if not update.message:
            return
        
        try:
            result = subprocess.run(
                ["codex", "login", "status"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            output = result.stdout.lower()
            
            if "not authenticated" in output or result.returncode != 0:
                await update.message.reply_text(
                    "🔴 **Codex Status: Not Authenticated**\n\n"
                    "To authenticate, use: `/codexlogin`",
                    parse_mode="Markdown"
                )
            elif "authenticated" in output or "logged in" in output:
                # Try to get more details
                org_result = subprocess.run(
                    ["codex"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                await update.message.reply_text(
                    "🟢 **Codex Status: Authenticated** ✅\n\n"
                    "You're ready to use Codex tools!\n\n"
                    "To logout: `/codexlogout`",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"🟡 **Codex Status:** Unknown\n\n"
                    f"Output: {result.stdout[:200]}",
                    parse_mode="Markdown"
                )
                
        except FileNotFoundError:
            await update.message.reply_text(
                "❌ **Codex CLI not found**\n\n"
                "Install with: `pip install codex`"
            )
        except Exception as e:
            logger.error(f"Codex status error: {e}")
            await update.message.reply_text(
                f"❌ Error checking status: {str(e)}"
            )

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming messages (text, photos, voice, documents)."""
        if not update.message or not update.effective_user:
            return
        
        message = update.message
        user = update.effective_user
        chat_id = message.chat_id
        
        # Use stable numeric ID, but keep username for allowlist compatibility
        sender_id = str(user.id)
        if user.username:
            sender_id = f"{sender_id}|{user.username}"
        
        # Store chat_id for replies
        self._chat_ids[sender_id] = chat_id
        
        # Build content from text and/or media
        content_parts = []
        media_paths = []
        
        # Text content
        if message.text:
            content_parts.append(message.text)
        if message.caption:
            content_parts.append(message.caption)
        
        # Handle media files
        media_file = None
        media_type = None
        
        if message.photo:
            media_file = message.photo[-1]  # Largest photo
            media_type = "image"
        elif message.voice:
            media_file = message.voice
            media_type = "voice"
        elif message.audio:
            media_file = message.audio
            media_type = "audio"
        elif message.document:
            media_file = message.document
            media_type = "file"
        
        # Download media if present
        if media_file and self._app:
            try:
                file = await self._app.bot.get_file(media_file.file_id)
                ext = self._get_extension(media_type, getattr(media_file, 'mime_type', None))
                
                # Save to workspace/media/
                from pathlib import Path
                media_dir = Path.home() / ".nanobot" / "media"
                media_dir.mkdir(parents=True, exist_ok=True)
                
                file_path = media_dir / f"{media_file.file_id[:16]}{ext}"
                await file.download_to_drive(str(file_path))
                
                media_paths.append(str(file_path))
                
                # Handle voice transcription
                if media_type == "voice" or media_type == "audio":
                    from nanobot.providers.transcription import GroqTranscriptionProvider
                    transcriber = GroqTranscriptionProvider(api_key=self.groq_api_key)
                    transcription = await transcriber.transcribe(file_path)
                    if transcription:
                        logger.info(f"Transcribed {media_type}: {transcription[:50]}...")
                        content_parts.append(f"[transcription: {transcription}]")
                    else:
                        content_parts.append(f"[{media_type}: {file_path}]")
                else:
                    content_parts.append(f"[{media_type}: {file_path}]")
                    
                logger.debug(f"Downloaded {media_type} to {file_path}")
            except Exception as e:
                logger.error(f"Failed to download media: {e}")
                content_parts.append(f"[{media_type}: download failed]")
        
        content = "\n".join(content_parts) if content_parts else "[empty message]"
        
        logger.debug(f"Telegram message from {sender_id}: {content[:50]}...")
        
        # Forward to the message bus
        await self._handle_message(
            sender_id=sender_id,
            chat_id=str(chat_id),
            content=content,
            media=media_paths,
            metadata={
                "message_id": message.message_id,
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "is_group": message.chat.type != "private"
            }
        )
    
    def _get_extension(self, media_type: str, mime_type: str | None) -> str:
        """Get file extension based on media type."""
        if mime_type:
            ext_map = {
                "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a",
            }
            if mime_type in ext_map:
                return ext_map[mime_type]
        
        type_map = {"image": ".jpg", "voice": ".ogg", "audio": ".mp3", "file": ""}
        return type_map.get(media_type, "")
