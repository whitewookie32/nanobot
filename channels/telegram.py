"""Telegram channel implementation using python-telegram-bot."""

import asyncio
import os
import re

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
        self._codex_login_proc: asyncio.subprocess.Process | None = None
        self._codex_login_task: asyncio.Task | None = None
    
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
        self._app.add_handler(CommandHandler("codexstatus", self._on_codex_status))
        self._app.add_handler(CommandHandler("codexlogout", self._on_codex_logout))
        
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
            if self._codex_login_proc and self._codex_login_proc.returncode is None:
                self._codex_login_proc.terminate()
                try:
                    await asyncio.wait_for(self._codex_login_proc.wait(), timeout=2)
                except Exception:
                    self._codex_login_proc.kill()
            if self._codex_login_task and not self._codex_login_task.done():
                self._codex_login_task.cancel()
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
            "Available commands:\n"
            "/codexlogin - Start Codex auth\n"
            "/codexstatus - Check Codex auth status\n"
            "/codexlogout - Logout Codex auth"
        )
    
    @staticmethod
    def _extract_codex_login_info(lines: list[str]) -> dict[str, str]:
        auth_url = ""
        callback_url = ""
        code = ""
        for line in reversed(lines):
            for match in re.findall(r"https?://\S+", line):
                url = match.rstrip(").,")
                lower_url = url.lower()
                if ("localhost" in lower_url or "127.0.0.1" in lower_url) and not callback_url:
                    callback_url = url
                elif not auth_url:
                    auth_url = url
            if not code and "code" in line.lower():
                match = re.search(r"([A-Z0-9]{4,}(?:-[A-Z0-9]{4,})?)", line)
                if match:
                    code = match.group(1)
            if auth_url and callback_url and code:
                break
        return {
            "url": auth_url,
            "authUrl": auth_url,
            "callbackUrl": callback_url,
            "code": code,
        }

    @staticmethod
    def _format_codex_login_message(info: dict[str, str], use_localhost: bool) -> str:
        auth_url = info.get("authUrl") or info.get("url")
        callback_url = info.get("callbackUrl")
        code = info.get("code")

        if use_localhost:
            lines_out = ["Codex authentication required."]
            if auth_url:
                lines_out.append(f"Open: {auth_url}")
            else:
                lines_out.append("Open: waiting for auth.openai.com URL from Codex CLI...")
            if callback_url:
                lines_out.append(f"Callback: {callback_url}")
            if code:
                lines_out.append(f"Code: {code}")
            lines_out.append("")
            lines_out.append("Use /codexstatus to check completion.")
            return "\n".join(lines_out)

        if not auth_url:
            auth_url = "https://auth.openai.com/device/login"
        return (
            "Codex authentication required.\n\n"
            f"Open: {auth_url}\n"
            + (f"Code: {code}\n\n" if code else "\n")
            + "Use /codexstatus to check completion."
        )

    async def _on_codex_login(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /codexlogin command."""
        if not update.message:
            return
        chat_id = update.message.chat_id

        if self._codex_login_proc and self._codex_login_proc.returncode is None:
            await update.message.reply_text(
                "Codex login is already running. Use /codexstatus to check state."
            )
            return

        use_localhost = os.getenv("NANOBOT_CODEX_LOCALHOST_OAUTH", "1").lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        command = ("codex", "login") if use_localhost else ("codex", "login", "--device-auth")
        mode = "localhost redirect" if use_localhost else "device code"
        await update.message.reply_text(f"Starting Codex authentication ({mode})...")

        try:
            proc = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        except FileNotFoundError:
            await update.message.reply_text(
                "Codex CLI not found. Install with: npm install -g @openai/codex"
            )
            return
        except Exception as exc:
            logger.error(f"Codex login error: {exc}")
            await update.message.reply_text(f"Failed to start Codex login: {exc}")
            return

        self._codex_login_proc = proc
        lines: list[str] = []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 20

        while loop.time() < deadline:
            if not proc.stdout:
                break
            if proc.returncode is not None:
                break
            try:
                raw_line = await asyncio.wait_for(proc.stdout.readline(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            if not raw_line:
                break
            line = raw_line.decode(errors="ignore").strip()
            if not line:
                continue
            lines.append(line)
            logger.info(f"Codex output: {line}")
            info = self._extract_codex_login_info(lines)
            if (use_localhost and info["authUrl"]) or info["code"]:
                break

        info = self._extract_codex_login_info(lines)
        auth_url = info.get("authUrl") or info.get("url")
        code = info.get("code")
        has_login_details = (
            (use_localhost and bool(auth_url))
            or (not use_localhost and auth_url)
            or bool(code)
        )

        if has_login_details:
            await update.message.reply_text(self._format_codex_login_message(info, use_localhost))
        else:
            await update.message.reply_text(
                "Codex auth started. Waiting for login URL/callback output; I will post it here when it appears."
            )

        async def _drain_login_output() -> None:
            details_sent = has_login_details
            try:
                if proc.stdout:
                    while True:
                        raw_line = await proc.stdout.readline()
                        if not raw_line:
                            break
                        line = raw_line.decode(errors="ignore").strip()
                        if line:
                            lines.append(line)
                            logger.info(f"Codex output: {line}")
                            if not details_sent and self._app:
                                live_info = self._extract_codex_login_info(lines)
                                live_auth_url = live_info.get("authUrl") or live_info.get("url")
                                live_code = live_info.get("code")
                                has_live_details = (
                                    (use_localhost and bool(live_auth_url))
                                    or (not use_localhost and live_auth_url)
                                    or bool(live_code)
                                )
                                if has_live_details:
                                    await self._app.bot.send_message(
                                        chat_id=chat_id,
                                        text=self._format_codex_login_message(live_info, use_localhost),
                                    )
                                    details_sent = True
                await proc.wait()
                logger.info(f"Codex login process exited with code {proc.returncode}")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"Codex login watcher error: {exc}")
            finally:
                self._codex_login_proc = None
                self._codex_login_task = None

        self._codex_login_task = asyncio.create_task(_drain_login_output())

    async def _on_codex_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /codexstatus command."""
        if not update.message:
            return

        try:
            proc = await asyncio.create_subprocess_exec(
                "codex",
                "login",
                "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            output_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = output_bytes.decode(errors="ignore").strip()
            logged_in = proc.returncode == 0

            if logged_in:
                await update.message.reply_text("Codex status: authenticated.")
                return

            suffix = "\n\nLogin is still in progress." if (
                self._codex_login_proc and self._codex_login_proc.returncode is None
            ) else ""
            await update.message.reply_text(
                "Codex status: not authenticated.\n"
                "Use /codexlogin to authenticate."
                f"{suffix}"
                + (f"\n\nOutput: {output[:300]}" if output else "")
            )
        except FileNotFoundError:
            await update.message.reply_text(
                "Codex CLI not found. Install with: npm install -g @openai/codex"
            )
        except asyncio.TimeoutError:
            await update.message.reply_text("Timed out checking Codex status. Try again.")
        except Exception as exc:
            logger.error(f"Codex status error: {exc}")
            await update.message.reply_text(f"Error checking Codex status: {exc}")

    async def _on_codex_logout(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /codexlogout command."""
        if not update.message:
            return

        if self._codex_login_proc and self._codex_login_proc.returncode is None:
            self._codex_login_proc.terminate()
            try:
                await asyncio.wait_for(self._codex_login_proc.wait(), timeout=2)
            except Exception:
                self._codex_login_proc.kill()
            self._codex_login_proc = None

        try:
            proc = await asyncio.create_subprocess_exec(
                "codex",
                "logout",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            output_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = output_bytes.decode(errors="ignore").strip()
            if proc.returncode == 0:
                await update.message.reply_text("Logged out of Codex.")
            else:
                await update.message.reply_text(
                    "Codex logout returned a non-zero status."
                    + (f"\n\nOutput: {output[:300]}" if output else "")
                )
        except FileNotFoundError:
            await update.message.reply_text(
                "Codex CLI not found. Install with: npm install -g @openai/codex"
            )
        except asyncio.TimeoutError:
            await update.message.reply_text("Timed out during Codex logout. Try again.")
        except Exception as exc:
            logger.error(f"Codex logout error: {exc}")
            await update.message.reply_text(f"Error during Codex logout: {exc}")

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
