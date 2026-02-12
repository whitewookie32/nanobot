"""
Codex OAuth - wrapper for official OpenAI Codex CLI.
Works on headless servers via device code flow.
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable


class CodexOAuthFlow:
    """Handle Codex OAuth using the official CLI."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path) if config_path else Path.home() / ".codex" / "config.json"
        self.codex_home = Path.home() / ".codex"
        self._proc: Optional[subprocess.Popen] = None
        self._lines: List[str] = []
        self._done = threading.Event()
        self._success = False
    
    @staticmethod
    def is_installed() -> bool:
        return shutil.which("codex") is not None
    
    def _env(self) -> Dict[str, str]:
        e = os.environ.copy()
        e["CODEX_HOME"] = str(self.codex_home)
        return e
    
    def load(self) -> Optional[Dict]:
        if not self.config_path.exists():
            return None
        try:
            with open(self.config_path) as f:
                return json.load(f)
        except:
            return None
    
    def is_authenticated(self) -> bool:
        return bool(self.load())
    
    def get_status(self) -> Dict:
        tokens = self.load()
        return {
            "installed": self.is_installed(),
            "authenticated": self.is_authenticated(),
            "config_path": str(self.config_path),
            "config_exists": self.config_path.exists(),
            "tokens": {k: v for k, v in (tokens or {}).items() if k != "access_token"} if tokens else None
        }
    
    def _extract(self, lines: List[str]) -> Dict[str, str]:
        """Extract URL and code from CLI output."""
        text = " ".join(lines)
        url = ""
        code = ""
        
        # Find URL
        m = re.search(r"(https?://auth\.openai\.com/[^\s\)\"']*)", text)
        if m:
            url = m.group(1).rstrip(").,'\"")
        
        # Find code (format: XXXX-XXXX or XXXX-XXXX-XXXX-XXXX)
        m = re.search(r"\b([A-Z0-9]{4}-[A-Z0-9]{4}(?:-[A-Z0-9]{4})?)\b", text)
        if m:
            code = m.group(1)
        
        return {"url": url, "code": code}
    
    def start_login(self) -> Dict[str, Any]:
        """Start device auth. Returns URL and code to display."""
        if not self.is_installed():
            return {"ok": False, "error": "codex CLI not installed"}
        
        if self._proc and self._proc.poll() is None:
            return {"ok": False, "error": "Login already in progress"}
        
        self._lines = []
        self._done.clear()
        self._success = False
        
        try:
            self._proc = subprocess.Popen(
                ["codex", "login", "--device-auth"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=self._env(),
                bufsize=1
            )
        except Exception as e:
            return {"ok": False, "error": str(e)}
        
        def _read():
            if self._proc and self._proc.stdout:
                for line in self._proc.stdout:
                    s = line.strip()
                    if s:
                        self._lines.append(s)
            if self._proc:
                self._success = (self._proc.wait() == 0)
            self._done.set()
        
        threading.Thread(target=_read, daemon=True).start()
        time.sleep(1)  # Wait for initial output
        
        info = self._extract(self._lines)
        return {
            "ok": True,
            "running": True,
            "url": info.get("url", ""),
            "code": info.get("code", ""),
            "message": self._format_msg(info)
        }
    
    def _format_msg(self, info: Dict[str, str]) -> str:
        url = info.get("url", "")
        code = info.get("code", "")
        
        msg = "🔐 Codex Authentication\n\n"
        msg += "This is a headless server. Complete on your phone/computer:\n\n"
        
        if code:
            msg += f"📱 Visit: {url}\n"
            msg += f"🔑 Code: {code}\n\n"
        elif url:
            msg += f"📱 Visit: {url}\n\n"
        else:
            msg += "(Getting auth URL...)\n\n"
        
        msg += "Waiting for you to authorize..."
        return msg
    
    def check_status(self) -> Dict[str, Any]:
        """Check current login status."""
        if not self._proc:
            return {"running": False, "authenticated": self.is_authenticated()}
        
        is_running = self._proc.poll() is None
        info = self._extract(self._lines)
        
        if self._done.is_set() or not is_running:
            return {
                "running": False,
                "authenticated": self.is_authenticated(),
                "url": info.get("url"),
                "code": info.get("code"),
                "output": self._lines[-10:]  # Last 10 lines
            }
        
        return {
            "running": True,
            "url": info.get("url"),
            "code": info.get("code"),
            "output": self._lines[-5:]
        }
    
    def wait(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Wait for login to complete."""
        if not self._proc:
            return {"success": False, "error": "Not started"}
        
        if timeout:
            self._done.wait(timeout)
        else:
            self._done.wait()
        
        return self.check_status()
    
    def logout(self) -> bool:
        """Logout and remove tokens."""
        if self.config_path.exists():
            self.config_path.unlink()
        
        if self.is_installed():
            try:
                subprocess.run(["codex", "logout"], capture_output=True, env=self._env(), timeout=10)
            except:
                pass
        
        return not self.config_path.exists()


# CLI functions
def login() -> Dict:
    """Interactive login - run this."""
    oauth = CodexOAuthFlow()
    
    if not oauth.is_installed():
        return {"ok": False, "error": "codex CLI not installed. Install: npm install -g @openai/codex"}
    
    if oauth.is_authenticated():
        s = oauth.get_status()
        return {"ok": True, "status": "authenticated", "email": s.get("tokens", {}).get("email")}
    
    result = oauth.start_login()
    if not result.get("ok"):
        return result
    
    # Show message
    print(result["message"])
    print("\nWaiting for authorization...")
    
    # Wait for completion
    final = oauth.wait(timeout=300)  # 5 min
    
    if final.get("authenticated"):
        s = oauth.get_status()
        return {"ok": True, "status": "success", "email": s.get("tokens", {}).get("email")}
    else:
        return {"ok": False, "error": "Authentication failed or timed out"}


def status() -> Dict:
    """Get auth status."""
    return CodexOAuthFlow().get_status()


def logout() -> Dict:
    """Logout."""
    success = CodexOAuthFlow().logout()
    return {"ok": success, "message": "Logged out" if success else "Not logged in"}


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "login"
    fn = {"login": login, "status": status, "logout": logout}.get(cmd, login)
    print(json.dumps(fn(), indent=2, default=str))
