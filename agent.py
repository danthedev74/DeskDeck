#!/usr/bin/env python3
"""
DeskDeck - turns a spare phone into a StandBy-style companion screen for your PC.

    python agent.py           real mode (Windows)
    python agent.py --demo    fake data on any OS, to preview the UI

Open the printed link on the phone. With Android + USB debugging, the agent
runs `adb reverse` for you, so the phone can use http://localhost:<port>.
"""
from __future__ import annotations

import sys

sys.coinit_flags = 0  # COM multithreaded apartment; must be set before comtypes is imported

import argparse
import asyncio
import ctypes
import datetime as dt
import hashlib
import json
import logging
import math
import os
import random
import re
import secrets
import shutil
import socket
import struct
import subprocess
import threading
import time
import urllib.parse
import warnings
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors="replace")
    except Exception:
        pass

try:
    import psutil
    from aiohttp import ClientSession, ClientTimeout, WSMsgType, web
except ImportError:
    print("Missing packages. Run:  pip install -r requirements.txt")
    raise SystemExit(1)

IS_WIN = sys.platform == "win32"
ROOT = Path(__file__).resolve().parent
try:
    VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
except Exception:
    VERSION = "dev"
WEB = ROOT / "web"
CONFIG_PATH = ROOT / "config.json"
PLAY_PATH = ROOT / "playtime.json"
DISCORD_PATH = ROOT / "discord.json"
UA = "DeskDeck/1.0 (personal desk dashboard)"
log = logging.getLogger("deskdeck")

# --------------------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "host": "0.0.0.0",
    "port": 8765,
    "token": "",
    "adb_reverse": True,
    "location": {"name": "Shah Alam", "lat": 3.0733, "lon": 101.5185},
    "ping": {"host": "1.1.1.1", "port": 443},
    "f1_favourite": "sainz",
    "photos_dir": "~/Pictures/DeskDeck",
    "lhm_url": "http://127.0.0.1:8085/data.json",
    "lyrics_offset": 0.3,
    # where files sent from the phone/iPad land ("" = your Downloads folder)
    "drop_dir": "",
    # game clips: "gamebar" (Win+Alt+G, needs background recording on) or "nvidia" (Alt+F10, needs Instant Replay on)
    "capture_tool": "gamebar",
    # folders the Captures gallery shows (newest first); empty = Game Bar, NVIDIA, AMD and Screenshots folders
    "capture_dirs": [],
    # Discord voice: your own app from discord.com/developers (OAuth2 client id + secret, redirect http://localhost)
    "discord": {"client_id": "", "client_secret": ""},
    # word-by-word lyric timing from NetEase Cloud Music when it has the song (falls back to LRCLIB lines)
    "word_lyrics": True,
    # Forza Horizon Data Out: set the game's Data Out port to "listen".
    # Every packet is passed on to "forward" so haptics apps (DSX, SimHub...) keep working.
    # FH6 Universal Radio mod (github.com/g0ldyy/fh6-universal-radio) web API
    "radio_url": "http://127.0.0.1:8420",
    # PC notifications on the Dynamic Island (Windows: Settings > Privacy > Notifications must allow apps)
    "notify": {"enabled": True, "block": []},
    # webhooks / Siri Shortcuts key (auto-generated) and optional tap actions for Room tiles:
    # "hook_actions": {"desk_led": {"on": "http://192.168.1.50/led?on=1", "off": "http://192.168.1.50/led?on=0"}}
    "hook_key": "",
    # updates from GitHub releases (tray > Check for updates; daily when auto_update is on), e.g. "danthedev74/deskdeck"
    "update_repo": "",
    "auto_update": True,
    # HTTPS for Wi-Fi screens (iPad): keeps the screen awake and makes clipboard work. 0 = off
    "https_port": 8766,
    "hook_actions": {},
    # Focus page: pomodoro lengths in minutes
    "focus": {"work": 25, "short": 5, "long": 15, "rounds": 4},
    # custom auto-page rules, e.g. [{"app": "obs64.exe", "page": "cc"}]
    "rules": [],
    # extra .exe names to treat as games, e.g. ["minecraft.exe"]
    "games": [],
    # community FH6 car-ordinal list (refreshed weekly; a copy ships in data/fh6_cars.json)
    "car_list_url": "https://raw.githubusercontent.com/darcane/LapScope/main/app/car_ordinals.json",
    "forza": {"listen": 5301, "forward": ["127.0.0.1:5300"], "auto_page": True, "launch": ""},
    "apps": [
        {"id": "discord", "label": "Discord", "icon": "bubble",
         "cmd": "\"%LOCALAPPDATA%\\Discord\\Update.exe\" --processStart Discord.exe"},
        {"id": "steam", "label": "Steam", "icon": "gamepad", "cmd": "steam://open/main"},
        {"id": "chrome", "label": "Chrome", "icon": "globe", "cmd": "chrome"},
        {"id": "files", "label": "Files", "icon": "folder", "cmd": "explorer"},
        {"id": "taskmgr", "label": "Task Mgr", "icon": "pulse", "cmd": "taskmgr"},
        {"id": "settings", "label": "Settings", "icon": "gear", "cmd": "ms-settings:"},
    ],
    # type: "keys" (combo like ctrl+shift+m), "text" (types it), "run" (command)
    "macros": [
        {"id": "cliphist", "label": "Clip History", "icon": "clipboard", "type": "keys", "value": "win+v"},
        {"id": "taskview", "label": "Task View", "icon": "windows", "type": "keys", "value": "win+tab"},
        {"id": "dcmute", "label": "Discord Mute", "icon": "mic.slash", "type": "keys", "value": "ctrl+shift+m"},
        {"id": "emoji", "label": "Emoji", "icon": "smile", "type": "keys", "value": "win+."},
    ],
}


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    user, broken = None, False
    if CONFIG_PATH.exists():
        try:
            user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            for k, v in user.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        except Exception as e:
            print(f"! config.json could not be read ({e}). Using defaults for this run.")
            broken = True
    if not cfg.get("token"):
        cfg["token"] = secrets.token_urlsafe(9)
    if not broken and (user is None or not user.get("token")):
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------

def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


# --------------------------------------------------------------------------------------
# HTTPS for Wi-Fi screens: a tiny local CA (trusted once on the iPad) signs the PC's cert
# --------------------------------------------------------------------------------------
CERT_DIR = ROOT / "certs"


def ensure_certs(ips):
    """Returns (cert, key) paths, (re)issuing the server cert when the LAN IP changes or it nears expiry."""
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError:
        return None
    import ipaddress
    CERT_DIR.mkdir(exist_ok=True)
    ca_key_p, ca_crt_p = CERT_DIR / "ca.key", CERT_DIR / "ca.crt"
    key_p, crt_p = CERT_DIR / "server.key", CERT_DIR / "server.crt"
    now = dt.datetime.now(dt.timezone.utc)
    pem = serialization.Encoding.PEM

    def write_key(k, p):
        p.write_bytes(k.private_bytes(pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))

    if ca_key_p.exists() and ca_crt_p.exists():
        ca_key = serialization.load_pem_private_key(ca_key_p.read_bytes(), None)
        ca_crt = x509.load_pem_x509_certificate(ca_crt_p.read_bytes())
    else:
        ca_key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"DeskDeck Local CA ({socket.gethostname()})"),
                          x509.NameAttribute(NameOID.ORGANIZATION_NAME, "DeskDeck")])
        ca_crt = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key())
                  .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
                  .not_valid_after(now + dt.timedelta(days=3650))
                  .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                  .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                               content_commitment=False, key_encipherment=False, data_encipherment=False,
                                               key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
                  .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
                  .sign(ca_key, hashes.SHA256()))
        write_key(ca_key, ca_key_p)
        ca_crt_p.write_bytes(ca_crt.public_bytes(pem))
        crt_p.unlink(missing_ok=True)
    want = sorted({ip for ip in ips if ip} | {"127.0.0.1"})
    host = socket.gethostname()
    if crt_p.exists() and key_p.exists():
        try:
            cur = x509.load_pem_x509_certificate(crt_p.read_bytes())
            san = cur.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            have = sorted(str(a) for a in san.get_values_for_type(x509.IPAddress))
            exp = getattr(cur, "not_valid_after_utc", None) or cur.not_valid_after.replace(tzinfo=dt.timezone.utc)
            if have == want and exp - now > dt.timedelta(days=30) and cur.issuer == ca_crt.subject:
                return crt_p, key_p
        except Exception:
            pass
    key = ec.generate_private_key(ec.SECP256R1())
    alt = [x509.DNSName("localhost"), x509.DNSName(host)] + [x509.IPAddress(ipaddress.ip_address(i)) for i in want]
    crt = (x509.CertificateBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"DeskDeck on {host}")]))
           .issuer_name(ca_crt.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
           .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=397))
           .add_extension(x509.SubjectAlternativeName(alt), critical=False)
           .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
           .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=False, content_commitment=False,
                                        data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                                        encipher_only=False, decipher_only=False), critical=True)
           .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
           .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
           .sign(ca_key, hashes.SHA256()))
    write_key(key, key_p)
    crt_p.write_bytes(crt.public_bytes(pem))
    return crt_p, key_p


def app_label(aumid: str) -> str:
    low = (aumid or "").lower()
    known = {
        "applemusic": "Apple Music", "spotify": "Spotify", "youtube-music": "YouTube Music",
        "youtubemusic": "YouTube Music", "msedge": "Edge", "chrome": "Chrome", "firefox": "Firefox",
        "brave": "Brave", "opera": "Opera", "308046b0af4a39cb": "Firefox", "vlc": "VLC", "tidal": "TIDAL", "foobar": "foobar2000",
        "zunemusic": "Media Player", "zunevideo": "Media Player", "deezer": "Deezer",
    }
    for k, v in known.items():
        if k in low:
            return v
    name = re.split(r"[!\\/]", aumid or "")[-1]
    name = re.sub(r"\.exe$", "", name, flags=re.I)
    return name[:24] or "Media"


def clean_title(t: str) -> str:
    t = re.sub(r"\s*[\(\[][^\)\]]*(official|lyric|audio|video|visuali[sz]er|remaster|explicit|\bmv\b|\bhd\b|4k)[^\)\]]*[\)\]]",
               "", t, flags=re.I)
    return t.strip() or t


def clean_artist(a: str) -> str:
    a = re.sub(r"\s*-\s*Topic$", "", a)
    a = re.sub(r"VEVO$", "", a)
    return a.strip()


_JUNK = (r"official|music\s*video|lyrics?|audio|video|visuali[sz]er|\bm\s*/?\s*v\b|\bhd\b|\bhq\b|\b4k\b|"
         r"remaster(?:ed)?|explicit|color\s*coded|eng\s*sub|full\s*album|performance\s*video|live\s*session")
_DESC = re.compile(r"\(?\s*(?:re-?mix|remaster|\d{4}\s+remaster|live\b|acoustic|version|edit\b|radio\s+edit|extended|mix\b|"
                   r"instrumental|from\b|feat|ft\.|sped\s*up|slowed|nightcore|demo\b|mono\b|stereo\b|bonus|single\b)", re.I)
_NORM = lambda x: re.sub(r"[^a-z0-9]", "", (x or "").lower())


def clean_track(title: str, artist: str):
    """YouTube-style 'Artist - Song (Official Video)' by 'ArtistVEVO' -> ('Song', 'Artist')."""
    t, a = (title or "").strip(), (artist or "").strip()
    raw_a = a
    a = re.sub(r"\s*-\s*Topic$", "", a, flags=re.I)
    a = re.sub(r"\s*VEVO$", "", a, flags=re.I)
    a = re.sub(r"\s+(official|music)(\s+channel)?$", "", a, flags=re.I).strip()
    channelish = a != raw_a
    t = re.sub(rf"\s*[\(\[【][^\)\]】]*(?:{_JUNK})[^\)\]】]*[\)\]】]", "", t, flags=re.I)
    t = re.sub(r"\s+(?:\||｜|//)\s+.*$", "", t)
    t = re.sub(r"\s*[-–—:]?\s*(?:official\s+)?(?:music\s+)?(?:lyric\s+)?(?:video|audio|visuali[sz]er|lyrics)\s*$",
               "", t, flags=re.I)
    m = re.match(r"^(.+?)\s+[-–—]\s+(.+)$", t)
    if m and not _DESC.match(m.group(2)):
        left, right = m.group(1).strip(), m.group(2).strip()
        na, nr = _NORM(a), _NORM(right)
        if na and nr and (nr == na or (len(na) > 3 and na in nr)) and not channelish:
            t = left                      # "Song - Artist"
        else:
            a, t = left, right            # "Artist - Song" (uploader is the artist, a label or a lyrics channel)
    t = re.sub(r"\s{2,}", " ", t).strip(" -–—|") or (title or "").strip()
    a = re.sub(r"\s{2,}", " ", a).strip() or (artist or "").strip()
    return t, a


LRC_TAG = re.compile(r"\[(\d+):(\d+(?:[.:]\d+)?)\]")


WORD_TAG = re.compile(r"<(\d+):(\d+(?:[.:]\d+)?)>")


def _lrc_t(m, s):
    return round(int(m) * 60 + float(s.replace(":", ".")), 3)


def parse_lrc(text: str) -> list:
    out = []
    for raw in (text or "").splitlines():
        tags = LRC_TAG.findall(raw)
        if not tags:
            continue
        line = WORD_TAG.sub("", LRC_TAG.sub("", raw)).strip()
        line = re.sub(r"\s{2,}", " ", line)
        for m, s in tags:
            out.append([_lrc_t(m, s), line])
    out.sort(key=lambda x: x[0])
    return out


def parse_lrc_words(text: str):
    """Enhanced LRC ("[00:12.00]<00:12.00>Every <00:12.40>thing") -> (lines, words) or None."""
    if not WORD_TAG.search(text or ""):
        return None
    lines, words = [], []
    for raw in (text or "").splitlines():
        tags = LRC_TAG.findall(raw)
        if not tags:
            continue
        body = LRC_TAG.sub("", raw)
        parts = WORD_TAG.split(body)          # [pre, m, s, text, m, s, text, ...]
        ws = []
        for i in range(1, len(parts) - 2, 3):
            t0 = _lrc_t(parts[i], parts[i + 1])
            txt = parts[i + 2]
            if txt.strip():
                ws.append([t0, None, txt])
        for k, w in enumerate(ws):
            nxt = ws[k + 1][0] if k + 1 < len(ws) else None
            w[1] = nxt if nxt is not None else round(w[0] + max(0.35, min(1.2, len(w[2].strip()) * 0.09)), 3)
        line = re.sub(r"\s{2,}", " ", WORD_TAG.sub("", body)).strip()
        lines.append([_lrc_t(*tags[0]), line])
        words.append(ws or None)
    order = sorted(range(len(lines)), key=lambda i: lines[i][0])
    lines = [lines[i] for i in order]
    words = [words[i] for i in order]
    if not any(words):
        return None
    return lines, words


YRC_WORD = re.compile(r"\((\d+),(\d+),-?\d+\)")
YRC_LINE = re.compile(r"^\[(\d+),(\d+)\](.*)$")


def parse_yrc(text: str):
    """NetEase word-by-word lyrics: "[16210,3460](16210,670,0)Every(16880,410,0)thing ..." -> (lines, words)."""
    lines, words = [], []
    for raw in (text or "").splitlines():
        m = YRC_LINE.match(raw.strip())
        if not m:
            continue                           # JSON credit lines etc.
        parts = YRC_WORD.split(m.group(3))   # [pre, start, dur, text, start, dur, text, ...]
        ws = []
        for i in range(1, len(parts) - 2, 3):
            t0 = int(parts[i]) / 1000
            t1 = t0 + int(parts[i + 1]) / 1000
            txt = parts[i + 2]
            if txt:
                ws.append([round(t0, 3), round(t1, 3), txt])
        text_line = re.sub(r"\s{2,}", " ", "".join(w[2] for w in ws)).strip()
        if not text_line:
            continue
        lines.append([round(int(m.group(1)) / 1000, 3), text_line])
        words.append(ws)
    if len(lines) < 4:
        return None
    return lines, words


def _norm_song(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\s*[\(\[].*?[\)\]]", "", s)            # (feat. x), [Remastered]
    s = re.sub(r"\s+-\s+.*$", "", s)                      # " - Radio Edit"
    s = re.sub(r"\b(feat|ft)\.?\b.*$", "", s)
    return re.sub(r"[^a-z0-9\u00c0-\uffff]", "", s)


def png_bytes(w: int, h: int, px) -> bytes:
    rows = []
    for y in range(h):
        row = bytearray(b"\x00")
        for x in range(w):
            row.extend(px(x, y))
        rows.append(bytes(row))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b""))


def sniff_type(b: bytes) -> str:
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    if b[:3] == b"GIF":
        return "image/gif"
    return "application/octet-stream"


# --------------------------------------------------------------------------------------
# Windows keyboard input
# --------------------------------------------------------------------------------------

VK = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "tab": 0x09,
    "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B, "space": 0x20, "backspace": 0x08,
    "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "home": 0x24, "end": 0x23, "pageup": 0x21,
    "pagedown": 0x22, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "printscreen": 0x2C,
    "prtsc": 0x2C, ".": 0xBE, ",": 0xBC, "-": 0xBD, "=": 0xBB, ";": 0xBA, "/": 0xBF, "`": 0xC0,
    "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE, "playpause": 0xB3, "nexttrack": 0xB0,
    "prevtrack": 0xB1, "volup": 0xAF, "voldown": 0xAE, "volmute": 0xAD,
}
EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2C, 0x2D, 0x2E, 0x5B, 0x5C,
            0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB3}


def vk_of(name: str) -> int:
    n = name.strip().lower()
    if n in VK:
        return VK[n]
    if re.fullmatch(r"f([1-9]|1\d|2[0-4])", n):
        return 0x6F + int(n[1:])
    if len(n) == 1 and n.isalnum():
        return ord(n.upper())
    raise ValueError(f"unknown key '{name}'")


if IS_WIN:
    from ctypes import wintypes

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class _HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class _INPUTU(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]

    class _INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTU)]

    def _kin(vk=0, scan=0, flags=0) -> _INPUT:
        i = _INPUT()
        i.type = 1  # INPUT_KEYBOARD
        i.u.ki = _KEYBDINPUT(vk, scan, flags, 0, 0)
        return i

    def _send_inputs(seq):
        arr = (_INPUT * len(seq))(*seq)
        ctypes.windll.user32.SendInput(len(seq), arr, ctypes.sizeof(_INPUT))

    def send_keys(combo: str):
        vks = [vk_of(k) for k in combo.split("+") if k.strip()]
        seq = []
        for v in vks:
            seq.append(_kin(v, 0, 0x1 if v in EXTENDED else 0))
        for v in reversed(vks):
            seq.append(_kin(v, 0, (0x1 if v in EXTENDED else 0) | 0x2))
        _send_inputs(seq)

    def type_text(text: str):
        seq = []
        for ch in text.replace("\r\n", "\n"):
            if ch == "\n":
                seq += [_kin(0x0D), _kin(0x0D, 0, 0x2)]
                continue
            data = ch.encode("utf-16-le")
            for k in range(0, len(data), 2):
                unit = int.from_bytes(data[k:k + 2], "little")
                seq += [_kin(0, unit, 0x4), _kin(0, unit, 0x4 | 0x2)]
        for k in range(0, len(seq), 64):
            _send_inputs(seq[k:k + 64])
            time.sleep(0.005)

    # ---- window switching (focus an app that's already open instead of launching again)
    _u32 = ctypes.windll.user32
    _dwm = ctypes.windll.dwmapi
    _HW = wintypes.HWND
    for _fn, _args, _res in (
        ("IsWindowVisible", [_HW], wintypes.BOOL), ("IsIconic", [_HW], wintypes.BOOL),
        ("GetWindow", [_HW, wintypes.UINT], _HW), ("GetWindowLongW", [_HW, ctypes.c_int], ctypes.c_long),
        ("GetWindowTextLengthW", [_HW], ctypes.c_int),
        ("GetWindowTextW", [_HW, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
        ("GetClassNameW", [_HW, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
        ("GetWindowThreadProcessId", [_HW, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
        ("ShowWindow", [_HW, ctypes.c_int], wintypes.BOOL), ("SetForegroundWindow", [_HW], wintypes.BOOL),
        ("BringWindowToTop", [_HW], wintypes.BOOL), ("SwitchToThisWindow", [_HW, wintypes.BOOL], None),
        ("GetForegroundWindow", [], _HW),
        ("PostMessageW", [_HW, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], wintypes.BOOL),
    ):
        getattr(_u32, _fn).argtypes = _args
        getattr(_u32, _fn).restype = _res
    _dwm.DwmGetWindowAttribute.argtypes = [_HW, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    _WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, _HW, wintypes.LPARAM)
    _u32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]

    def list_windows():
        """Top-level app windows in Z-order (most recently used first)."""
        out = []

        def cb(hwnd, _):
            try:
                if not _u32.IsWindowVisible(hwnd) or _u32.GetWindow(hwnd, 4):  # GW_OWNER
                    return True
                if _u32.GetWindowLongW(hwnd, -20) & 0x80:  # WS_EX_TOOLWINDOW
                    return True
                cloaked = ctypes.c_int(0)
                _dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
                if cloaked.value:
                    return True
                n = _u32.GetWindowTextLengthW(hwnd)
                if n <= 0:
                    return True
                title = ctypes.create_unicode_buffer(n + 1)
                _u32.GetWindowTextW(hwnd, title, n + 1)
                cls = ctypes.create_unicode_buffer(256)
                _u32.GetClassNameW(hwnd, cls, 256)
                pid = wintypes.DWORD()
                _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                out.append((hwnd, pid.value, title.value, cls.value))
            except Exception:
                pass
            return True

        _u32.EnumWindows(_WNDENUMPROC(cb), 0)
        return out

    def find_app_windows(rules):
        names, found = {}, []
        for hwnd, pid, title, cls in list_windows():
            if pid not in names:
                try:
                    names[pid] = psutil.Process(pid).name().lower()
                except Exception:
                    names[pid] = ""
            for r in rules:
                if r.get("exe") and names[pid] != r["exe"].lower():
                    continue
                if r.get("cls") and cls != r["cls"]:
                    continue
                if r.get("title") and r["title"].lower() not in title.lower():
                    continue
                found.append(hwnd)
                break
        return found

    def focus_window(hwnd) -> bool:
        if _u32.IsIconic(hwnd):
            _u32.ShowWindow(hwnd, 9)  # SW_RESTORE
        _u32.SwitchToThisWindow(hwnd, True)
        _u32.SetForegroundWindow(hwnd)
        if _u32.GetForegroundWindow() != hwnd:
            _send_inputs([_kin(0x12), _kin(0x12, 0, 0x2)])  # unlock foreground
            _u32.SetForegroundWindow(hwnd)
        _u32.BringWindowToTop(hwnd)
        time.sleep(0.06)
        return _u32.GetForegroundWindow() == hwnd

    # ---- foreground window (rules engine) + RivaTuner FPS
    class _RECT(ctypes.Structure):
        _fields_ = [("l", wintypes.LONG), ("t", wintypes.LONG), ("r", wintypes.LONG), ("b", wintypes.LONG)]

    class _MONINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", _RECT), ("rcWork", _RECT), ("dwFlags", wintypes.DWORD)]

    _u32.GetWindowRect.argtypes = [_HW, ctypes.POINTER(_RECT)]
    _u32.MonitorFromWindow.argtypes = [_HW, wintypes.DWORD]
    _u32.MonitorFromWindow.restype = wintypes.HMONITOR
    _u32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONINFO)]
    _k32 = ctypes.windll.kernel32
    _k32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    _k32.OpenFileMappingW.restype = wintypes.HANDLE
    _k32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
    _k32.MapViewOfFile.restype = ctypes.c_void_p
    _k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]

    def foreground_info():
        hwnd = _u32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD()
        _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        n = _u32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(max(1, n + 1))
        _u32.GetWindowTextW(hwnd, buf, n + 1)
        cls = ctypes.create_unicode_buffer(256)
        _u32.GetClassNameW(hwnd, cls, 256)
        r, mi, full = _RECT(), _MONINFO(), False
        mi.cbSize = ctypes.sizeof(_MONINFO)
        _u32.GetWindowRect(hwnd, ctypes.byref(r))
        hm = _u32.MonitorFromWindow(hwnd, 2)
        if hm and _u32.GetMonitorInfoW(hm, ctypes.byref(mi)):
            m = mi.rcMonitor
            full = r.l <= m.l and r.t <= m.t and r.r >= m.r and r.b >= m.b
        if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Windows.UI.Core.CoreWindow"):
            full = False
        return {"pid": pid.value, "title": buf.value.strip(), "full": full}

    def rtss_fps(pid: int, exe: str = ""):
        """Frame rate from RivaTuner Statistics Server's shared memory (installed with MSI Afterburner)."""
        h = _k32.OpenFileMappingW(0x0004, False, "RTSSSharedMemoryV2")
        if not h:
            return None
        try:
            p = _k32.MapViewOfFile(h, 0x0004, 0, 0, 0)
            if not p:
                return None
            try:
                sig, _ver, esz, aoff, acnt = struct.unpack("<5I", ctypes.string_at(p, 20))
                if sig != 0x52545353 or not esz or not acnt:  # 'RTSS'
                    return None
                want = os.path.basename(exe or "").lower()
                for i in range(min(acnt, 256)):
                    raw = ctypes.string_at(p + aoff + i * esz, 284)
                    epid = struct.unpack_from("<I", raw, 0)[0]
                    if not epid:
                        continue
                    name = raw[4:264].split(b"\0", 1)[0].decode("mbcs", "ignore")
                    if epid != pid and not (want and os.path.basename(name).lower() == want):
                        continue
                    _fl, t0, t1, frames, ftime = struct.unpack_from("<5I", raw, 264)
                    fps = 1000.0 * frames / (t1 - t0) if t1 > t0 and frames else None
                    ft = ftime / 1000.0 if ftime else (1000.0 / fps if fps else None)
                    return {"fps": round(fps, 1) if fps else None, "ft": round(ft, 2) if ft else None}
                return None
            finally:
                _k32.UnmapViewOfFile(p)
        finally:
            _k32.CloseHandle(h)

# How to recognise each launcher's window. Custom apps can add "match" in config.json,
# e.g. "match": [{"exe": "Code.exe"}] or [{"cls": "...", "title": "..."}].
APP_MATCH = {
    "discord": [{"exe": "Discord.exe"}],
    "steam": [{"exe": "steamwebhelper.exe", "title": "Steam"}, {"exe": "steam.exe"}],
    "chrome": [{"exe": "chrome.exe"}],
    "files": [{"cls": "CabinetWClass"}],
    "taskmgr": [{"exe": "Taskmgr.exe"}],
    "settings": [{"exe": "ApplicationFrameHost.exe", "title": "Settings"}, {"exe": "SystemSettings.exe"}],
}
# Apps that only ever run one instance: launching again just re-shows the existing one.
SINGLE_INSTANCE = {"discord", "steam", "taskmgr", "settings"}


def guess_rules(cmd: str):
    exes = re.findall(r"([^\s\"\\/]+\.exe)\b", cmd or "", flags=re.I)
    if exes:
        return [{"exe": exes[-1]}]
    c = (cmd or "").strip().strip('"')
    if c and re.fullmatch(r"[\w\-.]+", c):
        return [{"exe": c + ".exe"}]
    return None


TILE_TYPES = ("app", "keys", "text", "link", "run")
TILE_SLOTS = {"apps": 6, "macros": 4}


def tile_type(t: dict) -> str:
    typ = t.get("type")
    if typ in TILE_TYPES:
        return typ
    return "app" if t.get("cmd") else "keys"


def out_label(name: str) -> str:
    """"Headphones (Danish's AirPods Pro)" -> "Danish's AirPods Pro", "SAMSUNG (NVIDIA High Def...)" -> "SAMSUNG"."""
    m = re.match(r"^(?:Headphones|Headset|Earphones|Speakers?)\s*\((.+)\)$", name or "", re.I)
    if m and not re.search(r"realtek|high definition|audio$", m.group(1), re.I):
        return re.sub(r"\s*Hands-Free.*$", "", m.group(1))
    return re.sub(r"\s*\(.*\)\s*$", "", name or "") or name


def safe_filename(name: str) -> str:
    name = re.split(r"[\\/]", name or "")[-1]
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name).strip(" .")
    if not name:
        name = "file"
    stem, dot, ext = name.rpartition(".")
    if dot and len(ext) <= 10:
        return stem[:120] + "." + ext
    return name[:130]


def unique_path(folder: Path, name: str) -> Path:
    p = folder / name
    if not p.exists():
        return p
    stem, ext = os.path.splitext(name)
    for i in range(2, 1000):
        q = folder / f"{stem} ({i}){ext}"
        if not q.exists():
            return q
    return folder / f"{stem} {secrets.token_hex(3)}{ext}"


def downloads_dir() -> Path:
    if IS_WIN:
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
            v, _ = winreg.QueryValueEx(k, "{374DE290-123F-4565-9164-39C4925E467B}")
            p = Path(os.path.expandvars(v))
            if p.is_dir():
                return p
        except Exception:
            pass
    return Path.home() / "Downloads"


_IPOLICY = None


def _policy_config():
    """IPolicyConfig (undocumented but stable since Windows 7): the only way to change the default output."""
    global _IPOLICY
    import comtypes
    from ctypes import c_int, c_void_p, c_wchar_p
    from comtypes import COMMETHOD, GUID, HRESULT, IUnknown
    if _IPOLICY is None:
        def m(name, n):
            return COMMETHOD([], HRESULT, name, *[(["in"], c_wchar_p if i == 0 else c_void_p, f"a{i}") for i in range(n)])

        class IPolicyConfig(IUnknown):
            _iid_ = GUID("{f8679f50-850a-41cf-9c72-430f290290c8}")
            _methods_ = [
                m("GetMixFormat", 2), m("GetDeviceFormat", 3), m("ResetDeviceFormat", 1), m("SetDeviceFormat", 3),
                m("GetProcessingPeriod", 4), m("SetProcessingPeriod", 2), m("GetShareMode", 2), m("SetShareMode", 2),
                m("GetPropertyValue", 4), m("SetPropertyValue", 4),
                COMMETHOD([], HRESULT, "SetDefaultEndpoint", (["in"], c_wchar_p, "id"), (["in"], c_int, "role")),
                COMMETHOD([], HRESULT, "SetEndpointVisibility", (["in"], c_wchar_p, "id"), (["in"], c_int, "vis")),
            ]
        _IPOLICY = IPolicyConfig
    return comtypes.CoCreateInstance(GUID("{870af99c-171d-4f9e-af0d-e63df40c2bc9}"), _IPOLICY, comtypes.CLSCTX_ALL)


CAP_EXT = {".mp4": "video", ".mov": "video", ".m4v": "video", ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image"}
CAP_DIRS = ["~/Videos/Captures", "~/Videos/NVIDIA", "~/Videos/Radeon ReLive", "~/Videos/AMD", "~/Pictures/Screenshots"]
CAP_KEYS = {"gamebar": {"clip": "win+alt+g", "shot": "win+alt+printscreen"},
            "nvidia": {"clip": "alt+f10", "shot": "alt+f1"}}


def cap_game(path: str, base: str = ""):
    """Best guess of the game a capture came from (Game Bar / NVIDIA / AMD file and folder names)."""
    p = Path(path)
    stem = p.stem
    stem = re.sub(r"\.DVR$", "", stem, flags=re.I)
    g = re.sub(r"\s+\d{4}[-.]\d{2}[-.]\d{2}.*$", "", stem).strip(" -_")
    if not g or g.lower().startswith(("screenshot", "capture", "replay", "desktop")) or g == stem and re.search(r"\d{6}", stem):
        par = p.parent.name
        if base and os.path.normcase(str(p.parent)) == os.path.normcase(base):
            return None
        if par.lower() not in ("captures", "nvidia", "radeon relive", "amd", "screenshots", "videos", "pictures", "desktop"):
            return par
        return None
    return g[:48]


def img_thumb(path: str, size: int = 480):
    from PIL import Image, ImageOps
    import io
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail((size, size))
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        out = io.BytesIO()
        im.save(out, "JPEG", quality=80)
        return out.getvalue()


def to_jpeg(data: bytes, size: int = 480):
    from PIL import Image
    import io
    with Image.open(io.BytesIO(data)) as im:
        im.thumbnail((size, size))
        im = im.convert("RGB")
        out = io.BytesIO()
        im.save(out, "JPEG", quality=80)
        return out.getvalue()


# --------------------------------------------------------------------------------------
# F1 live timing (the feed the official app uses: SignalR Core, no login needed for timing)
# --------------------------------------------------------------------------------------
F1_SESS_DUR = {"Practice 1": 3600, "Practice 2": 3600, "Practice 3": 3600, "Sprint Qualifying": 2700, "Sprint Shootout": 2700,
               "Sprint": 3600, "Qualifying": 4500, "Race": 9000}
F1_TOPICS = ["Heartbeat", "DriverList", "TimingData", "TimingAppData", "TimingStats", "LapCount", "TrackStatus", "SessionInfo",
             "SessionStatus", "ExtrapolatedClock", "RaceControlMessages", "WeatherData"]


def f1_merge(base, delta):
    """Apply a live timing delta: dicts merge, lists can be patched by index ("3": {...}), "_deleted" removes keys."""
    if isinstance(delta, dict):
        if isinstance(base, list):
            base = {str(i): v for i, v in enumerate(base)}
        if not isinstance(base, dict):
            base = {}
        for k, v in delta.items():
            if k == "_deleted":
                for d in v or []:
                    base.pop(str(d), None)
                continue
            base[k] = f1_merge(base.get(k), v)
        return base
    return delta


def _seq(x):
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        return [x[k] for k in sorted(x, key=lambda s: int(s) if str(s).isdigit() else 1e9)]
    return []


def f1_payload(st: dict) -> dict:
    info = st.get("SessionInfo") or {}
    meet = info.get("Meeting") or {}
    typ = info.get("Type") or ""
    name = info.get("Name") or typ
    drivers = st.get("DriverList") or {}
    tdat = st.get("TimingData") or {}
    lines = tdat.get("Lines") or {}
    app = (st.get("TimingAppData") or {}).get("Lines") or {}
    part = int(tdat.get("SessionPart") or 0)
    race = typ == "Race" or name in ("Race", "Sprint")
    rows = []
    for num, ln in lines.items():
        if not isinstance(ln, dict):
            continue
        d = drivers.get(num) if isinstance(drivers.get(num), dict) else {}
        stints = _seq((app.get(num) or {}).get("Stints"))
        cur = stints[-1] if stints else {}
        last = ln.get("LastLapTime") or {}
        best = ln.get("BestLapTime") or {}
        gap = ""
        if race:
            gap = ln.get("GapToLeader") or ""
            itv = (ln.get("IntervalToPositionAhead") or {}).get("Value") or ""
        else:
            stats = _seq(ln.get("Stats"))
            bl = _seq(ln.get("BestLapTimes"))
            if part and len(stats) >= part:
                gap = (stats[part - 1] or {}).get("TimeDiffToFastest") or ""
                itv = (stats[part - 1] or {}).get("TimeDiffToPositionAhead") or ""
            else:
                gap = ln.get("TimeDiffToFastest") or ""
                itv = ln.get("TimeDiffToPositionAhead") or ""
            if part and len(bl) >= part and (bl[part - 1] or {}).get("Value"):
                best = bl[part - 1]
        try:
            pos = int(ln.get("Position") or ln.get("Line") or 99)
        except ValueError:
            pos = 99
        age = cur.get("TotalLaps")
        rows.append({
            "n": num, "pos": pos, "tla": d.get("Tla") or num, "name": d.get("LastName") or d.get("BroadcastName") or "",
            "col": "#" + str(d.get("TeamColour") or "888888").lstrip("#"),
            "gap": str(gap), "int": str(itv), "laps": ln.get("NumberOfLaps"),
            "last": last.get("Value") or "", "lf": 2 if last.get("OverallFastest") else 1 if last.get("PersonalFastest") else 0,
            "best": best.get("Value") or "", "bf": 2 if best.get("OverallFastest") else 0,
            "tyre": str(cur.get("Compound") or "").upper()[:1] if cur.get("Compound") not in (None, "UNKNOWN") else "",
            "age": age if isinstance(age, int) else None, "new": str(cur.get("New")).lower() == "true",
            "pits": ln.get("NumberOfPitStops") or 0, "pit": bool(ln.get("InPit")), "pitout": bool(ln.get("PitOut")),
            "out": bool(ln.get("Retired") or ln.get("Stopped")), "ko": bool(ln.get("KnockedOut")),
        })
    rows.sort(key=lambda r: r["pos"])
    clock = st.get("ExtrapolatedClock") or {}
    lap = st.get("LapCount") or {}
    ts = st.get("TrackStatus") or {}
    wx = st.get("WeatherData") or {}
    msgs = _seq((st.get("RaceControlMessages") or {}).get("Messages"))[-6:][::-1]
    return {
        "on": True, "gp": meet.get("Name") or "", "circuit": (meet.get("Circuit") or {}).get("ShortName") or meet.get("Location") or "",
        "sess": name, "race": race, "part": part, "status": (st.get("SessionStatus") or {}).get("Status") or "",
        "lap": lap.get("CurrentLap"), "laps": lap.get("TotalLaps"),
        "clock": {"utc": clock.get("Utc"), "rem": clock.get("Remaining"), "run": bool(clock.get("Extrapolating"))},
        "track": str(ts.get("Status") or "1"), "trackMsg": ts.get("Message") or "",
        "wx": {"air": wx.get("AirTemp"), "track": wx.get("TrackTemp"), "rain": str(wx.get("Rainfall") or "0") not in ("0", "False", "false"),
               "hum": wx.get("Humidity"), "wind": wx.get("WindSpeed")},
        "rc": [{"utc": m.get("Utc"), "lap": m.get("Lap"), "cat": m.get("Category"), "flag": m.get("Flag") or "",
                "msg": m.get("Message") or ""} for m in msgs if isinstance(m, dict)],
        "rows": rows,
    }


class F1Live:
    BASE = "livetiming.formula1.com/signalrcore"
    RS = "\x1e"

    def __init__(self, eng: "Engine"):
        self.eng = eng
        self.st: dict = {}
        self.on = False
        self._sent = 0.0
        self._dirty = False

    def window(self):
        """Only connect around an actual session from the calendar (saves the feed from us)."""
        f1 = self.eng.hub.state.get("f1") or {}
        nxt = f1.get("next") or {}
        now = time.time()
        for s in nxt.get("sessions") or []:
            ts = s.get("ts") or 0
            if ts - 20 * 60 <= now <= ts + F1_SESS_DUR.get(s.get("k"), 7200) + 40 * 60:
                return True
        return False

    async def run(self):
        await asyncio.sleep(8)
        while True:
            if not self.eng.cfg.get("f1_live", True) or not (self.window() or self.eng.cfg.get("f1_live_always")):
                await asyncio.sleep(60)
                continue
            try:
                await self.session()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.info("F1 live timing: %s", e)
            if self.on:
                self.on = False
                await self.eng.hub.send("f1live", {"on": False})
            await asyncio.sleep(30)

    async def session(self):
        http = self.eng.http
        base = self.eng.cfg.get("f1_live_url") or ("https://" + self.BASE)
        hdr = {"User-Agent": UA}
        try:
            async with http.options(base + "/negotiate", headers=hdr) as r:
                await r.read()
        except Exception as e:
            log.debug("f1 pre-negotiate: %s", e)
        async with http.post(base + "/negotiate?negotiateVersion=1", headers=hdr) as r:
            r.raise_for_status()
            neg = await r.json(content_type=None)
        tok = neg.get("connectionToken") or neg.get("connectionId")
        wsu = re.sub(r"^http", "ws", base) + "?id=" + urllib.parse.quote(tok or "")
        async with http.ws_connect(wsu, headers=hdr, heartbeat=None, max_msg_size=0, timeout=20) as ws:
            await ws.send_str(json.dumps({"protocol": "json", "version": 1}) + self.RS)
            await ws.send_str(json.dumps({"type": 1, "invocationId": "1", "target": "Subscribe", "arguments": [F1_TOPICS]}) + self.RS)
            log.info("F1 live timing connected")
            self.st = {}
            pinger = asyncio.create_task(self._ping(ws))
            try:
                last_rx = time.monotonic()
                while True:
                    try:
                        msg = await ws.receive(timeout=40)
                    except asyncio.TimeoutError:
                        raise ConnectionError("feed went quiet")
                    if msg.type in (WSMsgType.CLOSED, WSMsgType.CLOSE, WSMsgType.ERROR):
                        raise ConnectionError("feed closed")
                    if msg.type != WSMsgType.TEXT:
                        continue
                    last_rx = time.monotonic()
                    for part in msg.data.split(self.RS):
                        if part.strip():
                            await self._handle(json.loads(part))
                    if self._dirty and time.monotonic() - self._sent > 1.0:
                        await self._publish()
                    if not self.window() and not self.eng.cfg.get("f1_live_always") and \
                            (self.st.get("SessionStatus") or {}).get("Status") in ("Finalised", "Ends", "Inactive"):
                        break
            finally:
                pinger.cancel()

    async def _ping(self, ws):
        while True:
            await asyncio.sleep(15)
            await ws.send_str('{"type":6}' + self.RS)
            if self._dirty:
                await self._publish()

    async def _handle(self, m):
        t = m.get("type")
        if t == 1 and m.get("target") == "feed":
            args = m.get("arguments") or []
            if len(args) >= 2 and isinstance(args[0], str) and not args[0].endswith(".z"):
                self.st[args[0]] = f1_merge(self.st.get(args[0]), args[1])
                self._dirty = True
        elif t == 3 and m.get("invocationId") == "1":
            res = m.get("result") or {}
            for k, v in res.items():
                if not k.endswith(".z"):
                    self.st[k] = v
            self._dirty = True
            if m.get("error"):
                log.info("F1 subscribe: %s", m.get("error"))
        elif t == 7:
            raise ConnectionError(m.get("error") or "closed by server")

    async def _publish(self):
        self._dirty = False
        self._sent = time.monotonic()
        if not self.st.get("TimingData") and not self.st.get("SessionInfo"):
            return
        self.on = True
        await self.eng.hub.send("f1live", f1_payload(self.st))


class DemoF1Live(F1Live):
    GRID = [("4", "NOR", "Norris", "FF8000"), ("81", "PIA", "Piastri", "FF8000"), ("1", "VER", "Verstappen", "3671C6"),
            ("6", "HAD", "Hadjar", "3671C6"), ("16", "LEC", "Leclerc", "E8002D"), ("44", "HAM", "Hamilton", "E8002D"),
            ("63", "RUS", "Russell", "27F4D2"), ("12", "ANT", "Antonelli", "27F4D2"), ("55", "SAI", "Sainz", "64C4FF"),
            ("23", "ALB", "Albon", "64C4FF"), ("14", "ALO", "Alonso", "229971"), ("18", "STR", "Stroll", "229971"),
            ("10", "GAS", "Gasly", "0093CC"), ("43", "COL", "Colapinto", "0093CC"), ("31", "OCO", "Ocon", "B6BABD"),
            ("87", "BEA", "Bearman", "B6BABD"), ("27", "HUL", "Hulkenberg", "BB0A30"), ("5", "BOR", "Bortoleto", "BB0A30"),
            ("30", "LAW", "Lawson", "6692FF"), ("41", "LIN", "Lindblad", "6692FF"), ("11", "PER", "Perez", "AAAAAD"),
            ("77", "BOT", "Bottas", "AAAAAD")]

    async def run(self):
        rnd = random.Random(7)
        order = [g[0] for g in self.GRID]
        rnd.shuffle(order)
        gaps = {n: i * 1.6 + rnd.random() for i, n in enumerate(order)}
        tyre = {n: [rnd.choice("MH"), rnd.randint(8, 22)] for n in order}
        pits = {n: 0 for n in order}
        best = {n: 999.0 for n in order}
        lap, total, track, rc = 23, 50, "1", []
        drv = {n: {"RacingNumber": n, "Tla": t, "LastName": ln, "TeamColour": c} for n, t, ln, c in self.GRID}
        self.on = True
        k = 0
        while True:
            k += 1
            if k % 4 == 0:
                lap = min(total, lap + 1)
                for n in order:
                    tyre[n][1] += 1
            # small gap changes, the odd overtake and pit stop
            for n in order[1:]:
                gaps[n] = max(0.2, gaps[n] + rnd.uniform(-0.35, 0.3))
            if rnd.random() < 0.18:
                i = rnd.randint(1, len(order) - 2)
                order[i], order[i + 1] = order[i + 1], order[i]
                gaps[order[i]], gaps[order[i + 1]] = sorted([gaps[order[i]], gaps[order[i + 1]]])
            pit = None
            if rnd.random() < 0.08:
                pit = rnd.choice(order[3:])
                pits[pit] += 1
                tyre[pit] = [rnd.choice("HM"), 0]
            if k % 23 == 0:
                track = {"1": "4", "4": "1"}[track] if track in ("1", "4") else "1"
                rc.append({"Utc": dt.datetime.utcnow().isoformat() + "Z", "Lap": lap, "Category": "SafetyCar" if track == "4" else "Flag",
                           "Flag": "" if track == "4" else "GREEN", "Message": "SAFETY CAR DEPLOYED" if track == "4" else "TRACK CLEAR"})
            if k % 9 == 0:
                n = rnd.choice(order)
                rc.append({"Utc": dt.datetime.utcnow().isoformat() + "Z", "Lap": lap, "Category": "Other", "Flag": "",
                           "Message": f"CAR {n} ({drv[n]['Tla']}) TIME 1:{rnd.randint(30, 33)}.{rnd.randint(100, 999)} DELETED - TRACK LIMITS AT TURN {rnd.randint(1, 17)}"})
            lines = {}
            gl = sorted(order, key=lambda n: order.index(n))
            lead = 0.0
            for i, n in enumerate(gl):
                lt = 92.0 + rnd.random() * 1.6
                pf = lt < best[n]
                best[n] = min(best[n], lt)
                cum = sum(gaps[x] for x in gl[1:i + 1]) / 3 if i else 0.0
                lines[n] = {"Position": str(i + 1), "Line": i + 1, "NumberOfLaps": lap, "NumberOfPitStops": pits[n], "InPit": n == pit,
                            "GapToLeader": f"LAP {lap}" if i == 0 else f"+{cum + lead:.3f}",
                            "IntervalToPositionAhead": {"Value": f"LAP {lap}" if i == 0 else f"+{gaps[n] / 3:.3f}"},
                            "LastLapTime": {"Value": f"1:{lt - 60:06.3f}", "PersonalFastest": pf, "OverallFastest": pf and lt <= min(best.values())},
                            "BestLapTime": {"Value": f"1:{best[n] - 60:06.3f}"}}
            st = {"SessionInfo": {"Meeting": {"Name": "Qatar Grand Prix", "Circuit": {"ShortName": "Lusail"}}, "Type": "Race", "Name": "Race"},
                  "SessionStatus": {"Status": "Started"}, "DriverList": drv, "TimingData": {"Lines": lines},
                  "TimingAppData": {"Lines": {n: {"Stints": [{"Compound": {"S": "SOFT", "M": "MEDIUM", "H": "HARD"}[tyre[n][0]],
                                                              "TotalLaps": tyre[n][1], "New": "true"}]} for n in order}},
                  "LapCount": {"CurrentLap": lap, "TotalLaps": total}, "TrackStatus": {"Status": track},
                  "WeatherData": {"AirTemp": "24.8", "TrackTemp": "29.6", "Rainfall": "0", "Humidity": "58.0", "WindSpeed": "2.1"},
                  "RaceControlMessages": {"Messages": rc[-8:]}}
            await self.eng.hub.send("f1live", f1_payload(st))
            await asyncio.sleep(2)


class DiscordRPC:
    """Discord's local RPC (named pipe): voice channel, who's talking, mute / deafen / leave.
    Needs your own Discord application (client id + secret); the first connect shows an Authorize prompt in Discord."""
    SCOPES = ["rpc", "rpc.voice.read", "rpc.voice.write"]

    def __init__(self, eng: "Engine"):
        self.eng = eng
        self.tr = None
        self.buf = b""
        self.wait: dict = {}
        self.ev = asyncio.Queue()
        self.ch = None              # {"id", "name", "guild"}
        self.users: dict = {}       # id -> {...}
        self.speaking: set = set()
        self.me = {"mute": False, "deaf": False}
        self.status = "off"         # off | setup | connecting | auth | ready | error
        self.err = ""
        self._pub = None

    # ---- payload for the phone
    def payload(self):
        users = sorted(self.users.values(), key=lambda u: u["name"].lower())   # stable order: no jumping around while people talk
        return {"status": self.status, "err": self.err, "ch": self.ch, "me": self.me,
                "users": [{**u, "sp": u["id"] in self.speaking} for u in users][:24]}

    async def publish(self, force=False):
        p = self.payload()
        s = json.dumps(p, sort_keys=True)
        if force or s != self._pub:
            self._pub = s
            await self.eng.hub.send("dvoice", p)

    # ---- pipe framing
    class _Proto(asyncio.Protocol):
        def __init__(self, rpc):
            self.rpc = rpc

        def data_received(self, data):
            self.rpc._feed(data)

        def connection_lost(self, exc):
            self.rpc._closed()

    def _feed(self, data):
        self.buf += data
        while len(self.buf) >= 8:
            op, ln = struct.unpack("<II", self.buf[:8])
            if len(self.buf) < 8 + ln:
                return
            body, self.buf = self.buf[8:8 + ln], self.buf[8 + ln:]
            try:
                msg = json.loads(body.decode("utf-8"))
            except Exception:
                continue
            if op == 3:          # ping
                self._write(4, msg)
                continue
            if op == 2:
                self._closed()
                return
            n = msg.get("nonce")
            if n and n in self.wait:
                f = self.wait.pop(n)
                if not f.done():
                    f.set_result(msg)
            else:
                self.ev.put_nowait(msg)

    def _closed(self):
        for f in self.wait.values():
            if not f.done():
                f.set_exception(ConnectionError("Discord closed the connection"))
        self.wait.clear()
        self.ev.put_nowait({"evt": "__closed"})
        self.tr = None

    def _write(self, op, obj):
        if self.tr is None:
            raise ConnectionError("not connected")
        data = json.dumps(obj).encode("utf-8")
        self.tr.write(struct.pack("<II", op, len(data)) + data)

    async def cmd(self, name, args=None, evt=None, timeout=10):
        nonce = secrets.token_hex(8)
        f = asyncio.get_running_loop().create_future()
        self.wait[nonce] = f
        msg = {"cmd": name, "args": args or {}, "nonce": nonce}
        if evt:
            msg["evt"] = evt
        self._write(1, msg)
        res = await asyncio.wait_for(f, timeout)
        if res.get("evt") == "ERROR":
            d = res.get("data") or {}
            raise RuntimeError(f"{name}: {d.get('message')} ({d.get('code')})")
        return res.get("data")

    # ---- tokens
    def _tokens(self):
        try:
            return json.loads(DISCORD_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_tokens(self, t):
        DISCORD_PATH.write_text(json.dumps(t, indent=2), encoding="utf-8")

    async def _token(self, cid, secret, code=None, refresh=None):
        data = {"client_id": cid, "client_secret": secret}
        if code:
            data.update(grant_type="authorization_code", code=code, redirect_uri="http://localhost")
        else:
            data.update(grant_type="refresh_token", refresh_token=refresh)
        async with self.eng.http.post("https://discord.com/api/oauth2/token", data=data) as r:
            js = await r.json(content_type=None)
            if r.status != 200 or "access_token" not in js:
                raise RuntimeError(f"token: {js.get('error_description') or js.get('error') or r.status}")
        js["expires_at"] = time.time() + float(js.get("expires_in", 604800)) - 120
        self._save_tokens(js)
        return js

    # ---- main loop
    async def run(self):
        while True:
            dc = self.eng.cfg.get("discord") or {}
            cid, secret = str(dc.get("client_id") or "").strip(), str(dc.get("client_secret") or "").strip()
            if not cid or not secret:
                if self.status != "setup":
                    self.status = "setup"
                    await self.publish()
                await asyncio.sleep(4)
                continue
            try:
                await self.session(cid, secret)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.info("Discord voice: %s", e)
                self.err = str(e)[:140]
                self.status = "error" if "pipe" not in str(e).lower() and "not running" not in str(e).lower() else "off"
            if self.tr is not None:
                try:
                    self.tr.close()
                except Exception:
                    pass
                self.tr = None
            self.ch, self.users, self.speaking = None, {}, set()
            await self.publish()
            await asyncio.sleep(8)

    async def _connect(self):
        loop = asyncio.get_running_loop()
        if not hasattr(loop, "create_pipe_connection"):
            raise RuntimeError("needs the Windows Proactor event loop")
        last = None
        for i in range(10):
            try:
                self.tr, _ = await loop.create_pipe_connection(lambda: self._Proto(self), rf"\\.\pipe\discord-ipc-{i}")
                return
            except Exception as e:
                last = e
        raise ConnectionError(f"Discord is not running ({last})")

    async def session(self, cid, secret):
        self.buf, self.ev = b"", asyncio.Queue()
        await self._connect()
        self.status, self.err = "connecting", ""
        self._write(0, {"v": 1, "client_id": cid})
        ready = await asyncio.wait_for(self.ev.get(), 10)
        if ready.get("evt") != "READY":
            raise RuntimeError(f"handshake: {ready.get('data') or ready}")
        tok = self._tokens()
        if tok.get("client_id") not in (None, cid):
            tok = {}
        if tok and tok.get("expires_at", 0) < time.time() and tok.get("refresh_token"):
            try:
                tok = await self._token(cid, secret, refresh=tok["refresh_token"])
            except Exception as e:
                log.info("Discord token refresh: %s", e)
                tok = {}
        if not tok.get("access_token"):
            self.status = "auth"
            await self.publish()
            res = await self.cmd("AUTHORIZE", {"client_id": cid, "scopes": self.SCOPES}, timeout=120)
            tok = await self._token(cid, secret, code=res["code"])
            tok["client_id"] = cid
            self._save_tokens(tok)
        try:
            await self.cmd("AUTHENTICATE", {"access_token": tok["access_token"]})
        except RuntimeError:
            self._save_tokens({})
            raise
        self.status = "ready"
        log.info("Discord voice connected")
        for e in ("VOICE_CHANNEL_SELECT", "VOICE_SETTINGS_UPDATE"):
            await self.cmd("SUBSCRIBE", {}, evt=e)
        vs = await self.cmd("GET_VOICE_SETTINGS") or {}
        self.me = {"mute": bool(vs.get("mute")), "deaf": bool(vs.get("deaf"))}
        sel = await self.cmd("GET_SELECTED_VOICE_CHANNEL")
        await self._select(sel)
        await self.publish(force=True)
        while True:
            m = await self.ev.get()
            evt, d = m.get("evt"), m.get("data") or {}
            if evt == "__closed":
                raise ConnectionError("Discord closed")
            if evt == "VOICE_CHANNEL_SELECT":
                cid_ = d.get("channel_id")
                await self._select(await self.cmd("GET_CHANNEL", {"channel_id": cid_}) if cid_ else None)
            elif evt == "VOICE_SETTINGS_UPDATE":
                self.me = {"mute": bool(d.get("mute")), "deaf": bool(d.get("deaf"))}
            elif evt in ("VOICE_STATE_CREATE", "VOICE_STATE_UPDATE"):
                self._user(d)
            elif evt == "VOICE_STATE_DELETE":
                uid = (d.get("user") or {}).get("id")
                self.users.pop(uid, None)
                self.speaking.discard(uid)
            elif evt == "SPEAKING_START":
                self.speaking.add(str(d.get("user_id")))
            elif evt == "SPEAKING_STOP":
                self.speaking.discard(str(d.get("user_id")))
            await self.publish()

    def _user(self, d):
        u = d.get("user") or {}
        uid = str(u.get("id") or "")
        if not uid:
            return
        vs = d.get("voice_state") or {}
        av = u.get("avatar")
        url = f"https://cdn.discordapp.com/avatars/{uid}/{av}.png?size=128" if av else \
            f"https://cdn.discordapp.com/embed/avatars/{(int(uid) >> 22) % 6 if uid.isdigit() else 0}.png"
        self.users[uid] = {"id": uid, "name": d.get("nick") or u.get("global_name") or u.get("username") or "?", "av": url,
                           "mute": bool(vs.get("mute") or vs.get("self_mute") or vs.get("suppress")),
                           "deaf": bool(vs.get("deaf") or vs.get("self_deaf"))}

    async def _select(self, ch):
        old = self.ch
        if old:
            for e in ("VOICE_STATE_CREATE", "VOICE_STATE_UPDATE", "VOICE_STATE_DELETE", "SPEAKING_START", "SPEAKING_STOP"):
                try:
                    await self.cmd("UNSUBSCRIBE", {"channel_id": old["id"]}, evt=e)
                except Exception:
                    pass
        self.users, self.speaking = {}, set()
        if not ch:
            self.ch = None
            return
        guild = None
        if ch.get("guild_id"):
            try:
                guild = (await self.cmd("GET_GUILD", {"guild_id": ch["guild_id"]}) or {}).get("name")
            except Exception:
                guild = None
        self.ch = {"id": ch.get("id"), "name": ch.get("name") or "Voice", "guild": guild, "since": int(time.time())}
        for vs in ch.get("voice_states") or []:
            self._user(vs)
        for e in ("VOICE_STATE_CREATE", "VOICE_STATE_UPDATE", "VOICE_STATE_DELETE", "SPEAKING_START", "SPEAKING_STOP"):
            await self.cmd("SUBSCRIBE", {"channel_id": ch.get("id")}, evt=e)

    async def action(self, what):
        if self.status != "ready":
            return
        if what == "mute":
            await self.cmd("SET_VOICE_SETTINGS", {"mute": not self.me["mute"]})
        elif what == "deaf":
            await self.cmd("SET_VOICE_SETTINGS", {"deaf": not self.me["deaf"]})
        elif what == "leave":
            await self.cmd("SELECT_VOICE_CHANNEL", {"channel_id": None, "force": True})


class DemoDiscord(DiscordRPC):
    async def run(self):
        people = [("1", "danthedev74"), ("2", "Aiman"), ("3", "Sam"), ("4", "Hafiz"), ("5", "Mei Ling")]
        self.status = "ready"
        self.ch = {"id": "c1", "name": "forza-convoy", "guild": "G14 Gang", "since": int(time.time()) - 1260}
        for uid, n in people:
            self.users[uid] = {"id": uid, "name": n, "av": f"https://cdn.discordapp.com/embed/avatars/{int(uid) % 6}.png",
                               "mute": n == "Hafiz", "deaf": False}
        while True:
            self.speaking = set(random.sample([u for u, n in people if n not in ("Hafiz",)], k=random.choice([0, 1, 1, 2])))
            self.users["1"]["mute"] = self.me["mute"]
            self.users["1"]["deaf"] = self.me["deaf"]
            if self.me["mute"]:
                self.speaking.discard("1")
            await self.publish()
            await asyncio.sleep(random.uniform(0.6, 1.8))

    async def action(self, what):
        if what in ("mute", "deaf"):
            self.me[what] = not self.me[what]
        elif what == "leave":
            log.info("[demo] discord leave")
        await self.publish()


# --------------------------------------------------------------------------------------
# Hub - fan-out to connected phones
# --------------------------------------------------------------------------------------

class Hub:
    def __init__(self):
        self.clients: set = set()
        self.state: dict = {}

    async def send(self, t: str, data: dict, keep: bool = True):
        msg = {"t": t, **data}
        if keep:
            self.state[t] = msg
        if not self.clients:
            return
        s = json.dumps(msg, separators=(",", ":"))
        for ws in list(self.clients):
            try:
                await ws.send_str(s)
            except Exception:
                self.clients.discard(ws)


# --------------------------------------------------------------------------------------
# Windows components
# --------------------------------------------------------------------------------------

class GpuPdh:
    """GPU 3D-engine utilisation the same way Task Manager reads it (any vendor,
    and it does not wake a sleeping dGPU)."""

    def __init__(self):
        import win32pdh
        self.pdh = win32pdh
        self.q = None
        self.util, self.mem = [], []
        self.built = 0.0

    def _build(self):
        pdh = self.pdh
        if self.q is not None:
            try:
                pdh.CloseQuery(self.q)
            except Exception:
                pass
        self.q = pdh.OpenQuery()
        self.util, self.mem = [], []
        for path in pdh.ExpandCounterPath(r"\GPU Engine(*engtype_3D)\Utilization Percentage"):
            try:
                self.util.append((path, pdh.AddCounter(self.q, path)))
            except Exception:
                pass
        try:
            for path in pdh.ExpandCounterPath(r"\GPU Adapter Memory(*)\Dedicated Usage"):
                try:
                    self.mem.append((path, pdh.AddCounter(self.q, path)))
                except Exception:
                    pass
        except Exception:
            pass
        pdh.CollectQueryData(self.q)
        self.built = time.monotonic()
        time.sleep(0.3)

    def read(self):
        pdh = self.pdh
        if self.q is None or time.monotonic() - self.built > 20:
            self._build()
        pdh.CollectQueryData(self.q)
        per = {}
        for path, h in self.util:
            try:
                v = pdh.GetFormattedCounterValue(h, pdh.PDH_FMT_DOUBLE)[1]
            except Exception:
                continue
            m = re.search(r"luid_(0x[0-9a-fA-F]+_0x[0-9a-fA-F]+)", path)
            key = m.group(1) if m else "gpu"
            per[key] = per.get(key, 0.0) + v
        util = min(100.0, max(per.values())) if per else 0.0
        vram = 0
        for _, h in self.mem:
            try:
                vram = max(vram, pdh.GetFormattedCounterValue(h, pdh.PDH_FMT_LARGE)[1])
            except Exception:
                pass
        return util, vram


class WinNotes:
    """New Windows toast notifications (WhatsApp, Discord, Outlook...) for the Dynamic Island.
    Needs: Settings > Privacy & security > Notifications > "Let apps access your notifications"."""

    def __init__(self):
        self.listener = None
        self.state = None
        self.retry_at = 0.0
        self.seen = set()
        self.primed = False

    async def poll(self):
        if self.state == "unsupported" or (self.state == "denied" and time.time() < self.retry_at):
            return []
        if self.listener is None:
            try:
                from winrt.windows.ui.notifications.management import (UserNotificationListener,
                                                                     UserNotificationListenerAccessStatus as St)
            except Exception:
                self.state = "unsupported"
                log.info("Notifications: winrt notification packages missing (pip install -r requirements.txt)")
                return []
            lst = UserNotificationListener.current
            try:
                st = await lst.request_access_async()
            except Exception:
                st = lst.get_access_status()
            if st != St.ALLOWED:
                if self.state != "denied":
                    log.info("Notifications: access not allowed - turn on Settings > Privacy > Notifications")
                self.state, self.retry_at = "denied", time.time() + 60
                return []
            self.listener, self.state = lst, "ok"
        from winrt.windows.ui.notifications import NotificationKinds, KnownNotificationBindings
        notes = await self.listener.get_notifications_async(NotificationKinds.TOAST)
        out, ids = [], set()
        for n in notes:
            nid = n.id
            ids.add(nid)
            if nid in self.seen:
                continue
            self.seen.add(nid)
            if not self.primed:
                continue  # don't replay what was already sitting in the notification centre
            try:
                app = n.app_info.display_info.display_name if n.app_info else ""
            except Exception:
                app = ""
            texts = []
            try:
                b = n.notification.visual.get_binding(KnownNotificationBindings.toast_generic)
                if b:
                    texts = [t.text for t in b.get_text_elements() if t.text]
            except Exception:
                pass
            if not texts and not app:
                continue
            out.append({"app": app, "title": texts[0] if texts else app, "body": " · ".join(texts[1:3])[:220]})
        self.seen &= ids
        self.primed = True
        return out[-3:]


class WinMedia:
    """Now playing via Windows' media session API (works with Apple Music, Spotify,
    YouTube Music, browsers - anything in the Windows media flyout)."""

    def __init__(self):
        self.mgr = None
        self.session = None
        self.props = None

    async def poll(self):
        if self.mgr is None:
            try:
                from winrt.runtime import ApartmentType, init_apartment
                init_apartment(ApartmentType.MULTI_THREADED)
            except Exception:
                pass  # already initialised
            from winrt.windows.media.control import \
                GlobalSystemMediaTransportControlsSessionManager as Mgr
            self.mgr = await Mgr.request_async()
        s = self.mgr.get_current_session()
        self.session = s
        if s is None:
            return None
        props = await s.try_get_media_properties_async()
        if props is None:
            return None
        self.props = props
        info = s.get_playback_info()
        playing = bool(info) and int(info.playback_status) == 4
        pos = dur = 0.0
        tl = s.get_timeline_properties()
        if tl is not None:
            start = tl.start_time.total_seconds()
            dur = max(0.0, tl.end_time.total_seconds() - start)
            pos = max(0.0, tl.position.total_seconds() - start)
            lu = tl.last_updated_time
            if playing and lu is not None and lu.year > 2000:
                if lu.tzinfo is None:
                    lu = lu.replace(tzinfo=dt.timezone.utc)
                delta = (dt.datetime.now(dt.timezone.utc) - lu).total_seconds()
                if 0 < delta < 6 * 3600:
                    pos += delta
            if dur > 0:
                pos = min(pos, dur)
        return {"app": s.source_app_user_model_id or "", "title": props.title or "",
                "artist": props.artist or "", "album": props.album_title or "",
                "playing": playing, "pos": pos, "dur": dur}

    async def art(self):
        props = self.props
        if props is None or props.thumbnail is None:
            return None
        from winrt.windows.storage.streams import Buffer, InputStreamOptions
        stream = await props.thumbnail.open_read_async()
        try:
            size = int(stream.size)
            if size <= 0 or size > 8_000_000:
                return None
            buf = Buffer(size)
            res = await stream.read_async(buf, size, InputStreamOptions.READ_AHEAD)
            mv = memoryview(res)
            return bytes(mv[: int(res.length)])
        finally:
            try:
                stream.close()
            except Exception:
                pass

    async def cmd(self, c: str, v=None):
        s = self.session
        if s is None:
            keys = {"toggle": "playpause", "next": "nexttrack", "prev": "prevtrack"}.get(c)
            if keys:
                send_keys(keys)
            return
        if c == "toggle":
            await s.try_toggle_play_pause_async()
        elif c == "next":
            await s.try_skip_next_async()
        elif c == "prev":
            await s.try_skip_previous_async()
        elif c == "seek" and v is not None:
            await s.try_change_playback_position_async(int(float(v) * 10_000_000))


class LoopbackSpectrum(threading.Thread):
    """Captures what the PC is playing (WASAPI loopback) and turns it into 24 bands."""
    BANDS = 24

    def __init__(self, out_name_fn):
        super().__init__(daemon=True, name="spectrum")
        self.out_name_fn = out_name_fn
        self.latest = None
        self.stamp = 0.0

    def run(self):
        try:
            import numpy as np
            import pyaudiowpatch as pa
        except ImportError as e:
            log.warning("Spectrum off (%s). pip install numpy PyAudioWPatch", e)
            return
        self.np = np
        while True:
            p = stream = None
            try:
                p = pa.PyAudio()
                dev = p.get_default_wasapi_loopback()
                opened_for = self.out_name_fn()
                sr = int(dev["defaultSampleRate"])
                ch = max(1, int(dev["maxInputChannels"]))
                self._setup(sr)
                stream = p.open(format=pa.paFloat32, channels=ch, rate=sr, input=True,
                                input_device_index=dev["index"], frames_per_buffer=1024,
                                stream_callback=self._callback(ch))
                stream.start_stream()
                log.info("Spectrum: listening to %s", dev.get("name"))
                while stream.is_active():
                    time.sleep(1.0)
                    cur = self.out_name_fn()
                    if opened_for is None:
                        opened_for = cur
                    elif cur and cur != opened_for:
                        log.info("Spectrum: output changed to %s", cur)
                        break
            except Exception as e:
                log.warning("Spectrum: %s", e)
                time.sleep(5)
            finally:
                try:
                    if stream:
                        stream.stop_stream()
                        stream.close()
                except Exception:
                    pass
                try:
                    if p:
                        p.terminate()
                except Exception:
                    pass
            time.sleep(0.5)

    def _setup(self, sr):
        np = self.np
        self.n = 2048
        self.win = np.hanning(self.n).astype(np.float32)
        self.norm = float(self.win.sum()) / 2.0
        self.buf = np.zeros(self.n, dtype=np.float32)
        freqs = np.fft.rfftfreq(self.n, 1.0 / sr)
        edges = np.geomspace(45.0, min(16000.0, sr / 2 - 200), self.BANDS + 1)
        idx = np.searchsorted(freqs, edges)
        for i in range(1, len(idx)):
            if idx[i] <= idx[i - 1]:
                idx[i] = idx[i - 1] + 1
        idx = np.minimum(idx, len(freqs) - 1)
        self.idx = idx
        centers = np.sqrt(edges[:-1] * edges[1:])
        self.tilt = (3.0 * np.log2(centers / 1000.0)).astype(np.float32)

    def _callback(self, ch):
        np = self.np

        def cb(in_data, frame_count, time_info, status):
            try:
                x = np.frombuffer(in_data, dtype=np.float32)
                if ch > 1:
                    x = x.reshape(-1, ch).mean(axis=1)
                k = len(x)
                if k >= self.n:
                    self.buf[:] = x[-self.n:]
                elif k:
                    self.buf[:-k] = self.buf[k:].copy()
                    self.buf[-k:] = x
                spec = np.abs(np.fft.rfft(self.buf * self.win)) / self.norm
                seg = spec[self.idx[0]:self.idx[-1]]
                mx = np.maximum.reduceat(seg, self.idx[:-1] - self.idx[0])
                db = 20.0 * np.log10(mx + 1e-9) + self.tilt
                self.latest = np.clip((db + 62.0) / 52.0, 0.0, 1.0).tolist()
                self.stamp = time.monotonic()
            except Exception:
                pass
            return (None, 0)  # paContinue

        return cb


def _com_thread_init():
    try:
        import comtypes
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
    except Exception:
        pass


class WinPlatform:
    def __init__(self, eng: "Engine"):
        self.eng = eng
        self._cpu_cache = {}
        self.com = ThreadPoolExecutor(1, thread_name_prefix="com", initializer=_com_thread_init)
        self.vol_cache: dict = {}
        self.out_name = None
        self.media = WinMedia()
        self.media_app = ""
        self.mode_override = (None, 0.0)
        try:
            self.gpu = GpuPdh()
        except Exception as e:
            self.gpu = None
            log.warning("GPU counters unavailable: %s", e)
        self.spec = LoopbackSpectrum(lambda: self.out_name)
        self.spec.start()
        self.self_key = sys.executable.replace("\\", "#").lower()

    async def _com(self, fn, *a):
        return await asyncio.get_running_loop().run_in_executor(self.com, fn, *a)

    async def _io(self, fn, *a):
        return await asyncio.get_running_loop().run_in_executor(self.eng.pool, fn, *a)

    # ---- stats
    def gpu_read(self):
        return self.gpu.read() if self.gpu else (None, None)

    # ---- audio endpoints (pycaw)
    def _dev(self, flow: int):
        import comtypes
        from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
        from pycaw.constants import CLSID_MMDeviceEnumerator, ERole
        from pycaw.pycaw import AudioUtilities
        en = comtypes.CoCreateInstance(CLSID_MMDeviceEnumerator, IMMDeviceEnumerator,
                                       comtypes.CLSCTX_INPROC_SERVER)
        try:
            d = en.GetDefaultAudioEndpoint(flow, ERole.eMultimedia.value)
        except Exception:
            return None
        did = d.GetId()
        c = self.vol_cache.get(flow)
        if c is not None and c.id == did:
            return c
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ad = AudioUtilities.CreateDevice(d)
        self.vol_cache[flow] = ad
        return ad

    def _vol_state(self):
        st = {"level": None, "muted": None, "mic": None, "out": None}
        out = self._dev(0)
        if out is not None:
            ev = out.EndpointVolume
            st["level"] = round(float(ev.GetMasterVolumeLevelScalar()), 3)
            st["muted"] = bool(ev.GetMute())
            st["out"] = out.FriendlyName
            self.out_name = st["out"]
        mic = self._dev(1)
        if mic is not None:
            st["mic"] = bool(mic.EndpointVolume.GetMute())
        return st

    def _vol_set(self, v: float):
        out = self._dev(0)
        if out is None:
            return
        ev = out.EndpointVolume
        ev.SetMasterVolumeLevelScalar(max(0.0, min(1.0, v)), None)
        if v > 0 and ev.GetMute():
            ev.SetMute(0, None)

    def _vol_mute(self):
        out = self._dev(0)
        if out is not None:
            ev = out.EndpointVolume
            ev.SetMute(0 if ev.GetMute() else 1, None)

    # ---- per-app volume (music only, not the system master)
    LABEL_PROCS = {"Apple Music": ("applemusic",), "Spotify": ("spotify",), "Chrome": ("chrome",),
                   "Edge": ("msedge",), "Firefox": ("firefox",), "Brave": ("brave",), "Opera": ("opera",),
                   "VLC": ("vlc",), "TIDAL": ("tidal",), "foobar2000": ("foobar2000",), "Deezer": ("deezer",),
                   "Media Player": ("microsoftmediaplayer", "zune", "musicui"), "YouTube Music": ("youtubemusic",)}

    def _music_sessions(self):
        from pycaw.pycaw import AudioUtilities
        if not self.media_app:
            return []
        hints = self.LABEL_PROCS.get(app_label(self.media_app))
        if not hints:
            base = re.split(r"[!\\/]", self.media_app)[-1]
            base = re.sub(r"\.exe$", "", base, flags=re.I)
            hints = (re.sub(r"[^a-z0-9]", "", base.lower())[:10],)
        hints = tuple(h for h in hints if h)
        out = []
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sessions = AudioUtilities.GetAllSessions()
        for ss in sessions:
            if ss.Process is None or ss.SimpleAudioVolume is None:
                continue
            try:
                flat = re.sub(r"[^a-z0-9]", "", (ss.Process.name() or "").lower())
            except Exception:
                continue
            if any(h in flat for h in hints):
                out.append(ss)
        return out

    def _appv_state(self):
        ss = self._music_sessions()
        if not ss:
            return None
        try:
            return round(float(ss[0].SimpleAudioVolume.GetMasterVolume()), 3)
        except Exception:
            return None

    def _appv_set(self, v: float):
        v = max(0.0, min(1.0, v))
        for ss in self._music_sessions():
            try:
                ss.SimpleAudioVolume.SetMasterVolume(v, None)
                ss.SimpleAudioVolume.SetMute(0, None)
            except Exception:
                pass

    def _mic_toggle(self):
        mic = self._dev(1)
        if mic is not None:
            ev = mic.EndpointVolume
            ev.SetMute(0 if ev.GetMute() else 1, None)

    async def vol_state(self):
        return await self._com(self._vol_state)

    async def vol_set(self, v):
        await self._com(self._vol_set, v)

    async def vol_mute(self):
        await self._com(self._vol_mute)

    async def mic_toggle(self):
        await self._com(self._mic_toggle)

    async def appv_state(self):
        return await self._com(self._appv_state)

    async def appv_set(self, v):
        await self._com(self._appv_set, v)

    # ---- output picker (speakers / headphones / AirPods / TV)
    def _outputs(self):
        import comtypes
        from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
        from pycaw.constants import CLSID_MMDeviceEnumerator
        from pycaw.pycaw import AudioUtilities
        en = comtypes.CoCreateInstance(CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER)
        try:
            cur = en.GetDefaultAudioEndpoint(0, 1).GetId()
        except Exception:
            cur = None
        col = en.EnumAudioEndpoints(0, 1)          # render devices that are plugged in / connected
        out = []
        for i in range(col.GetCount()):
            d = col.Item(i)
            did = d.GetId()
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    name = AudioUtilities.CreateDevice(d).FriendlyName or "Output"
            except Exception:
                name = "Output"
            out.append({"id": did, "name": name, "on": did == cur})
        out.sort(key=lambda o: (not o["on"], o["name"].lower()))
        return out

    def _output_set(self, did):
        pc = _policy_config()
        for role in (0, 1, 2):                      # console, multimedia, communications
            pc.SetDefaultEndpoint(did, role)

    async def outputs(self):
        return await self._com(self._outputs)

    async def output_set(self, did):
        await self._com(self._output_set, did)

    # ---- Start menu apps, for picking what a Control Center button opens
    def _start_apps(self):
        now = time.time()
        if getattr(self, "_sa", None) and now - self._sa[0] < 600:
            return self._sa[1]
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"],
                           capture_output=True, timeout=20, creationflags=0x08000000)
        items = json.loads(r.stdout.decode("utf-8", "replace") or "[]")
        if isinstance(items, dict):
            items = [items]
        junk = re.compile(r"uninstall|readme|help|documentation|website|release notes|license|manual|\bfaq\b", re.I)
        seen, out = set(), []
        for it in items:
            n, aid = (it.get("Name") or "").strip(), (it.get("AppID") or "").strip()
            if not n or not aid or junk.search(n) or n.lower() in seen or aid.lower().startswith(("http:", "https:")):
                continue
            seen.add(n.lower())
            out.append({"name": n, "id": aid})
        out.sort(key=lambda x: x["name"].lower())
        self._sa = (now, out)
        return out

    async def start_apps(self):
        return await self._io(self._start_apps)

    async def open_url(self, url):
        await self._io(os.startfile, url)

    async def reveal(self, path):
        await self._io(lambda: subprocess.Popen(f'explorer /select,"{path}"', creationflags=0x08000000))

    async def video_thumb(self, path):
        """Windows' own thumbnail for a video (the same one Explorer shows)."""
        from winrt.windows.storage import StorageFile
        from winrt.windows.storage.fileproperties import ThumbnailMode, ThumbnailOptions
        from winrt.windows.storage.streams import Buffer, InputStreamOptions
        f = await StorageFile.get_file_from_path_async(os.path.abspath(path))
        th = await f.get_thumbnail_async(ThumbnailMode.VIDEOS_VIEW, 480, ThumbnailOptions.RESIZE_THUMBNAIL)
        try:
            size = int(th.size)
            if size <= 0:
                return None
            buf = Buffer(size)
            res = await th.read_async(buf, size, InputStreamOptions.READ_AHEAD)
            data = bytes(memoryview(res)[: int(res.length)])
        finally:
            try:
                th.close()
            except Exception:
                pass
        return await self._io(to_jpeg, data)

    # ---- media
    async def media_poll(self):
        m = await self.media.poll()
        if m:
            self.media_app = m.get("app") or ""
        return m

    async def media_art(self):
        return await self.media.art()

    async def media_cmd(self, c, v=None):
        await self.media.cmd(c, v)

    def spectrum(self):
        return self.spec.latest, self.spec.stamp

    # ---- ON AIR (mic / camera in use, from Windows privacy registry)
    def _privacy(self):
        import winreg
        base = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"
        res = {"mic": [], "cam": []}

        def name_of(key):
            if "#" in key:
                return re.sub(r"\.exe$", "", key.split("#")[-1], flags=re.I)
            return key.split("_")[0].split(".")[-1]

        def scan(k, cap):
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                try:
                    sk = winreg.OpenKey(k, sub)
                except OSError:
                    continue
                if sub == "NonPackaged":
                    scan(sk, cap)
                    continue
                try:
                    stop = winreg.QueryValueEx(sk, "LastUsedTimeStop")[0]
                    start = winreg.QueryValueEx(sk, "LastUsedTimeStart")[0]
                except OSError:
                    continue
                if stop == 0 and start > 0 and sub.lower() != self.self_key:
                    n = name_of(sub)
                    if n and n not in res[cap]:
                        res[cap].append(n)

        for cap, key in (("mic", "microphone"), ("cam", "webcam")):
            try:
                scan(winreg.OpenKey(winreg.HKEY_CURRENT_USER, base + "\\" + key), cap)
            except OSError:
                pass
        return res

    async def privacy(self):
        return await self._io(self._privacy)

    # ---- G-Helper performance mode
    def _mode_get(self):
        name, until = self.mode_override
        if name and time.time() < until:
            return name
        p = Path(os.environ.get("APPDATA", "")) / "GHelper" / "config.json"
        if not p.exists():
            return None
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return name
        m = d.get("performance_mode")
        base = {0: "balanced", 1: "turbo", 2: "silent"}
        if m in base:
            return base[m]
        if isinstance(m, int):
            self.mode_name = d.get(f"mode_name_{m}") or "Custom"
            return "custom"
        return None

    async def mode_get(self):
        return await self._io(self._mode_get)

    async def mode_set(self, name):
        key = {"silent": "f16", "balanced": "f17", "turbo": "f18"}.get(name)
        if key:
            await self._io(send_keys, f"ctrl+shift+alt+{key}")
            self.mode_override = (name, time.time() + 4)

    # ---- actions
    def _launch(self, cmd):
        subprocess.Popen(f'start "" {os.path.expandvars(cmd)}', shell=True,
                         creationflags=0x08000000)

    async def launch(self, cmd):
        await self._io(self._launch, cmd)

    def _open_app(self, app):
        rules = app.get("match") or APP_MATCH.get(app.get("id")) or guess_rules(app.get("cmd", ""))
        wins = find_app_windows(rules) if rules else []
        if wins:
            fg = _u32.GetForegroundWindow()
            # already in front with several windows -> bring the oldest one up (cycles through them)
            target = wins[-1] if (fg in wins and len(wins) > 1) else wins[0]
            if focus_window(target):
                return "focused"
            if app.get("id") not in SINGLE_INSTANCE:
                return "focused"
        self._launch(app["cmd"])
        return "launched"

    async def open_app(self, app):
        return await self._io(self._open_app, app)

    # ---- Forza Horizon process control
    @staticmethod
    def _forza_procs():
        out = []
        for p in psutil.process_iter(["name"]):
            n = (p.info.get("name") or "").lower()
            if n.startswith("forzahorizon") and n.endswith(".exe"):
                out.append(p)
        return out

    def _forza_launch_cmd(self):
        custom = (self.eng.cfg.get("forza") or {}).get("launch")
        if custom:
            return custom
        if getattr(self, "_fz_cmd", None):
            return self._fz_cmd
        cmd = None
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\Apps\2483190")
            if winreg.QueryValueEx(k, "Installed")[0] == 1:
                cmd = "steam://rungameid/2483190"
        except OSError:
            pass
        if not cmd:  # Xbox app / Microsoft Store version
            try:
                r = subprocess.run(["powershell", "-NoProfile", "-Command",
                                    "(Get-StartApps | Where-Object Name -like '*Forza Horizon 6*' | Select-Object -First 1).AppID"],
                                   capture_output=True, text=True, timeout=15, creationflags=0x08000000)
                aid = (r.stdout or "").strip()
                if aid:
                    cmd = f"shell:AppsFolder\\{aid}"
            except Exception:
                pass
        self._fz_cmd = cmd or "steam://rungameid/2483190"
        return self._fz_cmd

    def _forza(self, v):
        procs = self._forza_procs()
        if v == "open":
            pids = {p.pid for p in procs}
            if pids:
                wins = [h for h, pid, _, _ in list_windows() if pid in pids]
                if wins and focus_window(wins[0]):
                    return "Switched to Forza"
                return "Forza is running"
            self._launch(self._forza_launch_cmd())
            return "Launching Forza Horizon 6"
        if not procs:
            return "Forza isn't running"
        if v == "kill":
            for p in procs:
                try:
                    p.kill()
                except Exception:
                    pass
            return "Forza force-closed"
        pids = {p.pid for p in procs}
        for h, pid, _, _ in list_windows():
            if pid in pids:
                _u32.PostMessageW(h, 0x0010, 0, 0)  # WM_CLOSE
        return "Closing Forza... (hold again to force quit)"

    async def forza(self, v):
        return await self._io(self._forza, v)

    async def forza_running(self):
        return bool(await self._io(self._forza_procs))

    def _foreground(self):
        fg = foreground_info()
        if not fg or not fg["pid"]:
            return None
        try:
            pr = psutil.Process(fg["pid"])
            fg["exe"] = pr.exe() or ""
            fg["name"] = pr.name() or ""
        except Exception:
            fg["exe"], fg["name"] = "", ""
        return fg

    async def foreground(self):
        return await self._io(self._foreground)

    async def notes(self):
        if not hasattr(self, "_notes"):
            self._notes = WinNotes()
        return await self._notes.poll()

    def _focus_named(self, name):
        key = re.sub(r"[^a-z0-9]", "", (name or "").lower())
        if not key:
            return False
        for hwnd, pid, title, cls in list_windows():
            try:
                pn = re.sub(r"[^a-z0-9]", "", psutil.Process(pid).name().lower().replace(".exe", ""))
            except Exception:
                pn = ""
            if key in pn or key in re.sub(r"[^a-z0-9]", "", title.lower()):
                return focus_window(hwnd)
        return False

    async def focus_named(self, name):
        return await self._io(self._focus_named, name)

    # ---- Wi-Fi details for the Health page
    def _wifi(self):
        try:
            out = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True,
                                 timeout=4, creationflags=0x08000000).stdout
        except Exception:
            return None
        d = {}
        for line in out.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k, v = k.strip().lower(), v.strip()
            if k == "ssid" and "ssid" not in d:
                d["ssid"] = v
            elif k == "signal":
                d["signal"] = int(re.sub(r"\D", "", v) or 0)
            elif k.startswith("receive rate"):
                d["rx"] = _num(v)
            elif k == "radio type":
                d["radio"] = v
        return d or None

    async def wifi(self):
        return await self._io(self._wifi)

    # ---- call controls: focus the call window, then press the app's own shortcut
    CALL_KEYS = {"teams": {"cam": "ctrl+shift+o", "hand": "ctrl+shift+k", "leave": "ctrl+shift+h"},
                 "zoom": {"cam": "alt+v", "hand": "alt+y", "leave": "alt+q"},
                 "meet": {"cam": "ctrl+e", "hand": "ctrl+alt+h"},
                 "discord": {}, "slack": {"cam": "v"}}

    @staticmethod
    def _call_family(key: str) -> str:
        k = (key or "").lower()
        if "teams" in k:
            return "teams"
        if k.startswith("zoom"):
            return "zoom"
        if k in ("chrome", "msedge", "firefox", "brave"):
            return "meet"
        return k

    def _call_window(self, key):
        fam = self._call_family(key)
        exes = {"teams": ("ms-teams.exe", "teams.exe", "msteams.exe"), "zoom": ("zoom.exe",),
                "meet": ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"), "discord": ("discord.exe",),
                "slack": ("slack.exe",)}.get(fam, (f"{fam}.exe",))
        best = None
        for hwnd, pid, title, cls in list_windows():
            try:
                name = psutil.Process(pid).name().lower()
            except Exception:
                continue
            if name not in exes:
                continue
            if fam == "meet" and not re.search(r"\bmeet\b|zoom|teams|whereby|jitsi", title, re.I):
                continue
            if best is None or re.search(r"meeting|call|meet", title, re.I):
                best = (hwnd, title)
        return best

    async def call_title(self, key):
        try:
            w = await self._io(self._call_window, key)
        except Exception:
            return None
        return w[1] if w else None

    async def call_action(self, key, cmd):
        combo = self.CALL_KEYS.get(self._call_family(key), {}).get(cmd)
        if not combo:
            return False

        def run():
            w = self._call_window(key)
            if not w or not focus_window(w[0]):
                return False
            time.sleep(0.12)
            send_keys(combo)
            return True
        return await self._io(run)

    # ---- heavy apps
    def _procs(self):
        me = None
        try:
            me = psutil.Process().username()
        except Exception:
            pass
        groups = {}
        for p in psutil.process_iter(["name", "username", "memory_info"]):
            try:
                name = (p.info.get("name") or "").lower()
                if not name or name in PROTECTED_PROCS:
                    continue
                if me and p.info.get("username") != me:
                    continue
                cached = self._cpu_cache.get(p.pid)
                if cached is None:
                    self._cpu_cache[p.pid] = p
                    p.cpu_percent(None)
                    c = 0.0
                else:
                    c = cached.cpu_percent(None)
                rss = p.info["memory_info"].rss if p.info.get("memory_info") else 0
                g = groups.setdefault(name, {"exe": name, "mem": 0, "cpu": 0.0, "n": 0})
                g["mem"] += rss
                g["cpu"] += c
                g["n"] += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        alive = set(psutil.pids())
        for pid in list(self._cpu_cache):
            if pid not in alive:
                self._cpu_cache.pop(pid, None)
        ncpu = psutil.cpu_count() or 1
        merged = {}
        for g in groups.values():
            nice = app_nice(g["exe"])
            m = merged.setdefault(nice, {"name": nice, "exe": [], "mem": 0, "cpu": 0.0, "n": 0})
            m["exe"].append(g["exe"])
            m["mem"] += g["mem"]
            m["cpu"] += g["cpu"] / ncpu
            m["n"] += g["n"]
        res = sorted(merged.values(), key=lambda x: x["mem"] + x["cpu"] * 60e6, reverse=True)[:6]
        for r in res:
            r["mem"] = round(r["mem"] / 2**20)
            r["cpu"] = round(r["cpu"], 1)
        return res

    async def procs(self):
        return await self._io(self._procs)

    def _kill(self, exes):
        me = None
        try:
            me = psutil.Process().username()
        except Exception:
            pass
        n = 0
        for p in psutil.process_iter(["name", "username"]):
            try:
                name = (p.info.get("name") or "").lower()
                if name in exes and name not in PROTECTED_PROCS and (not me or p.info.get("username") == me):
                    p.terminate()
                    n += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return n

    async def kill(self, exes):
        return await self._io(self._kill, [e.lower() for e in exes])

    async def fps(self, pid, exe):
        return await self._io(rtss_fps, pid, exe)

    async def keys(self, combo):
        await self._io(send_keys, combo)

    async def text(self, s):
        await self._io(type_text, s)

    async def sys_action(self, name):
        if name == "lock":
            ctypes.windll.user32.LockWorkStation()
            return
        combo = {"shot": "win+printscreen", "snip": "win+shift+s", "desk": "win+d",
                 "taskview": "win+tab", "gshot": "win+alt+printscreen", "gclip": "win+alt+g"}.get(name)
        if combo:
            await self.keys(combo)

    def _clip_get(self):
        import win32clipboard as wc
        import win32con
        for _ in range(10):
            try:
                wc.OpenClipboard()
                break
            except Exception:
                time.sleep(0.05)
        else:
            return ""
        try:
            if wc.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                return wc.GetClipboardData(win32con.CF_UNICODETEXT) or ""
            return ""
        finally:
            wc.CloseClipboard()

    def _clip_set(self, text):
        import win32clipboard as wc
        import win32con
        for _ in range(10):
            try:
                wc.OpenClipboard()
                break
            except Exception:
                time.sleep(0.05)
        else:
            raise RuntimeError("clipboard busy")
        try:
            wc.EmptyClipboard()
            wc.SetClipboardText(text, win32con.CF_UNICODETEXT)
        finally:
            wc.CloseClipboard()

    async def clip_get(self):
        return await self._io(self._clip_get)

    async def clip_set(self, text):
        await self._io(self._clip_set, text)

    async def laptop_extra(self):
        return {}

    def demo_lyrics(self, key):
        return None


# --------------------------------------------------------------------------------------
# Demo platform (any OS)
# --------------------------------------------------------------------------------------

DEMO_TRACKS = [
    {"title": "Afterglow Avenue", "artist": "Neon Harbor", "album": "City Static", "dur": 214,
     "lines": ["", "Streetlights hum a slower tune", "Windows down in late July",
               "Every sign is burning blue", "Like the city learned to fly", "",
               "Hold the wheel and hold the night", "Nothing here is out of reach",
               "We were chasing borrowed light", "Following the empty street", "",
               "Afterglow, afterglow", "Take the long way, take it slow", "Afterglow, afterglow",
               "Only we will ever know", "", "Morning waits behind the hill",
               "Let it wait a little more", "Engine idle, hearts are still",
               "Parked beside the dawn's front door"]},
    {"title": "Paper Planes at Dusk", "artist": "Mira Vale", "album": "Low Tide", "dur": 187,
     "lines": ["", "Folded every word I meant", "Threw them off the balcony",
               "Watched them drift where daylight went", "Hoping one comes back to me", "",
               "Paper planes at dusk", "Carry what I couldn't say", "Paper planes at dusk",
               "Gliding softly, far away", "", "Orange sky and quiet rooms",
               "Coffee cold beside the sill", "Every flight is something new",
               "Every landing, something still"]},
    {"title": "Kuala Rain", "artist": "Sora & The Lanterns", "album": "Monsoon Tapes", "dur": 236,
     "lines": ["", "Thunder rolling over town", "Mamak tables, plastic chairs",
               "Watch the four o'clock come down", "Steam is rising everywhere", "",
               "Oh the rain, the rain", "Sings the roof a lullaby", "Oh the rain, the rain",
               "Washing out the evening sky", "", "Neon puddles on the road",
               "Motorbikes in silver lines", "Every gutter overflowed",
               "Every heart is keeping time"]},
]


def demo_art(i: int) -> bytes:
    S = 256

    def px(x, y):
        u, v = x / S, y / S
        if i == 0:  # dusk road
            r = int(255 * (0.95 - 0.55 * v)); g = int(255 * (0.35 + 0.15 * (1 - v)) * (1 - v * 0.6)); b = int(255 * (0.35 + 0.45 * v))
            d = math.hypot(u - 0.5, v - 0.55)
            if d < 0.2:
                r, g, b = 255, int(190 - d * 300), int(90 + d * 100)
            if v > 0.62:
                stripe = (int((v - 0.62) * 40) % 2 == 0) and abs(u - 0.5) < (v - 0.6) * 0.9
                r, g, b = (30, 12, 40) if not stripe else (255, 120, 170)
            return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))
        if i == 1:  # teal waves
            w = math.sin(u * 9 + math.sin(v * 5) * 2) * 0.5 + 0.5
            r = int(20 + 60 * w * (1 - v)); g = int(90 + 120 * (1 - v) * w); b = int(140 + 90 * w)
            d = math.hypot(u - 0.72, v - 0.28)
            if d < 0.09:
                r, g, b = 255, 236, 200
            return (min(255, r), min(255, g), min(255, b))
        # purple monsoon
        n = math.sin(u * 30 + v * 4) * 0.5 + 0.5
        r = int(70 + 120 * (1 - v) + 30 * n); g = int(30 + 40 * n); b = int(120 + 110 * v)
        if int((u * 14 + v * 22)) % 7 == 0:
            r, g, b = 255, 210, 120
        return (min(255, r), min(255, g), min(255, b))

    return png_bytes(S, S, px)


class DemoPlatform:
    def __init__(self, eng: "Engine"):
        self.eng = eng
        self.t0 = time.time()
        self.vol = {"level": 0.42, "muted": False, "mic": False, "out": "Speakers (Demo)"}
        self.mode = "balanced"
        self.clip = "Clipboard from your PC lands here."
        self._avol = 0.72
        self.ti, self.pos, self.playing = 0, 31.0, True
        self.last = time.monotonic()
        self.arts = [demo_art(i) for i in range(len(DEMO_TRACKS))]

    def _adv(self):
        now = time.monotonic()
        if self.playing:
            self.pos += now - self.last
        self.last = now
        if self.pos >= DEMO_TRACKS[self.ti]["dur"]:
            self.ti, self.pos = (self.ti + 1) % len(DEMO_TRACKS), 0.0

    def gpu_read(self):
        t = time.time()
        return 18 + 14 * math.sin(t / 7) + random.random() * 6, int(2.1e9 + 3e8 * math.sin(t / 30))

    async def vol_state(self):
        outs = await self.outputs()
        return {**self.vol, "out": next((o["name"] for o in outs if o["on"]), "Speakers")}

    async def vol_set(self, v):
        self.vol["level"] = round(max(0.0, min(1.0, float(v))), 3)
        if v > 0:
            self.vol["muted"] = False

    async def appv_state(self):
        return self._avol

    async def appv_set(self, v):
        self._avol = max(0.0, min(1.0, float(v)))

    async def vol_mute(self):
        self.vol["muted"] = not self.vol["muted"]

    async def mic_toggle(self):
        self.vol["mic"] = not self.vol["mic"]

    async def media_poll(self):
        self._adv()
        tr = DEMO_TRACKS[self.ti]
        return {"app": "AppleInc.AppleMusicWin_demo!App", "title": tr["title"], "artist": tr["artist"],
                "album": tr["album"], "playing": self.playing, "pos": self.pos, "dur": tr["dur"]}

    async def media_art(self):
        return self.arts[self.ti]

    async def media_cmd(self, c, v=None):
        self._adv()
        if c == "toggle":
            self.playing = not self.playing
        elif c == "next":
            self.ti, self.pos = (self.ti + 1) % len(DEMO_TRACKS), 0.0
        elif c == "prev":
            if self.pos > 3:
                self.pos = 0.0
            else:
                self.ti, self.pos = (self.ti - 1) % len(DEMO_TRACKS), 0.0
        elif c == "seek" and v is not None:
            self.pos = max(0.0, min(float(v), DEMO_TRACKS[self.ti]["dur"] - 1))

    def spectrum(self):
        if not self.playing:
            return None, 0.0
        t = time.monotonic()
        beat = max(0.0, 1 - ((t * 2.05) % 1.0) * 2.6)
        vals = []
        for i in range(24):
            base = 0.78 - i * 0.017
            wob = 0.16 * math.sin(t * (2.1 + i * 0.37) + i * 0.9) + 0.08 * math.sin(t * 7.3 + i)
            kick = beat * (0.35 if i < 5 else 0.1)
            vals.append(max(0.0, min(1.0, base + wob + kick - 0.25 + random.random() * 0.06)))
        return vals, t

    async def privacy(self):
        ph = (time.time() - self.t0) % 120
        return {"mic": ["Discord"] if 45 < ph < 75 else [], "cam": ["Chrome"] if 60 < ph < 75 else []}

    async def mode_get(self):
        return self.mode

    async def mode_set(self, name):
        if name in ("silent", "balanced", "turbo"):
            self.mode = name

    async def launch(self, cmd):
        log.info("[demo] launch %s", cmd)

    async def open_app(self, app):
        log.info("[demo] open/focus %s", app.get("label"))
        return "launched"

    async def forza(self, v):
        log.info("[demo] forza %s", v)
        return {"open": "Launching Forza Horizon 6", "quit": "Closing Forza...", "kill": "Forza force-closed"}.get(v, "")

    async def forza_running(self):
        return bool(self.eng.demo_forza)

    async def notes(self):
        t = time.time()
        if not hasattr(self, "_nt"):
            self._nt = t + 8
        if t >= self._nt:
            self._nt = t + 45
            return [random.choice([{"app": "WhatsApp", "title": "Ali", "body": "Weh jom lunch pukul 1? Aku belanja hari ni"},
                                   {"app": "Discord", "title": "#forza-club", "body": "Sam: anyone up for a convoy tonight?"},
                                   {"app": "Outlook", "title": "Weekly report", "body": "Reminder: send your weekly update before 5 PM"}])]
        return []

    async def focus_named(self, name):
        log.info("[demo] focus %s", name)
        return True

    async def wifi(self):
        return {"ssid": "Home_5G", "signal": 86, "rx": 1201.0, "radio": "802.11ax"}

    async def call_title(self, key):
        return "Daily stand-up | Microsoft Teams" if "teams" in key else "Voice · #general"

    async def call_action(self, key, cmd):
        log.info("[demo] call %s %s", key, cmd)
        return True

    async def procs(self):
        t = time.time()
        base = [("Forza Horizon 6", ["forzahorizon6.exe"], 9300, 38, 1), ("Google Chrome", ["chrome.exe"], 3270, 12, 24),
                ("Microsoft Teams", ["ms-teams.exe"], 1410, 6, 5), ("Discord", ["discord.exe"], 880, 3, 6),
                ("Steam", ["steam.exe", "steamwebhelper.exe"], 610, 4, 7), ("Apple Music", ["applemusic.exe"], 420, 1, 2)]
        gone = getattr(self, "_killed", set())
        return [{"name": n, "exe": e, "mem": int(m + 60 * math.sin(t / 7 + i)),
                 "cpu": round(max(0.1, c + 3 * math.sin(t / 5 + i)), 1), "n": k}
                for i, (n, e, m, c, k) in enumerate(base) if n not in gone]

    async def kill(self, exes):
        self._killed = getattr(self, "_killed", set()) | {app_nice(exes[0])}
        return 3

    async def foreground(self):
        if getattr(self.eng, "demo_game", False):
            return {"pid": 4242, "title": "VALORANT  ", "full": True, "name": "VALORANT-Win64-Shipping.exe",
                    "exe": r"C:\Riot Games\VALORANT\live\ShooterGame\Binaries\Win64\VALORANT-Win64-Shipping.exe"}
        return {"pid": 1, "title": "DeskDeck", "full": False, "name": "explorer.exe", "exe": r"C:\Windows\explorer.exe"}

    async def fps(self, pid, exe):
        if pid != 4242:
            return None
        t = time.time()
        f = 236 + 14 * math.sin(t / 3) + random.random() * 9 - (40 if random.random() < 0.04 else 0)
        return {"fps": round(f, 1), "ft": round(1000 / f, 2)}

    async def keys(self, combo):
        log.info("[demo] keys %s", combo)

    async def outputs(self):
        if not hasattr(self, "_outs"):
            self._outs = [{"id": "spk", "name": "Speakers (Realtek(R) Audio)"},
                          {"id": "pods", "name": "Headphones (Danish's AirPods Pro)"},
                          {"id": "hdmi", "name": "SAMSUNG (NVIDIA High Definition Audio)"},
                          {"id": "hs", "name": "Headset (Danish's AirPods Pro Hands-Free)"}]
            self._out_cur = "spk"
        return sorted([{**o, "on": o["id"] == self._out_cur} for o in self._outs], key=lambda o: (not o["on"], o["name"].lower()))

    async def output_set(self, did):
        await self.outputs()
        self._out_cur = did
        log.info("[demo] output -> %s", did)

    async def start_apps(self):
        return [{"name": n, "id": i} for n, i in (
            ("Apple Music", "AppleInc.AppleMusicWin_nzyj5cx40ttqa!App"), ("Discord", "com.squirrel.Discord.Discord"),
            ("EA app", "EA.Desktop"), ("Forza Horizon 6", "Microsoft.ForzaHorizon6_8wekyb3d8bbwe!App"),
            ("G-Helper", "C:\\Tools\\GHelper.exe"), ("Google Chrome", "Chrome"), ("NVIDIA app", "NVIDIA.App"),
            ("Notepad", "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App"), ("OBS Studio", "OBS Studio"),
            ("Spotify", "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"), ("Steam", "Steam"),
            ("Visual Studio Code", "Microsoft.VisualStudioCode"), ("WhatsApp", "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"))]

    async def open_url(self, url):
        log.info("[demo] open %s", url)

    async def reveal(self, path):
        log.info("[demo] reveal %s", path)

    def demo_caps(self) -> Path:
        d = Path(os.environ.get("TEMP") or "/tmp") / "deskdeck-demo-caps"
        if getattr(self, "_caps_ok", False):
            return d
        self._caps_ok = True
        try:
            from PIL import Image, ImageDraw
            d.mkdir(exist_ok=True)
            now = time.time()
            shots = [("Forza Horizon 6 2026-11-19 22-14-03.png", (255, 120, 60), (40, 20, 90)),
                     ("Forza Horizon 6 2026-11-19 21-58-41.png", (60, 190, 255), (10, 30, 60)),
                     ("Need for Speed Unbound 2026-11-18 23-02-11.png", (255, 60, 120), (20, 10, 30)),
                     ("Screenshot 2026-11-17 101530.png", (120, 120, 140), (30, 30, 40))]
            for k, (n, c1, c2) in enumerate(shots):
                p = d / n
                if not p.exists():
                    im = Image.new("RGB", (640, 360))
                    dr = ImageDraw.Draw(im)
                    for y in range(360):
                        t = y / 359
                        dr.line([(0, y), (640, y)], fill=tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3)))
                    dr.ellipse([420, 60, 560, 200], fill=(255, 230, 180))
                    dr.polygon([(0, 360), (260, 220), (640, 300), (640, 360)], fill=tuple(v // 3 for v in c2))
                    im.save(p)
                os.utime(p, (now - 3600 * (k * 7 + 2), now - 3600 * (k * 7 + 2)))
            if shutil.which("ffmpeg"):
                for k, n in enumerate(["Forza Horizon 6 2026-11-20 01-50-12.mp4", "Need for Speed Unbound 2026-11-19 23-40-55.mp4"]):
                    p = d / n
                    if not p.exists():
                        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=30:duration=3",
                                        "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", str(p)], timeout=60)
                    if p.exists():
                        os.utime(p, (now - 600 * (k * 9 + 1), now - 600 * (k * 9 + 1)))
        except Exception as e:
            log.info("[demo] captures: %s", e)
        return d

    async def video_thumb(self, path):
        if not shutil.which("ffmpeg"):
            return None
        r = await asyncio.create_subprocess_exec("ffmpeg", "-v", "error", "-ss", "1", "-i", path, "-frames:v", "1", "-vf", "scale=480:-1",
                                                 "-f", "image2", "-c:v", "mjpeg", "-", stdout=subprocess.PIPE)
        out, _ = await r.communicate()
        return out or None

    async def text(self, s):
        log.info("[demo] type %r", s[:40])

    async def sys_action(self, name):
        log.info("[demo] system %s", name)

    async def clip_get(self):
        return self.clip

    async def clip_set(self, text):
        self.clip = text
        log.info("[demo] clipboard <- %r", text[:40])

    async def laptop_extra(self):
        t = time.time()
        g = bool(getattr(self.eng, "demo_game", False))
        return {"bat": 78, "plugged": True, "left": None, "lhm": True,
                "cpuT": round((76 if g else 58) + 6 * math.sin(t / 9)), "gpuT": round((70 if g else 49) + 4 * math.sin(t / 13)),
                "cpuW": round((52 if g else 14) + 6 * math.sin(t / 7), 1), "gpuW": round((86 if g else 9) + 5 * math.sin(t / 6), 1),
                "fans": [(4700 if g else 3100) + int(300 * math.sin(t / 5)), 2900]}

    def demo_lyrics(self, key):
        tr = next((x for x in DEMO_TRACKS if x["title"] == key[1]), None)
        if not tr:
            return None
        lines, t = [], 9.0
        for ln in tr["lines"]:
            lines.append([round(t, 2), ln])
            t += 9.0 if ln == "" else 4.6
        if tr is not DEMO_TRACKS[0]:
            return {"synced": True, "lines": lines, "src": "LRCLIB"}
        # the first demo song has word timing, like NetEase gives us
        out_l, out_w = [], []
        for t0, ln in lines:
            if not ln:
                continue
            ws, tt = [], t0
            for k, w in enumerate(ln.split(" ")):
                d = 0.22 + len(w) * 0.07 + (0.6 if k == len(ln.split(" ")) - 1 else 0)
                ws.append([round(tt, 3), round(tt + d, 3), w + ("" if k == len(ln.split(" ")) - 1 else " ")])
                tt += d + 0.04
            out_l.append([t0, ln]); out_w.append(ws)
        return {"synced": True, "lines": out_l, "words": out_w, "src": "NetEase"}


# --------------------------------------------------------------------------------------
# LibreHardwareMonitor parsing (temps / fans)
# --------------------------------------------------------------------------------------

def _num(v):
    if not isinstance(v, str):
        return None
    m = re.search(r"-?\d+(?:[.,]\d+)?", v)
    return float(m.group(0).replace(",", ".")) if m else None


def parse_lhm(tree: dict) -> dict:
    cpu, gpu, fans, cpuw, gpuw = [], [], [], [], []

    def walk(node, hw):
        text = str(node.get("Text", ""))
        sid = str(node.get("SensorId", "") or "")
        img = str(node.get("ImageURL", "") or "").lower()
        kids = node.get("Children") or []
        h = hw
        if kids:
            t = text.lower()
            if "cpu.png" in img or any(k in t for k in ("ryzen", "intel core", "core ultra", "athlon")):
                h = "cpu"
            elif "nvidia" in img or any(k in t for k in ("nvidia", "geforce", "rtx ")):
                h = "dgpu"
            elif "ati.png" in img or "radeon" in t:
                h = "igpu"
        else:
            val = node.get("Value")
            typ = str(node.get("Type", "") or "").lower()
            n = _num(val)
            if n is not None and isinstance(val, str):
                if "°c" in val.lower() or typ == "temperature" or "/temperature/" in sid:
                    if h == "cpu" or sid.startswith(("/amdcpu", "/intelcpu")):
                        cpu.append((text.lower(), n))
                    elif h == "dgpu" or sid.startswith("/gpu-nvidia"):
                        gpu.append((text.lower(), n))
                elif ("rpm" in val.lower() or typ == "fan" or "/fan/" in sid) and n > 0:
                    fans.append((text, n))
                elif val.strip().lower().endswith(" w") or typ == "power" or "/power/" in sid:
                    if h == "cpu" or sid.startswith(("/amdcpu", "/intelcpu")):
                        cpuw.append((text.lower(), n))
                    elif h == "dgpu" or sid.startswith("/gpu-nvidia"):
                        gpuw.append((text.lower(), n))
        for k in kids:
            walk(k, h)

    walk(tree, None)

    def pick(lst, prefs):
        for p in prefs:
            for t, v in lst:
                if p in t and v > 0:
                    return v
        vals = [v for _, v in lst if v > 0]
        return max(vals) if vals else None

    c = pick(cpu, ("tctl", "tdie", "package"))
    g = pick(gpu, ("gpu core",))
    cw = pick(cpuw, ("package", "cpu package", "core"))
    gw = pick(gpuw, ("gpu package", "gpu power", "board"))
    return {"cpuT": round(c) if c else None, "gpuT": round(g) if g else None,
            "cpuW": round(cw, 1) if cw else None, "gpuW": round(gw, 1) if gw else None,
            "fans": [round(v) for _, v in fans[:3]]}


# --------------------------------------------------------------------------------------
# Forza Horizon telemetry ("Data Out") - relay + parser
# --------------------------------------------------------------------------------------
# FH6 packet (FH5 uses the same layout): 323 bytes documented, little-endian.
FH_MIN_LEN = 323


def parse_fh(b: bytes) -> dict:
    u = struct.unpack_from
    f4 = lambda o: list(u("<4f", b, o))
    acc_x, acc_y, acc_z = u("<3f", b, 20)
    tt = [round((t - 32) * 5 / 9) for t in f4(268)]  # Forza reports tyre temps in °F
    lap, pos, thr, brk, clu, hb, gear = u("<HBBBBBB", b, 312)
    steer = u("<b", b, 320)[0]
    return {
        "on": u("<i", b, 0)[0] == 1,
        "max": round(u("<f", b, 8)[0]), "idle": round(u("<f", b, 12)[0]), "rpm": round(u("<f", b, 16)[0]),
        "gx": round(acc_x / 9.81, 3), "gz": round(acc_z / 9.81, 3),
        "susp": [round(x, 3) for x in f4(68)],
        "slip": [round(abs(x), 2) for x in f4(180)],
        "ord": u("<i", b, 212)[0], "cls": u("<i", b, 216)[0], "pi": u("<i", b, 220)[0],
        "dt": u("<i", b, 224)[0], "cyl": u("<i", b, 228)[0],
        "kmh": round(u("<f", b, 256)[0] * 3.6, 1),
        "hp": round(max(0.0, u("<f", b, 260)[0]) * 0.00134102),
        "nm": round(max(0.0, u("<f", b, 264)[0])),
        "tt": tt, "boost": round(u("<f", b, 284)[0], 1), "fuel": round(u("<f", b, 288)[0], 3),
        "dist": round(u("<f", b, 292)[0] / 1000, 2),
        "best": round(u("<f", b, 296)[0], 2), "last": round(u("<f", b, 300)[0], 2),
        "cur": round(u("<f", b, 304)[0], 2), "race": round(u("<f", b, 308)[0], 1),
        "lap": lap, "pos": pos, "thr": thr, "brk": brk, "clu": clu, "hb": hb, "gear": gear,
        "steer": round(steer / 127, 3),
    }


class ForzaRelay(threading.Thread):
    """Listens for Forza Data Out, forwards every packet untouched (so haptics/SimHub keep
    working), and keeps the latest parsed frame for the phone."""

    def __init__(self, port: int, forwards):
        super().__init__(daemon=True, name="forza")
        self.port = int(port)
        self.forwards = []
        for f in forwards or []:
            try:
                h, p = str(f).rsplit(":", 1)
                p = int(p)
            except ValueError:
                log.warning("Forza: forward '%s' ignored (use host:port)", f)
                continue
            if p == self.port and h in ("127.0.0.1", "localhost", "0.0.0.0"):
                continue  # would loop back into ourselves
            self.forwards.append((h, p))
        self.latest = None
        self.stamp = 0.0

    def run(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.bind(("0.0.0.0", self.port))
        except OSError as e:
            log.warning("Forza: can't listen on UDP %s (%s) - is another app using it?", self.port, e)
            return
        out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        fw = ", ".join(f"{h}:{p}" for h, p in self.forwards)
        log.info("Forza: listening on UDP %s%s", self.port, f" (forwarding to {fw})" if fw else "")
        while True:
            try:
                data, _ = s.recvfrom(4096)
            except OSError:
                time.sleep(0.02)
                continue
            for dst in self.forwards:
                try:
                    out.sendto(data, dst)
                except OSError:
                    pass
            if len(data) >= FH_MIN_LEN:
                try:
                    self.latest = parse_fh(data)
                    self.stamp = time.monotonic()
                except Exception:
                    pass


def fake_forza(t: float) -> dict:
    """Demo telemetry: a car pulling through the gears, braking every 24 s."""
    cyc = t % 24.0
    if cyc < 19:
        spd = 40 + cyc * 13.5
    else:
        spd = 40 + 19 * 13.5 - (cyc - 19) * 58
    spd = max(30.0, spd)
    ratios = [0, 52, 84, 118, 154, 192, 236, 300]
    gear = next((g for g in range(1, 8) if spd <= ratios[g]), 7)
    lo = ratios[gear - 1] if gear > 1 else 0
    frac = (spd - lo) / max(1, ratios[gear] - lo)
    rpm = 3200 + frac * 4700
    braking = cyc >= 19
    thr = 0 if braking else 255
    brk = int(200 + 40 * math.sin(t * 9)) if braking else 0
    steer = math.sin(t * 0.6) * 0.35
    return {"on": True, "max": 8000, "idle": 900, "rpm": round(rpm), "gx": round(steer * 1.1, 3),
            "gz": round(-1.1 if braking else 0.55 * (1 - frac * 0.5), 3),
            "susp": [0.5] * 4, "slip": [0.2, 0.2, 1.3 if braking else 0.4, 1.3 if braking else 0.5],
            "ord": 2471, "cls": 4, "pi": 845, "dt": 2, "cyl": 6, "kmh": round(spd, 1),
            "hp": round(0 if braking else 390 + 180 * frac), "nm": round(0 if braking else 520 + 90 * frac),
            "tt": [84, 86, 92, 95], "boost": round(0 if braking else 6 + 12 * frac, 1), "fuel": 0.72,
            "dist": round(t * 0.04, 2), "best": 0, "last": 0, "cur": 0, "race": 0,
            "lap": 0, "pos": 0, "thr": thr, "brk": brk, "clu": 0, "hb": 0, "gear": gear,
            "steer": round(steer, 3)}


# --------------------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------------------

RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
F1_SESSIONS = [("FirstPractice", "Practice 1"), ("SecondPractice", "Practice 2"),
               ("ThirdPractice", "Practice 3"), ("SprintQualifying", "Sprint Qualifying"),
               ("SprintShootout", "Sprint Shootout"), ("Sprint", "Sprint"), ("Qualifying", "Qualifying")]
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


# ============================================================================
# Health page helpers: heavy apps, protected processes, nice names
# ============================================================================
PROTECTED_PROCS = {"system", "registry", "idle", "memory compression", "secure system", "smss.exe", "csrss.exe",
                   "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe", "svchost.exe", "dwm.exe",
                   "fontdrvhost.exe", "explorer.exe", "sihost.exe", "ctfmon.exe", "msmpeng.exe", "searchhost.exe",
                   "startmenuexperiencehost.exe", "shellexperiencehost.exe", "runtimebroker.exe", "taskhostw.exe",
                   "python.exe", "pythonw.exe", "py.exe", "adb.exe", "librehardwaremonitor.exe", "ghelper.exe",
                   "audiodg.exe", "conhost.exe", "dllhost.exe", "spoolsv.exe", "wudfhost.exe", "lsaiso.exe",
                   "textinputhost.exe", "securityhealthservice.exe", "nvcontainer.exe", "atiesrxx.exe", "atieclxx.exe"}
APP_NAMES = {"chrome": "Google Chrome", "msedge": "Microsoft Edge", "firefox": "Firefox", "brave": "Brave",
             "ms-teams": "Microsoft Teams", "teams": "Microsoft Teams", "discord": "Discord", "steam": "Steam",
             "steamwebhelper": "Steam", "code": "VS Code", "spotify": "Spotify", "applemusic": "Apple Music",
             "amplibraryagent": "Apple Music", "whatsapp": "WhatsApp", "obs64": "OBS Studio", "zoom": "Zoom",
             "slack": "Slack", "notion": "Notion", "figma": "Figma", "photoshop": "Photoshop", "vlc": "VLC",
             "epicgameslauncher": "Epic Games", "riotclientservices": "Riot Client", "telegram": "Telegram",
             "winword": "Word", "excel": "Excel", "powerpnt": "PowerPoint", "outlook": "Outlook", "olk": "Outlook",
             "msedgewebview2": "Edge WebView", "acrobat": "Acrobat", "idea64": "IntelliJ IDEA", "pycharm64": "PyCharm",
             "forzahorizon6": "Forza Horizon 6", "forzahorizon5": "Forza Horizon 5", "taskmgr": "Task Manager"}


def fps_low(h):
    """A 'lowest' that ignores loading screens and alt-tab hitches: 5th percentile of the
    samples that are at least a quarter of the median."""
    if len(h) < 6:
        return round(min(h)) if h else None
    srt = sorted(h)
    med = srt[len(srt) // 2]
    keep = [v for v in srt if v >= max(5.0, med * 0.25)] or srt
    return round(keep[min(len(keep) - 1, int(len(keep) * 0.05))])


def app_nice(exe_name: str) -> str:
    stem = re.sub(r"\.exe$", "", exe_name or "", flags=re.I)
    return APP_NAMES.get(stem.lower()) or (stem[:1].upper() + stem[1:] if stem else "?")


# ============================================================================
# FH6 car names (ordinal -> "2016 Mercedes-Benz C63 AMG Coupe")
# ============================================================================
CAR_MAKES = ("AMG Transport Dynamics", "Aston Martin", "Alfa Romeo", "Land Rover", "Formula Drift", "RJ Anderson",
             "Sierra Cars", "De Tomaso", "Lynk & Co", "Hot Wheels", "Local Motors", "Austin Healey")
CAR_CACHE = ROOT / "fh6_cars.cache.json"


def split_car(full: str):
    m = re.match(r"^(\d{4})\s+(.+)$", full or "")
    if not m:
        return None
    year, rest = m.groups()
    make = next((mk for mk in CAR_MAKES if rest.startswith(mk + " ")), rest.split(" ", 1)[0])
    model = rest[len(make):].strip() or rest
    return {"year": year, "make": make, "model": model, "full": full}


class CarDB:
    def __init__(self):
        self.by_ord = {}
        best = {}
        for path in (ROOT / "data" / "fh6_cars.json", CAR_CACHE):
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(d, dict) and len(d) >= len(best):
                    best = d
            except Exception:
                pass
        self._load(best)

    def _load(self, d: dict):
        out = {}
        for name, ordv in d.items():
            info = split_car(str(name))
            try:
                if info:
                    out[str(int(ordv))] = info
            except (TypeError, ValueError):
                pass
        if out:
            self.by_ord = out

    def get(self, ordinal):
        return self.by_ord.get(str(ordinal))

    async def refresh(self, http, url: str):
        """Weekly refresh from the community list; keeps the bundled copy if anything looks off."""
        try:
            if CAR_CACHE.exists() and time.time() - CAR_CACHE.stat().st_mtime < 7 * 86400:
                return
            async with http.get(url, timeout=ClientTimeout(total=15)) as r:
                if r.status != 200:
                    return
                d = json.loads(await r.text())
            if isinstance(d, dict) and len(d) >= max(100, len(self.by_ord) // 2):
                CAR_CACHE.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
                self._load(d)
                log.info("car list updated: %d cars", len(self.by_ord))
        except Exception as e:
            log.debug("car list refresh failed: %s", e)


class Engine:
    def __init__(self, cfg: dict, demo: bool, demo_forza: bool = False, demo_game: bool = False):
        self.cfg, self.demo, self.demo_forza = cfg, demo, demo_forza
        self.demo_game = demo_game
        self._game = None          # {"pid", "exe", "name"} of the game being played
        self._ctx_last = None
        self._caps: dict = {}      # capture id -> (path, kind)
        self._thumbs: dict = {}
        self.discord = DemoDiscord(self) if demo else (DiscordRPC(self) if IS_WIN else None)
        self.f1live = None
        self._meet_since = None
        self._call_title = None
        self._rules_at = 0.0
        self._rules_active = []
        self._fps_hist = []
        self._quota_next = 0.0
        self._quota_last = None
        self._procs_on = 0.0
        self.focus = self._load_focus()
        if not cfg.get("hook_key"):
            cfg["hook_key"] = secrets.token_urlsafe(12)
            self._persist_cfg_key("hook_key", cfg["hook_key"])
        self.hooks = self._load_hooks()
        self.ssl_ctx = None
        self._cert_ip = None
        self._hooks_dirty = False
        self.forza = None
        self.cars = self._load_cars()
        self.cardb = CarDB()
        self.hub = Hub()
        self.pool = ThreadPoolExecutor(4, thread_name_prefix="io")
        self.http: ClientSession | None = None
        self.plat = DemoPlatform(self) if demo else WinPlatform(self)
        self.tasks: list = []
        self.art: dict = {}
        self.media_key = None
        self.media_sent = None
        self.media_sent_at = 0.0
        self.art_hash = None
        self.prev_art_hash = None
        self.art_tries = 0
        self.art_try_at = 0.0
        self.lyrics_cache: dict = {}
        self.photos: list = []
        self.lhm_next = 0.0
        self.lhm_last = {"lhm": False, "cpuT": None, "gpuT": None, "fans": []}
        self.adb_ok = None
        self._vol_last = None
        self._air_last = None
        self._appv_last = None
        self._radio_last = None
        self._radio_sent_at = 0.0
        self._radio_st_at = 0.0
        self._radio_st_src = ""
        self._radio_stations: list = []
        self._radio_art_src = None
        self._radio_art = None
        self._radio_qkey = None
        self._radio_fail = 0
        self._radio_flip = False
        self.rart: dict = {}
        self.thumbs: dict = {}

    # ---------------- lifecycle
    async def start(self, app):
        self.http = ClientSession(headers={"User-Agent": UA}, timeout=ClientTimeout(total=12))
        loops = [
            (self.tick_sys, 1.0), (self.tick_laptop, 3.0), (self.tick_media, 0.5),
            (self.tick_volume, 0.5), (self.tick_privacy, 1.5), (self.tick_ping, 3.0),
            (self.tick_weather, 600), (self.tick_f1, 1200), (self.tick_photos, 60),
            (self.tick_radio, 1.0), (self.tick_ctx, 1.5), (self.tick_game, 0.5),
            (self.tick_procs, 3.0), (self.tick_wifi, 30), (self.tick_quota, 30), (self.tick_focus, 1.0),
            (self.tick_notes, 2.0), (self.tick_hooks, 15), (self.tick_cert, 300), (self.tick_play, 5.0),
        ]
        if self.discord:
            self.tasks.append(asyncio.create_task(self.discord.run()))
        if not self.demo or self.cfg.get("_demo_f1"):
            self.f1live = DemoF1Live(self) if self.demo else F1Live(self)
            self.tasks.append(asyncio.create_task(self.f1live.run()))
        if self.cfg.get("adb_reverse") and shutil.which("adb"):
            loops.append((self.tick_adb, 10))
        for fn, every in loops:
            self.tasks.append(asyncio.create_task(self._forever(fn, every)))
        self.tasks.append(asyncio.create_task(self.loop_spectrum()))
        fz = self.cfg.get("forza") or {}
        if fz.get("listen") and not self.demo_forza:
            self.forza = ForzaRelay(fz["listen"], fz.get("forward") or [])
            self.forza.start()
        self.tasks.append(asyncio.create_task(self.loop_forza()))
        if not self.demo:
            self.tasks.append(asyncio.create_task(self._forever(self.tick_cars, 6 * 3600)))

    async def stop(self, app):
        for t in self.tasks:
            t.cancel()
        if self.http:
            await self.http.close()

    async def _forever(self, fn, every):
        fails = 0
        while True:
            try:
                await fn()
                fails = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                fails += 1
                if fails in (1, 10) or fails % 100 == 0:
                    log.warning("%s: %s", fn.__name__, e)
            if fails == 0:
                delay = every
            elif every >= 60:
                delay = 60  # network fetches: retry in a minute
            else:
                delay = every if fails < 3 else max(every, 10)
            await asyncio.sleep(delay)

    async def _io(self, fn, *a):
        return await asyncio.get_running_loop().run_in_executor(self.pool, fn, *a)

    # ---------------- system
    async def tick_sys(self):
        if not hasattr(self, "_net"):
            psutil.cpu_percent(None)
            self._net = (time.monotonic(), psutil.net_io_counters())
            self._gpu_fail = 0
        cpu = psutil.cpu_percent(None)
        vm = psutil.virtual_memory()
        t0, n0 = self._net
        t1, n1 = time.monotonic(), psutil.net_io_counters()
        span = max(1e-3, t1 - t0)
        self._net = (t1, n1)
        gpu = vram = None
        if self._gpu_fail < 5:
            try:
                gpu, vram = await self._io(self.plat.gpu_read)
                self._gpu_fail = 0
            except Exception as e:
                self._gpu_fail += 1
                if self._gpu_fail == 5:
                    log.warning("GPU usage disabled: %s", e)
        await self.hub.send("sys", {
            "cpu": round(cpu, 1), "ram": round(vm.percent, 1),
            "ramUsed": round(vm.used / 2**30, 1), "ramTot": round(vm.total / 2**30, 1),
            "gpu": None if gpu is None else round(gpu, 1),
            "vram": None if not vram else round(vram / 2**30, 1),
            "up": int((n1.bytes_sent - n0.bytes_sent) / span),
            "down": int((n1.bytes_recv - n0.bytes_recv) / span),
        })

    async def tick_laptop(self):
        d = {"bat": None, "plugged": None, "left": None}
        try:
            b = psutil.sensors_battery()
        except Exception:
            b = None
        if b is not None:
            d["bat"] = round(b.percent)
            d["plugged"] = bool(b.power_plugged)
            if isinstance(b.secsleft, int) and b.secsleft > 0 and not b.power_plugged:
                d["left"] = b.secsleft
        d.update(await self.lhm())
        d.update(await self.plat.laptop_extra())
        d["mode"] = await self.plat.mode_get()
        d["modeName"] = getattr(self.plat, "mode_name", None)
        await self.hub.send("laptop", d)
        try:
            running = await self.plat.forza_running()
        except Exception:
            running = False
        if running != (self.hub.state.get("fzapp") or {}).get("running"):
            await self.hub.send("fzapp", {"running": running})

    async def lhm(self):
        if self.demo or time.time() < self.lhm_next:
            return self.lhm_last
        try:
            async with self.http.get(self.cfg["lhm_url"], timeout=ClientTimeout(total=1.5)) as r:
                tree = await r.json(content_type=None)
            res = parse_lhm(tree)
            res["lhm"] = True
        except Exception:
            res = {"lhm": False, "cpuT": None, "gpuT": None, "fans": []}
            self.lhm_next = time.time() + 20
        self.lhm_last = res
        return res

    # ---------------- media
    async def tick_media(self):
        m = await self.plat.media_poll()
        if not m or not (m["title"] or m["artist"]):
            if self.media_key is not None or self.media_sent is None:
                self.media_key = None
                self.media_sent = {"active": False}
                await self.hub.send("media", {"active": False})
            return
        title, artist, album = m["title"], m["artist"], m["album"]
        if not album and " — " in artist:  # Apple Music packs "Artist — Album"
            artist, album = artist.split(" — ", 1)
        album = re.sub(r"^[\s\-–—·:]+", "", album or "")  # "-Ugh, those feels again" -> "Ugh, those feels again"
        if app_label(m["app"]) in ("Chrome", "Edge", "Firefox", "Brave", "Opera"):  # YouTube in a browser
            title, artist = clean_track(title, artist)
        key = (m["app"], title, artist)
        if key != self.media_key:
            self.media_key = key
            self.prev_art_hash = self.art_hash
            self.art_hash, self.art_tries, self.art_try_at = None, 0, 0.0
            asyncio.create_task(self.load_lyrics(key, title, artist, album, m["dur"]))
        need_art = self.art_hash is None or (self.art_hash == self.prev_art_hash and self.art_tries < 6)
        if need_art and self.art_tries < 8 and time.monotonic() - self.art_try_at > 0.9:
            self.art_tries += 1
            self.art_try_at = time.monotonic()
            try:
                data = await self.plat.media_art()
            except Exception:
                data = None
            if data:
                h = hashlib.sha1(data).hexdigest()[:12]
                self.art[h] = (data, sniff_type(data))
                while len(self.art) > 12:
                    self.art.pop(next(iter(self.art)))
                self.art_hash = h
        payload = {
            "active": True, "app": app_label(m["app"]), "title": title, "artist": artist,
            "album": album, "playing": m["playing"], "dur": round(m["dur"], 2),
            "art": f"/art/{self.art_hash}" if self.art_hash else None,
        }
        try:
            av = await self.plat.appv_state()
        except Exception:
            av = None
        if av is not None:
            payload["avol"] = av
        changed = payload != self.media_sent
        if changed or time.monotonic() - self.media_sent_at > 2.0:
            self.media_sent, self.media_sent_at = payload, time.monotonic()
            await self.hub.send("media", {**payload, "pos": round(m["pos"], 2)})

    async def load_lyrics(self, key, title, artist, album, dur):
        kid = "|".join(key)
        await self.hub.send("lyrics", {"key": kid, "loading": True})
        res = self.lyrics_cache.get(kid)
        if res is None:
            res = self.plat.demo_lyrics(key) if self.demo else None
            if res is None and not self.demo:
                res = await self.fetch_lyrics(title, artist, album, dur)
            res = res or {"none": True}
            self.lyrics_cache[kid] = res
            while len(self.lyrics_cache) > 60:
                self.lyrics_cache.pop(next(iter(self.lyrics_cache)))
        if self.media_key == key:
            await self.hub.send("lyrics", {"key": kid, **res})

    async def fetch_lyrics(self, title, artist, album, dur):
        async def safe(coro, what):
            try:
                return await asyncio.wait_for(coro, 9)
            except Exception as e:
                log.info("lyrics (%s): %s", what, e)
                return None

        jobs = [safe(self.fetch_lrclib(title, artist, album, dur), "lrclib")]
        if self.cfg.get("word_lyrics", True):
            jobs.append(safe(self.fetch_netease(title, artist, dur), "netease"))
        got = await asyncio.gather(*jobs)
        lrc = got[0]
        ne = got[1] if len(got) > 1 else None
        if ne and not (lrc and lrc.get("words")):
            log.info("lyrics: %s - %s (NetEase, word timing)", artist, title)
            return ne
        if lrc:
            log.info("lyrics: %s - %s (LRCLIB%s)", artist, title, ", word timing" if lrc.get("words") else "")
        return lrc

    async def fetch_netease(self, title, artist, dur):
        t, a = clean_title(title), clean_artist(artist)
        hdr = {"Referer": "https://music.163.com/", "Cookie": "os=pc; appver=2.10.13",
               "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
        async with self.http.post("https://music.163.com/api/search/get/web", headers=hdr,
                                  data={"s": f"{t} {a}", "type": "1", "limit": "10", "offset": "0"}) as r:
            js = await r.json(content_type=None)
        songs = ((js or {}).get("result") or {}).get("songs") or []
        nt, na = _norm_song(t), _norm_song(a)
        best = None
        for s in songs:
            name = _norm_song(s.get("name", ""))
            arts = [_norm_song(x.get("name", "")) for x in (s.get("artists") or s.get("ar") or [])]
            ms = s.get("duration") or s.get("dt") or 0
            if not name or not (name == nt or (len(nt) > 5 and (name.startswith(nt) or nt.startswith(name)))):
                continue
            if na and not any(x and (x in na or na in x) for x in arts):
                continue
            if dur and ms and abs(ms / 1000 - dur) > 3.5:
                continue
            best = s
            break
        if not best:
            return None
        sid = best["id"]
        tries = (
            ("POST", "https://music.163.com/api/song/lyric/v1",
             {"id": str(sid), "cp": "false", "tv": "0", "lv": "0", "rv": "0", "kv": "0", "yv": "0", "ytv": "0", "yrv": "0"}),
            ("GET", f"https://music.163.com/api/song/lyric?os=pc&id={sid}&lv=-1&kv=-1&tv=-1&rv=-1&yv=-1", None),
        )
        for method, url, data in tries:
            try:
                async with self.http.request(method, url, headers=hdr, data=data) as r:
                    lj = await r.json(content_type=None)
            except Exception as e:
                log.debug("netease lyric %s: %s", url, e)
                continue
            yrc = ((lj or {}).get("yrc") or {}).get("lyric")
            parsed = parse_yrc(yrc) if yrc else None
            if parsed:
                lines, words = parsed
                return {"synced": True, "lines": lines, "words": words, "src": "NetEase"}
        return None

    async def fetch_lrclib(self, title, artist, album, dur):
        t, a = clean_title(title), clean_artist(artist)
        base = "https://lrclib.net/api"

        def pack(d):
            if not d:
                return None
            if d.get("instrumental"):
                return {"instrumental": True}
            if d.get("syncedLyrics"):
                pw = parse_lrc_words(d["syncedLyrics"])
                if pw:
                    return {"synced": True, "lines": pw[0], "words": pw[1], "src": "LRCLIB"}
                return {"synced": True, "lines": parse_lrc(d["syncedLyrics"]), "src": "LRCLIB"}
            if d.get("plainLyrics"):
                return {"synced": False, "plain": d["plainLyrics"].splitlines()}
            return None

        params = {"track_name": t, "artist_name": a}
        if album:
            params["album_name"] = album
        if dur and dur > 0:
            params["duration"] = int(round(dur))
        async with self.http.get(f"{base}/get", params=params) as r:
            if r.status == 200:
                got = pack(await r.json(content_type=None))
                if got and got.get("synced"):
                    return got
        for q in ({"track_name": t, "artist_name": a}, {"q": f"{a} {t}"}):
            async with self.http.get(f"{base}/search", params=q) as r:
                if r.status != 200:
                    continue
                items = await r.json(content_type=None) or []
            if not items:
                continue

            def score(it):
                s = 0
                if it.get("syncedLyrics"):
                    s += 10
                if dur and it.get("duration") and abs(float(it["duration"]) - dur) <= 3:
                    s += 5
                return s

            best = max(items[:12], key=score)
            got = pack(best)
            if got:
                return got
        return None

    async def loop_spectrum(self):
        out = [0.0] * 24
        agc = 0.6
        zero_sent = True
        while True:
            await asyncio.sleep(1 / 30)
            try:
                raw, stamp = self.plat.spectrum()
            except Exception:
                raw, stamp = None, 0.0
            fresh = raw is not None and time.monotonic() - stamp < 0.25
            if fresh:
                peak = max(raw)
                agc = max(peak, agc - 0.0015)
                off = max(-0.1, min(0.3, 0.92 - agc))
                target = [min(1.0, max(0.0, v + off)) for v in raw]
            else:
                target = [0.0] * 24
            for i in range(24):
                d = target[i] - out[i]
                out[i] += d * (0.6 if d > 0 else 0.16)
            if not self.hub.clients:
                continue
            silent = max(out) < 0.01
            if silent and zero_sent:
                continue
            zero_sent = silent
            await self.hub.send("spec", {"b": [int(v * 100) for v in out]}, keep=False)

    # ---------------- rules engine: what's going on right now (game / call / custom app rules)
    GAME_DIRS = ("\\steamapps\\common\\", "\\xboxgames\\", "\\epic games\\", "\\riot games\\", "\\ea games\\",
                 "\\ubisoft game launcher\\games\\", "\\gog galaxy\\games\\", "\\battle.net\\", "\\rockstar games\\",
                 "\\games\\")
    NOT_GAMES = ("explorer", "chrome", "msedge", "firefox", "brave", "opera", "vlc", "applemusic", "spotify", "code",
                 "powerpnt", "winword", "excel", "obs64", "discord", "steamwebhelper", "steam", "epicgameslauncher",
                 "riotclientservices", "riotclientux", "battle.net", "eadesktop", "mpc-hc64", "potplayermini64",
                 "teams", "ms-teams", "zoom", "applicationframehost", "systemsettings", "textinputhost", "deskdeck")
    CALL_APPS = {"teams": "Microsoft Teams", "msteams": "Microsoft Teams", "ms-teams": "Microsoft Teams",
                 "zoom": "Zoom", "discord": "Discord", "slack": "Slack", "webex": "Webex", "ciscocollabhost": "Webex",
                 "skype": "Skype", "whatsapp": "WhatsApp", "chrome": "Google Meet", "msedge": "Browser call",
                 "firefox": "Browser call"}

    def _is_game(self, fg) -> bool:
        stem = re.sub(r"\.exe$", "", (fg.get("name") or "").lower())
        if not stem or any(stem == n or stem.startswith(n) for n in self.NOT_GAMES):
            return False
        games = [g.lower() for g in self.cfg.get("games", [])]
        if stem in games or fg.get("name", "").lower() in games:
            return True
        exe = (fg.get("exe") or "").lower()
        if any(d in exe for d in self.GAME_DIRS):
            return True
        gpu = (self.hub.state.get("sys") or {}).get("gpu") or 0
        return bool(fg.get("full")) and gpu >= 45

    async def tick_ctx(self):
        # --- game: latch onto the fullscreen/foreground game until its process exits
        fg = None
        try:
            fg = await self.plat.foreground()
        except Exception as e:
            log.debug("foreground: %s", e)
        if self._game and not self.demo and not psutil.pid_exists(self._game["pid"]):
            self._game = None
        if self.demo and not self.demo_game:
            self._game = None
        if fg and self._is_game(fg) and (not self._game or self._game["pid"] != fg["pid"]):
            title = fg.get("title") or ""
            nice = title if 0 < len(title) <= 40 else re.sub(r"(?i)(-win64-shipping|-win64|_dx1[12]|_x64|\.exe)$", "",
                                                                  os.path.splitext(fg.get("name") or "Game")[0])
            self._game = {"pid": fg["pid"], "exe": fg.get("exe") or "", "name": nice.strip() or "Game"}
            self._fps_hist = []
        game = self._game
        fz_live = bool(self.forza and self.forza.latest is not None and time.monotonic() - self.forza.stamp < 3) \
            or bool(self.demo_forza)
        if game and fz_live and "forzahorizon" in (game.get("exe") or "").lower():
            game = None  # Forza has its own Drive page
        # --- call: a call app is using the mic
        air = self.hub.state.get("air") or {}
        call = None
        for app in air.get("mic") or []:
            key = re.sub(r"[^a-z-]", "", app.lower())
            label = next((v for k, v in self.CALL_APPS.items() if key.startswith(k)), None)
            if label:
                call = {"app": label, "key": key, "cam": bool(air.get("cam"))}
                break
        dch = self.discord.ch if self.discord and self.discord.status == "ready" else None
        if dch and (call is None or call["key"].startswith("discord")) and not (self.demo and call is None):
            call = {"app": "Discord", "key": "discord", "cam": bool(call and call.get("cam")), "voice": True}
        if call and not self._meet_since:
            self._meet_since = time.time()
        if not call:
            self._meet_since = None
        if call:
            call["since"] = int(self._meet_since)
            if not self._call_title or self._call_title[0] != call["key"] or time.monotonic() - self._call_title[2] > 20:
                t = None
                try:
                    t = await self.plat.call_title(call["key"])
                except Exception:
                    pass
                self._call_title = (call["key"], t, time.monotonic())
            call["title"] = self._call_title[1]
        # --- custom rules from config: [{"app": "obs64.exe", "page": "cc"}]
        rules = self.cfg.get("rules") or []
        if rules and time.monotonic() - self._rules_at > 3:
            self._rules_at = time.monotonic()
            try:
                names = {(p.info.get("name") or "").lower() for p in psutil.process_iter(["name"])}
            except Exception:
                names = set()
            act = []
            for r in rules:
                app = str(r.get("app", "")).lower()
                if app and (app in names or app + ".exe" in names) and r.get("page"):
                    act.append(str(r["page"]))
            self._rules_active = act
        gm = None
        if game:
            gm = {"name": game["name"]}
            if "forzahorizon" in (game.get("exe") or "").lower():
                gm["fz"] = True
        ctx = {"game": gm, "call": call, "rules": self._rules_active}
        if ctx != self._ctx_last:
            self._ctx_last = ctx
            await self.hub.send("ctx", ctx)

    async def tick_game(self):
        g = self._game
        if not g or not self.hub.clients:
            return
        try:
            f = await self.plat.fps(g["pid"], g["exe"])
        except Exception as e:
            log.debug("fps: %s", e)
            f = None
        if f and f.get("fps"):
            self._fps_hist = (self._fps_hist + [f["fps"]])[-120:]
        h = self._fps_hist
        await self.hub.send("game", {
            "name": g["name"], "rtss": f is not None,
            "fps": f and f.get("fps"), "ft": f and f.get("ft"),
            "avg": round(sum(h) / len(h)) if h else None, "min": fps_low(h),
        }, keep=False)

    # ---------------- Control Center buttons (editable from the phone)
    def tiles_payload(self):
        keep = ("id", "label", "icon", "type", "value", "cmd")
        out = {}
        for lst, n in TILE_SLOTS.items():
            out[lst] = [{**{k: t.get(k) for k in keep if t.get(k) is not None}, "type": tile_type(t)}
                        for t in (self.cfg.get(lst) or [])[:n]]
        return out

    async def run_tile(self, t, ws):
        P, typ = self.plat, tile_type(t)
        val = str(t.get("value") or "")
        if typ == "app":
            res = await P.open_app({**t, "cmd": t.get("cmd") or val})
            msg = f"Switched to {t.get('label')}" if res == "focused" else f"Opening {t.get('label')}"
            await ws.send_str(json.dumps({"t": "toast", "msg": msg, "icon": "check"}))
        elif typ == "keys":
            await P.keys(val)
        elif typ == "text":
            await P.text(val)
        elif typ == "link":
            if not re.match(r"^[a-z][a-z0-9+.-]*:", val, re.I):
                val = "https://" + val
            await P.open_url(val)
        elif typ == "run":
            await P.launch(val)

    async def tile_save(self, lst_name, i, tile):
        if lst_name not in TILE_SLOTS or not 0 <= i < TILE_SLOTS[lst_name]:
            return
        lst = [dict(x) for x in (self.cfg.get(lst_name) or [])]
        defaults = DEFAULT_CONFIG[lst_name]
        while len(lst) <= i:
            lst.append(dict(defaults[len(lst)]) if len(lst) < len(defaults) else
                       {"id": "t" + secrets.token_hex(3), "label": "Button", "icon": "star", "type": "keys", "value": ""})
        if tile is None:                               # back to the factory button
            if i < len(defaults):
                lst[i] = dict(defaults[i])
        else:
            typ = tile.get("type") if tile.get("type") in TILE_TYPES else "keys"
            label = re.sub(r"\s+", " ", str(tile.get("label") or "")).strip()[:22] or "Button"
            icon = re.sub(r"[^a-z0-9.]", "", str(tile.get("icon") or "star"))[:24] or "star"
            val = str(tile.get("value") or "")[:600].strip()
            old = lst[i]
            same = tile_type(old) == typ and (val == (old.get("value") or "") or (typ == "app" and not tile.get("pick")))
            new = {"id": old.get("id") if same and old.get("id") else "t" + secrets.token_hex(3),
                   "label": label, "icon": icon, "type": typ, "value": val}
            if typ == "app" and not tile.get("pick") and old.get("cmd") and same:
                val = new["value"] = old.get("value") or ""
                new["cmd"] = old["cmd"]
                if old.get("match"):
                    new["match"] = old["match"]
            if typ == "app":
                # picked from the Start menu: open it through the shell, so Store apps (Apple Music...) work too
                new.setdefault("cmd", val)             # typed by hand: a command, path or URL scheme
                if tile.get("pick"):
                    new["cmd"] = f'"shell:AppsFolder\\{val}"'
                    exe = re.findall(r"([^\\/]+\.exe)$", val, re.I)
                    if exe:
                        new["match"] = [{"exe": exe[0]}]
            lst[i] = new
        self.cfg[lst_name] = lst
        await self._io(self._persist_cfg_key, lst_name, lst)
        await self.hub.send("tiles", self.tiles_payload(), keep=False)

    # ---------------- play time (Screen Time, for games)
    def _play_load(self):
        if self.demo:
            today = dt.date.today()
            names = ["Forza Horizon 6", "Need for Speed™ Unbound", "EA SPORTS FC™ 26"]
            out = {}
            for k in range(13, 0, -1):
                d = (today - dt.timedelta(days=k)).isoformat()
                rnd = random.Random(k)
                out[d] = {n: rnd.choice([0, 0, 1800, 2700, 4200, 6600]) for n in names}
            out[today.isoformat()] = {"Forza Horizon 6": 4980, "Need for Speed™ Unbound": 1500}
            return out
        try:
            return (json.loads(PLAY_PATH.read_text(encoding="utf-8")) or {}).get("days") or {}
        except Exception:
            return {}

    def _play_save(self):
        keep = sorted(self._play)[-120:]
        self._play = {k: self._play[k] for k in keep}
        tmp = PLAY_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps({"days": self._play}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, PLAY_PATH)

    def play_payload(self):
        today = dt.date.today()
        mon = today - dt.timedelta(days=today.weekday())
        day = lambda d: self._play.get(d.isoformat()) or {}
        week = [day(mon + dt.timedelta(days=k)) for k in range(7)]
        prev = sum(sum(day(mon - dt.timedelta(days=7 - k)).values()) for k in range(7))
        games: dict = {}
        for d in week:
            for n, s in d.items():
                games[n] = games.get(n, 0) + s
        tday = day(today)
        top = sorted(tday.items(), key=lambda x: -x[1])
        return {"today": int(sum(tday.values()) // 60), "top": top[0][0] if top and top[0][1] >= 60 else None,
                "week": [int(sum(d.values()) // 60) for d in week], "dow": today.weekday(),
                "games": [[n, int(s // 60)] for n, s in sorted(games.items(), key=lambda x: -x[1])[:3] if s >= 60],
                "prev": int(prev // 60), "now": self._game["name"] if self._game else None}

    async def tick_play(self):
        if not hasattr(self, "_play"):
            self._play = await self._io(self._play_load)
            self._play_dirty, self._play_last, self._play_sent = 0.0, time.monotonic(), None
        now = time.monotonic()
        step, self._play_last = min(30.0, now - self._play_last), now
        g = self._game
        if g:
            d = self._play.setdefault(dt.date.today().isoformat(), {})
            d[g["name"]] = round(d.get(g["name"], 0) + step, 1)
            self._play_dirty += step
        if not self.demo and self._play_dirty and (self._play_dirty >= 60 or not g):
            self._play_dirty = 0.0
            try:
                await self._io(self._play_save)
            except Exception as e:
                log.debug("playtime save: %s", e)
        p = self.play_payload()
        if p != self._play_sent:
            self._play_sent = p
            await self.hub.send("play", p)

    # ---------------- captures gallery (Game Bar / NVIDIA / AMD clips + screenshots)
    def cap_dirs(self):
        if self.demo:
            return [self.plat.demo_caps()]
        return [Path(os.path.expandvars(os.path.expanduser(d))) for d in (self.cfg.get("capture_dirs") or CAP_DIRS)]

    def _scan_caps(self):
        found, bases = [], {}
        for base in self.cap_dirs():
            if not base.is_dir():
                continue
            for root, subdirs, files in os.walk(base):
                if len(Path(root).relative_to(base).parts) >= 2:
                    subdirs[:] = []
                for f in files:
                    kind = CAP_EXT.get(os.path.splitext(f)[1].lower())
                    if not kind:
                        continue
                    fp = os.path.join(root, f)
                    try:
                        st = os.stat(fp)
                    except OSError:
                        continue
                    if st.st_size < 1024:
                        continue
                    found.append((st.st_mtime, fp, kind, st.st_size))
                    bases[fp] = str(base)
        found.sort(reverse=True)
        items = []
        for mt, fp, kind, size in found[:72]:
            cid = hashlib.sha1(fp.encode("utf-8", "replace")).hexdigest()[:14]
            self._caps[cid] = (fp, kind)
            items.append({"id": cid, "name": os.path.basename(fp), "kind": kind, "ts": int(mt), "size": size, "game": cap_game(fp, bases.get(fp, ""))})
        return items

    async def _cap_watch(self, what):
        before = {i["id"] for i in await self._io(self._scan_caps)}
        for wait in (2, 2, 3, 3, 4, 5):
            await asyncio.sleep(wait)
            items = await self._io(self._scan_caps)
            new = [i for i in items if i["id"] not in before]
            if new:
                await self.hub.send("capnew", {"item": new[0]}, keep=False)
                return

    async def cap_handler(self, request):
        if not self.authed(request):
            return web.Response(status=403, text="bad token")
        ent = self._caps.get(request.match_info["id"])
        if not ent or not os.path.exists(ent[0]):
            return web.Response(status=404)
        hdr = {"Cache-Control": "private, max-age=3600"}
        if request.query.get("dl"):
            hdr["Content-Disposition"] = f'attachment; filename="{safe_filename(os.path.basename(ent[0]))}"'
        return web.FileResponse(ent[0], headers=hdr)

    async def capthumb_handler(self, request):
        if not self.authed(request):
            return web.Response(status=403, text="bad token")
        ent = self._caps.get(request.match_info["id"])
        if not ent:
            return web.Response(status=404)
        path, kind = ent
        data = self._thumbs.get(path)
        if data is None:
            try:
                data = await (self._io(img_thumb, path) if kind == "image" else self.plat.video_thumb(path))
            except Exception as e:
                log.debug("thumb %s: %s", path, e)
                data = None
            self._thumbs[path] = data or b""
            while len(self._thumbs) > 200:
                self._thumbs.pop(next(iter(self._thumbs)))
        if not data:
            return web.Response(status=204)
        return web.Response(body=data, content_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})

    # ---------------- files sent from the phone / iPad
    def drop_dir(self) -> Path:
        d = (self.cfg.get("drop_dir") or "").strip()
        return Path(os.path.expandvars(os.path.expanduser(d))) if d else downloads_dir()

    async def upload_handler(self, request):
        if not self.authed(request):
            return web.Response(status=403, text="bad token")
        dest = self.drop_dir()
        await self._io(lambda: dest.mkdir(parents=True, exist_ok=True))
        reader = await request.multipart()
        saved, total = [], 0
        while True:
            part = await reader.next()
            if part is None:
                break
            if not getattr(part, "filename", None):
                continue
            path = unique_path(dest, safe_filename(part.filename))
            f = await self._io(open, path, "wb")
            try:
                while True:
                    chunk = await part.read_chunk(1 << 20)
                    if not chunk:
                        break
                    total += len(chunk)
                    await self._io(f.write, chunk)
            except Exception:
                f.close()
                await self._io(lambda: path.unlink(missing_ok=True))
                raise
            f.close()
            saved.append(path.name)
        if saved:
            log.info("Received %d file(s) from %s -> %s", len(saved), request.remote, dest)
        return web.json_response({"ok": True, "files": saved, "bytes": total, "dir": str(dest)})

    # ---------------- notifications, webhooks, Siri Shortcuts
    @staticmethod
    def _persist_cfg_key(k, v):
        try:
            d = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
            if d.get(k) != v:
                d[k] = v
                CONFIG_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")
        except Exception as e:
            log.debug("config save: %s", e)

    @staticmethod
    def lan_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return None

    async def tick_cert(self):
        if not self.ssl_ctx:
            return
        ip = lan_ip()
        if ip == self._cert_ip:
            return
        try:
            paths = await self._io(ensure_certs, [ip])
            if paths:
                self.ssl_ctx.load_cert_chain(*map(str, paths))
                self._cert_ip = ip
                log.info("HTTPS certificate now covers %s", ip)
        except Exception as e:
            log.warning("HTTPS certificate refresh failed: %s", e)

    async def ca_handler(self, request):
        p = CERT_DIR / "ca.crt"
        if not p.exists():
            raise web.HTTPNotFound()
        return web.Response(body=p.read_bytes(), content_type="application/x-x509-ca-cert",
                            headers={"Content-Disposition": 'attachment; filename="DeskDeck-CA.crt"'})

    async def setup_handler(self, request):
        if not self.authed(request):
            return web.Response(status=403, text="Open the link with ?k= from DeskDeck")
        ip, tok, hp = lan_ip(), self.cfg["token"], self.cfg.get("https_port")
        https = f"https://{ip}:{hp}/?k={tok}" if hp and self.ssl_ctx else None
        steps = (f"""<li><a class="b" href="/ca.crt">Download the DeskDeck profile</a><small>Tap <b>Allow</b>, then <b>Close</b>.</small></li>
<li>Open <b>Settings</b> → <b>General</b> → <b>VPN &amp; Device Management</b> → <b>DeskDeck Local CA</b> → <b>Install</b>.</li>
<li>Open <b>Settings</b> → <b>General</b> → <b>About</b> → <b>Certificate Trust Settings</b> → turn on <b>DeskDeck Local CA</b>.</li>
<li><a class="b" href="{https}">Open DeskDeck (secure)</a><small>Then <b>Share</b> → <b>Add to Home Screen</b> with <b>Open as Web App</b> on.</small></li>"""
                 if https else "<li>HTTPS is off. Install it with <code>pip install cryptography</code> and restart DeskDeck.</li>")
        html = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DeskDeck · iPad setup</title><style>
body{{margin:0;background:#000;color:#fff;font:17px/1.45 -apple-system,system-ui,sans-serif;padding:36px 22px;max-width:640px}}
h1{{font-size:30px;margin:0 0 6px;letter-spacing:-.02em}}p{{color:#8e8e93;margin:0 0 22px}}
ol{{padding-left:22px}}li{{margin:0 0 18px}}small{{display:block;color:#8e8e93;margin-top:6px}}
a.b{{display:inline-block;background:#0a84ff;color:#fff;text-decoration:none;font-weight:600;padding:12px 18px;border-radius:14px}}
code{{background:#1c1c1e;padding:2px 6px;border-radius:6px}}</style></head><body>
<h1>Set up DeskDeck on iPad</h1><p>One-time steps so the screen stays awake and the clipboard works over Wi-Fi.</p>
<ol>{steps}</ol><p>Phone on USB? You don't need any of this.</p></body></html>"""
        return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-store"})

    async def tick_notes(self):
        nc = self.cfg.get("notify") or {}
        if not nc.get("enabled", True) or not self.hub.clients:
            return
        try:
            notes = await self.plat.notes()
        except Exception as e:
            log.debug("notes: %s", e)
            return
        block = {b.lower() for b in nc.get("block") or []}
        for n in notes:
            if (n.get("app") or "").lower() in block:
                continue
            await self.hub.send("note", n, keep=False)

    HOOKS_PATH = ROOT / "hooks.json"

    def _load_hooks(self):
        try:
            d = json.loads(self.HOOKS_PATH.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def _hooks_payload(self):
        now = time.time()
        vals = [v for v in self.hooks.values() if not v.get("ttl") or now - v["ts"] < v["ttl"]]
        vals.sort(key=lambda v: v.get("order", v["ts"]))
        acts = self.cfg.get("hook_actions") or {}
        return {"values": [{**v, "action": v["id"] in acts} for v in vals], "key": self.cfg.get("hook_key"),
                "lan": self.lan_ip(), "port": self.cfg.get("port")}

    async def push_hooks(self):
        await self.hub.send("hooks", self._hooks_payload())

    async def tick_hooks(self):
        if self._hooks_dirty:
            self._hooks_dirty = False
            try:
                await self._io(lambda: self.HOOKS_PATH.write_text(json.dumps(self.hooks, ensure_ascii=False), encoding="utf-8"))
            except Exception:
                pass
        await self.push_hooks()  # also drops expired values from the Room page

    def hook_ok(self, request) -> bool:
        k = request.query.get("key") or request.headers.get("X-DeskDeck-Key") or ""
        return bool(k) and secrets.compare_digest(k, self.cfg.get("hook_key") or "")

    async def _hook_body(self, request):
        d = dict(request.query)
        d.pop("key", None)
        if request.method == "POST" and request.can_read_body:
            raw = await request.text()
            try:
                js = json.loads(raw) if raw.strip() else None
                if isinstance(js, dict):
                    d.update(js)
            except ValueError:
                from urllib.parse import parse_qsl
                d.update(dict(parse_qsl(raw)))
        return d

    async def hook_value(self, request):
        if not self.hook_ok(request):
            return web.json_response({"ok": False, "error": "bad key"}, status=403)
        d = await self._hook_body(request)
        items = d.get("values") if isinstance(d.get("values"), list) else [d]
        for it in items[:20]:
            hid = re.sub(r"[^\w.-]", "_", str(it.get("id") or it.get("label") or ""))[:40]
            if not hid:
                continue
            raw = it.get("value")
            val = raw
            if isinstance(raw, str):
                low = raw.strip().lower()
                if low in ("true", "on", "yes"):
                    val = True
                elif low in ("false", "off", "no"):
                    val = False
                else:
                    n = _num(raw)
                    val = n if n is not None and re.fullmatch(r"\s*-?[\d.,]+\s*", raw) else raw[:60]
            prev = self.hooks.get(hid) or {}
            hist = prev.get("hist", [])
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                hist = (hist + [round(float(val), 3)])[-120:]
            self.hooks[hid] = {
                "id": hid, "label": str(it.get("label") or prev.get("label") or hid)[:30], "value": val,
                "unit": str(it.get("unit", prev.get("unit", "")))[:8], "sub": str(it.get("sub", prev.get("sub", "")))[:60],
                "color": str(it.get("color", prev.get("color", "")))[:20], "ts": time.time(),
                "ttl": float(it.get("ttl", prev.get("ttl", 0)) or 0), "hist": hist,
                "order": prev.get("order", time.time()),
            }
        self._hooks_dirty = True
        await self.push_hooks()
        return web.json_response({"ok": True})

    async def hook_notify(self, request):
        if not self.hook_ok(request):
            return web.json_response({"ok": False, "error": "bad key"}, status=403)
        d = await self._hook_body(request)
        await self.hub.send("note", {"app": str(d.get("app", "Webhook"))[:30], "title": str(d.get("title", ""))[:80],
                                     "body": str(d.get("body", d.get("message", "")))[:220],
                                     "buzz": str(d.get("vibrate", "1")) not in ("0", "false")}, keep=False)
        return web.json_response({"ok": True})

    async def hook_page(self, request):
        if not self.hook_ok(request):
            return web.json_response({"ok": False, "error": "bad key"}, status=403)
        d = await self._hook_body(request)
        await self.hub.send("goto", {"page": str(d.get("page", "home"))[:20]}, keep=False)
        return web.json_response({"ok": True})

    async def hook_clear(self, request):
        if not self.hook_ok(request):
            return web.json_response({"ok": False, "error": "bad key"}, status=403)
        d = await self._hook_body(request)
        if d.get("id"):
            self.hooks.pop(str(d["id"]), None)
        else:
            self.hooks.clear()
        self._hooks_dirty = True
        await self.push_hooks()
        return web.json_response({"ok": True})

    DO_MAP = {
        "lock": {"a": "sys", "v": "lock"}, "desktop": {"a": "sys", "v": "desk"}, "screenshot": {"a": "sys", "v": "shot"},
        "snip": {"a": "sys", "v": "snip"}, "taskview": {"a": "sys", "v": "taskview"}, "mic": {"a": "mic"},
        "mute": {"a": "vol", "mute": True}, "play": {"a": "media", "cmd": "toggle"}, "pause": {"a": "media", "cmd": "toggle"},
        "next": {"a": "media", "cmd": "next"}, "prev": {"a": "media", "cmd": "prev"},
        "silent": {"a": "mode", "v": "silent"}, "balanced": {"a": "mode", "v": "balanced"}, "turbo": {"a": "mode", "v": "turbo"},
        "focus": {"a": "focus", "cmd": "start"}, "unfocus": {"a": "focus", "cmd": "stop"},
        "forza": {"a": "forza", "v": "open"},
    }

    class _Sink:
        """Stands in for a phone socket when an action comes from Shortcuts/HTTP."""
        def __init__(self):
            self.msgs = []

        async def send_str(self, s):
            try:
                self.msgs.append(json.loads(s))
            except Exception:
                pass

    async def do_handler(self, request):
        """Siri Shortcuts / scripts: GET /api/do?key=HOOK_KEY&do=lock  (also: vol&v=30, app&v=discord, page&v=focus)"""
        if not self.hook_ok(request):
            return web.json_response({"ok": False, "error": "bad key"}, status=403)
        d = await self._hook_body(request)
        what, v = str(d.get("do") or d.get("a") or "").lower(), d.get("v")
        if what == "vol" and v is not None:
            m = {"a": "vol", "set": max(0.0, min(1.0, (_num(str(v)) or 0) / 100))}
        elif what in ("app", "macro") and v:
            m = {"a": what, "id": str(v)}
        elif what == "page" and v:
            await self.hub.send("goto", {"page": str(v)}, keep=False)
            return web.json_response({"ok": True})
        elif what in self.DO_MAP:
            m = dict(self.DO_MAP[what])
        else:
            return web.json_response({"ok": False, "error": "unknown action",
                                      "actions": sorted(list(self.DO_MAP) + ["vol", "app", "macro", "page"])}, status=400)
        sink = self._Sink()
        try:
            await self.act(m, sink)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)
        said = next((x.get("msg") for x in sink.msgs if x.get("t") == "toast"), None)
        await self.hub.send("toast", {"msg": said or f"Shortcut: {what}", "icon": "bolt"}, keep=False)
        return web.json_response({"ok": True, "said": said})

    # ---------------- Health page: heavy apps, Wi-Fi, Claude usage
    async def tick_procs(self):
        if not self.hub.clients or time.monotonic() > self._procs_on:
            return  # only while someone is looking at the Health page
        try:
            lst = await self.plat.procs()
        except Exception as e:
            log.debug("procs: %s", e)
            return
        await self.hub.send("procs", {"list": lst}, keep=False)

    async def tick_wifi(self):
        try:
            w = await self.plat.wifi()
        except Exception:
            w = None
        await self.hub.send("wifi", w or {})

    CLAUDE_CREDS = Path.home() / ".claude" / ".credentials.json"

    async def tick_quota(self):
        """Claude usage (the numbers behind Claude Code's /usage). Read-only, and polite: at most every 3 min."""
        if time.time() < self._quota_next:
            return
        if self.demo:
            t = time.time()
            self._quota_next = t + 60
            await self.hub.send("quota", {"ok": True, "plan": "Pro", "limits": [
                {"k": "session", "label": "5-hour", "pct": 72, "reset": int(t + 2 * 3600 + 25 * 60)},
                {"k": "weekly", "label": "Weekly", "pct": 34, "reset": int(t + 3 * 86400)}]})
            return
        self._quota_next = time.time() + 180

        async def fail(msg, wait):
            self._quota_next = time.time() + wait
            prev = self._quota_last or {}
            await self.hub.send("quota", {**prev, "ok": bool(prev.get("limits")), "err": msg})
        try:
            creds = json.loads(self.CLAUDE_CREDS.read_text(encoding="utf-8"))
            o = creds.get("claudeAiOauth") or {}
            token = o.get("accessToken") or ""
        except FileNotFoundError:
            return await fail("Sign in to Claude Code on this PC to see usage", 600)
        except Exception:
            return await fail("Couldn't read Claude Code sign-in", 120)
        exp = o.get("expiresAt") or 0
        if not token or (exp and exp / 1000 < time.time() + 60):
            return await fail("Claude Code sign-in expired - open Claude Code once", 120)
        try:
            async with self.http.get("https://api.anthropic.com/api/oauth/usage", timeout=ClientTimeout(total=15),
                                     headers={"Authorization": f"Bearer {token}", "anthropic-beta": "oauth-2025-04-20",
                                              "User-Agent": "DeskDeck"}) as r:
                if r.status == 429:
                    ra = _num(r.headers.get("Retry-After") or "") or 600
                    return await fail("Usage check is rate limited", max(180, ra))
                if r.status == 401:
                    return await fail("Claude Code sign-in was refused", 1800)
                if r.status != 200:
                    return await fail(f"Usage unavailable (HTTP {r.status})", 600)
                js = await r.json(content_type=None)
        except Exception:
            return await fail("Can't reach Anthropic right now", 120)

        def ts(v):
            try:
                return int(dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp())
            except Exception:
                return None
        limits = []
        for l in js.get("limits") or []:
            kind = l.get("kind")
            lab = {"session": "5-hour", "weekly_all": "Weekly"}.get(kind)
            if lab:
                limits.append({"k": "session" if kind == "session" else "weekly", "label": lab,
                               "pct": round(_num(str(l.get("percent"))) or 0), "reset": ts(l.get("resets_at"))})
        if not limits:
            for key, k, lab in (("five_hour", "session", "5-hour"), ("seven_day", "weekly", "Weekly")):
                v = js.get(key)
                if isinstance(v, dict):
                    limits.append({"k": k, "label": lab, "pct": round(_num(str(v.get("utilization"))) or 0),
                                   "reset": ts(v.get("resets_at"))})
        sub = (o.get("subscriptionType") or "").capitalize() or "Claude"
        self._quota_last = {"ok": True, "plan": sub, "limits": limits}
        await self.hub.send("quota", self._quota_last)

    # ---------------- Focus page: pomodoro + daily checklist (shared by every screen)
    FOCUS_PATH = ROOT / "focus.json"

    def _load_focus(self):
        try:
            d = json.loads(self.FOCUS_PATH.read_text(encoding="utf-8"))
        except Exception:
            d = {}
        d.setdefault("todo", [])
        d.setdefault("day", time.strftime("%Y-%m-%d"))
        d["timer"] = {"mode": "idle", "end": 0, "left": 0, "round": 1, "paused": False}
        return d

    def _save_focus(self):
        try:
            self.FOCUS_PATH.write_text(json.dumps({"todo": self.focus["todo"], "day": self.focus["day"]},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:
            log.debug("focus save: %s", e)

    def _focus_payload(self):
        f = self.cfg.get("focus") or {}
        t = self.focus["timer"]
        return {"todo": self.focus["todo"], "mode": t["mode"], "end": t["end"], "left": t["left"],
                "paused": t["paused"], "round": t["round"], "rounds": int(f.get("rounds", 4)),
                "len": {"work": int(f.get("work", 25)), "short": int(f.get("short", 5)), "long": int(f.get("long", 15))}}

    async def push_focus(self):
        await self.hub.send("focus", self._focus_payload())

    async def tick_focus(self):
        today = time.strftime("%Y-%m-%d")
        changed = False
        if self.focus["day"] != today:  # the checklist un-ticks itself every morning
            self.focus["day"] = today
            for it in self.focus["todo"]:
                it["done"] = False
            self._save_focus()
            changed = True
        t = self.focus["timer"]
        if t["mode"] != "idle" and not t["paused"] and time.time() >= t["end"]:
            f = self.cfg.get("focus") or {}
            if t["mode"] == "work":
                long_ = t["round"] >= int(f.get("rounds", 4))
                t["mode"] = "long" if long_ else "short"
                mins = int(f.get("long" if long_ else "short", 5))
                await self.hub.send("toast", {"msg": "Break time", "icon": "leaf"}, keep=False)
            else:
                t["round"] = 1 if t["mode"] == "long" else t["round"] + 1
                t["mode"] = "work"
                mins = int(f.get("work", 25))
                await self.hub.send("toast", {"msg": "Back to focus", "icon": "bolt"}, keep=False)
            t["end"] = time.time() + mins * 60
            changed = True
        if changed or "focus" not in self.hub.state:
            await self.push_focus()

    async def focus_cmd(self, m):
        cmd = m.get("cmd")
        f = self.cfg.get("focus") or {}
        t = self.focus["timer"]
        if cmd == "start":
            t.update(mode="work", end=time.time() + int(f.get("work", 25)) * 60, paused=False, round=1)
        elif cmd == "pause" and t["mode"] != "idle" and not t["paused"]:
            t.update(paused=True, left=max(0, t["end"] - time.time()))
        elif cmd == "resume" and t["paused"]:
            t.update(paused=False, end=time.time() + t["left"])
        elif cmd == "skip" and t["mode"] != "idle":
            t["end"] = time.time()
            t["paused"] = False
            await self.tick_focus()
            return
        elif cmd == "add5" and t["mode"] != "idle":
            if t["paused"]:
                t["left"] += 300
            else:
                t["end"] += 300
        elif cmd == "stop":
            t.update(mode="idle", end=0, left=0, paused=False, round=1)
        elif cmd == "add":
            txt = str(m.get("text", "")).strip()[:80]
            if txt:
                self.focus["todo"].append({"id": secrets.token_hex(4), "t": txt, "done": False})
                self.focus["todo"] = self.focus["todo"][-30:]
        elif cmd in ("toggle", "del"):
            for it in list(self.focus["todo"]):
                if it["id"] == m.get("id"):
                    if cmd == "toggle":
                        it["done"] = not it["done"]
                    else:
                        self.focus["todo"].remove(it)
        elif cmd == "clear":
            self.focus["todo"] = [it for it in self.focus["todo"] if not it["done"]]
        if cmd in ("add", "toggle", "del", "clear"):
            await self._io(self._save_focus)
        await self.push_focus()

    # ---------------- Universal Radio (FH6 mod)
    def _radio_base(self):
        u = (self.cfg.get("radio_url") or "http://127.0.0.1:8420").rstrip("/")
        if self._radio_flip and u.endswith(":8420"):  # the mod moves to 8421 when 8420 is taken
            u = u[:-4] + "8421"
        return u

    def _rart_put(self, data: bytes) -> str:
        h = hashlib.sha1(data).hexdigest()[:12]
        self.rart[h] = (data, sniff_type(data))
        while len(self.rart) > 8:
            self.rart.pop(next(iter(self.rart)))
        return f"/rart/{h}"

    async def _radio_get(self, path, timeout=1.5):
        if self.demo_forza:
            return self._fake_radio_get(path)
        async with self.http.get(self._radio_base() + path, timeout=ClientTimeout(total=timeout)) as r:
            return await r.json(content_type=None)

    async def _radio_post(self, path, body=None):
        if self.demo_forza:
            return self._fake_radio_post(path, body)
        async with self.http.post(self._radio_base() + path, json=body, timeout=ClientTimeout(total=3)) as r:
            await r.read()

    async def tick_radio(self):
        try:
            st = await self._radio_get("/api/state", 0.8)
        except Exception:
            self._radio_fail += 1
            self._radio_flip = not self._radio_flip
            if self._radio_fail >= 3 and self._radio_last is not False:
                self._radio_last = False
                await self.hub.send("radio", {"on": False})
            return
        self._radio_fail = 0
        src = st.get("sources") or {}
        active = src.get("active") or ""
        info = next((x for x in src.get("available", []) if x.get("name") == active), {})
        det = info.get("details") or {}
        caps = info.get("capabilities") or {}
        tr = st.get("track") or {}
        # station list (sources that have stations)
        if active in ("youtube_music", "jellyfin", "local_files"):
            if active != self._radio_st_src or time.monotonic() - self._radio_st_at > 30:
                self._radio_st_at, self._radio_st_src = time.monotonic(), active
                try:
                    js = await self._radio_get(f"/api/source/{active}/stations")
                    self._radio_stations = [x.get("name") for x in js.get("stations", []) if x.get("name")]
                except Exception:
                    self._radio_stations = []
        else:
            self._radio_stations, self._radio_st_src = [], active
        # artwork (proxied so the phone never needs the internet)
        art_src = tr.get("artwork_url") or ""
        if art_src != self._radio_art_src:
            self._radio_art_src, self._radio_art = art_src, None
            data = None
            if self.demo_forza and art_src:
                data = self._fake_art(art_src)
            elif art_src:
                url = self._radio_base() + art_src if art_src.startswith("/") else art_src
                try:
                    async with self.http.get(url, timeout=ClientTimeout(total=5)) as r:
                        if r.status == 200:
                            data = await r.read()
                except Exception:
                    data = None
            if data:
                self._radio_art = self._rart_put(data)
        title, artist = clean_track(tr.get("title") or "", tr.get("artist") or "")
        audio = st.get("audio") or {}
        payload = {
            "on": True, "attached": bool(audio.get("active")),
            "source": active, "sourceName": info.get("display_name") or active,
            "state": info.get("playback_state") or "", "title": title, "artist": artist,
            "art": self._radio_art, "dur": round((tr.get("duration_ms") or 0) / 1000, 1),
            "stations": self._radio_stations,
            "station": det.get("active_station") or "",
            "shuffle": det.get("shuffle"), "gain": audio.get("output_gain"),
            "queue": bool(caps.get("queue")) and active in ("youtube_music", "jellyfin", "local_files"),
            "cursor": det.get("queue_cursor"),
        }
        if payload != self._radio_last or time.monotonic() - self._radio_sent_at > 3:
            qkey = (active, det.get("active_station"), det.get("queue_size"), det.get("queue_cursor"), title)
            requeue = self._radio_last and qkey != self._radio_qkey
            self._radio_qkey = qkey
            self._radio_last, self._radio_sent_at = payload, time.monotonic()
            await self.hub.send("radio", {**payload, "pos": round((tr.get("position_ms") or 0) / 1000, 1)})
            if requeue:
                await self.hub.send("radioqdirty", {}, keep=False)

    @staticmethod
    def _yt_id(url: str):
        m = re.search(r"(?:[?&]v=|youtu\.be/|/shorts/|/embed/)([\w-]{11})", url or "")
        return m.group(1) if m else None

    async def radio_queue(self):
        last = self._radio_last or {}
        src = last.get("source") or ""
        if not last.get("queue"):
            return {"tracks": [], "cursor": None}
        js = await self._radio_get(f"/api/source/{src}/queue", 3)
        out = []
        for e in (js.get("tracks") or [])[:200]:
            t, a = clean_track(e.get("title") or "", e.get("artist") or e.get("folder") or "")
            vid = self._yt_id(e.get("url") or "")
            out.append({"i": e.get("index"), "t": t, "a": a, "th": f"/yt/{vid}" if vid else None})
        return {"tracks": out, "cursor": js.get("cursor")}

    async def radio_cmd(self, cmd, v=None):
        last = self._radio_last or {}
        src = last.get("source") or "youtube_music"
        if cmd == "toggle":
            await self._radio_post(f"/api/source/{src}/{'pause' if last.get('state') == 'playing' else 'play'}")
        elif cmd in ("next", "prev"):
            await self._radio_post(f"/api/source/{src}/{'next' if cmd == 'next' else 'previous'}")
        elif cmd == "station" and v:
            await self._radio_post(f"/api/source/{src}/activate", {"name": str(v)})
        elif cmd == "jump" and v is not None:
            await self._radio_post(f"/api/source/{src}/play", {"index": int(v)})
        elif cmd == "shuffle" and src in ("youtube_music", "jellyfin"):
            await self._radio_post(f"/api/source/{src}/shuffle", {"shuffle": bool(v)})
        elif cmd == "gain" and v is not None:
            await self._radio_post("/api/options", {"output_gain": max(0.0, min(1.0, float(v)))})

    async def yt_thumb_handler(self, request):
        vid = request.match_info["vid"]
        if not re.fullmatch(r"[\w-]{11}", vid):
            raise web.HTTPNotFound()
        data = self.thumbs.get(vid)
        if data is None:
            if self.demo_forza:
                data = self._fake_art(vid)
            else:
                try:
                    async with self.http.get(f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                                             timeout=ClientTimeout(total=6)) as r:
                        if r.status != 200:
                            raise web.HTTPNotFound()
                        data = await r.read()
                except web.HTTPException:
                    raise
                except Exception:
                    raise web.HTTPNotFound()
            self.thumbs[vid] = data
            while len(self.thumbs) > 300:
                self.thumbs.pop(next(iter(self.thumbs)))
        return web.Response(body=data, content_type=sniff_type(data),
                            headers={"Cache-Control": "public, max-age=604800"})

    async def rart_handler(self, request):
        item = self.rart.get(request.match_info["h"])
        if not item:
            raise web.HTTPNotFound()
        return web.Response(body=item[0], content_type=item[1],
                            headers={"Cache-Control": "public, max-age=86400"})

    # ---- demo radio (for --demo-forza)
    _FAKE_Q = [("Kaze no Machi - Midnight Expressway (Official Video)", "KazeNoMachiVEVO"),
               ("Afterglow Avenue [Official Music Video]", "Neon Harbor - Topic"),
               ("Tokyo Drift Club - Neon Shrine (Lyrics)", "Tokyo Drift Club"),
               ("Touge Sunrise (Visualizer)", "Akina Waves"),
               ("Bayside 86 - Wangan Lights | 4K", "Bayside86Official"),
               ("Rain on Route 9 (Audio)", "Slow Static - Topic"),
               ("Hikari - Paper Lanterns (Official Video) [HD]", "HikariVEVO"),
               ("Coastline 1989", "Neon Harbor - Topic")]

    def _fake(self):
        if not hasattr(self, "_fr"):
            self._fr = {"cur": 1, "t0": time.monotonic(), "playing": True, "gain": 0.62, "shuffle": True,
                        "station": "Night Drive"}
        return self._fr

    def _fake_art(self, key: str) -> bytes:
        arts = getattr(self.plat, "arts", None)
        if arts:
            return arts[sum(map(ord, key)) % len(arts)]
        return png_bytes(4, 4, lambda x, y: (90, 60, 160))

    def _fake_radio_get(self, path):
        fr = self._fake()
        if path == "/api/state":
            t = time.monotonic()
            if fr["playing"] and t - fr["t0"] > 200:
                fr["cur"] = (fr["cur"] + 1) % len(self._FAKE_Q); fr["t0"] = t
            pos = (t - fr["t0"]) if fr["playing"] else fr.get("paused_at", 0)
            title, artist = self._FAKE_Q[fr["cur"]]
            return {"audio": {"active": True, "output_gain": fr["gain"]},
                    "sources": {"active": "youtube_music", "available": [{
                        "name": "youtube_music", "display_name": "YouTube Music",
                        "playback_state": "playing" if fr["playing"] else "paused",
                        "capabilities": {"previous": True, "queue": True},
                        "details": {"shuffle": fr["shuffle"], "active_station": fr["station"],
                                    "queue_size": len(self._FAKE_Q), "queue_cursor": fr["cur"]}}]},
                    "track": {"title": title, "artist": artist, "artwork_url": f"demo{fr['cur']}{fr['station']}",
                              "duration_ms": 200000, "position_ms": int(pos * 1000)}}
        if path.endswith("/stations"):
            return {"stations": [{"name": n} for n in ("Night Drive", "JDM Classics", "Lo-fi Touge", "Phonk Run", "City Pop")],
                    "active_station": fr["station"]}
        if path.endswith("/queue"):
            return {"cursor": fr["cur"], "tracks": [
                {"index": i, "title": t, "artist": a, "url": f"https://music.youtube.com/watch?v=demo{i:07d}x{fr['station'][:2]}"[:46]}
                for i, (t, a) in enumerate(self._FAKE_Q)]}
        return {}

    def _fake_radio_post(self, path, body):
        fr = self._fake(); body = body or {}
        n = len(self._FAKE_Q)
        if path.endswith("/pause"):
            fr["paused_at"] = time.monotonic() - fr["t0"]; fr["playing"] = False
        elif path.endswith("/play") and "index" in body:
            fr["cur"] = int(body["index"]) % n; fr["t0"] = time.monotonic(); fr["playing"] = True
        elif path.endswith("/play"):
            fr["t0"] = time.monotonic() - fr.get("paused_at", 0); fr["playing"] = True
        elif path.endswith("/next"):
            fr["cur"] = (fr["cur"] + 1) % n; fr["t0"] = time.monotonic()
        elif path.endswith("/previous"):
            fr["cur"] = (fr["cur"] - 1) % n; fr["t0"] = time.monotonic()
        elif path.endswith("/activate"):
            fr["station"] = body.get("name") or fr["station"]; fr["cur"] = 0; fr["t0"] = time.monotonic()
        elif path.endswith("/shuffle"):
            fr["shuffle"] = bool(body.get("shuffle"))
        elif path == "/api/options":
            fr["gain"] = float(body.get("output_gain", fr["gain"]))

    # ---------------- forza
    @staticmethod
    def _load_cars():
        try:
            return json.loads((ROOT / "cars.json").read_text(encoding="utf-8"))
        except Exception:
            return {}

    async def loop_forza(self):
        was_live = False
        t0 = time.monotonic()
        while True:
            await asyncio.sleep(1 / 30)
            if self.demo_forza:
                d, fresh = fake_forza(time.monotonic() - t0), True
            else:
                r = self.forza
                d = r.latest if r else None
                fresh = d is not None and time.monotonic() - r.stamp < 1.5
            if fresh:
                if self.hub.clients:
                    o = d["ord"]
                    await self.hub.send("fz", {**d, "live": True, "name": self.cars.get(str(o)),
                                               "car": self.cardb.get(o)}, keep=False)
                was_live = True
            elif was_live:
                was_live = False
                await self.hub.send("fz", {"live": False}, keep=False)

    async def tick_cars(self):
        await self.cardb.refresh(self.http, self.cfg.get("car_list_url") or "")

    def save_car_name(self, ordinal: int, name: str):
        name = (name or "").strip()[:60]
        if name:
            self.cars[str(int(ordinal))] = name
        else:
            self.cars.pop(str(int(ordinal)), None)
        (ROOT / "cars.json").write_text(json.dumps(self.cars, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---------------- volume / privacy / ping
    async def tick_volume(self):
        st = await self.plat.vol_state()
        if st != self._vol_last:
            self._vol_last = st
            await self.hub.send("vol", st)

    async def push_volume(self):
        self._vol_last = await self.plat.vol_state()
        await self.hub.send("vol", self._vol_last)

    async def tick_privacy(self):
        p = await self.plat.privacy()
        if p != self._air_last:
            self._air_last = p
            await self.hub.send("air", p)

    async def tick_ping(self):
        ms = None
        if self.demo:
            ms = round(9 + random.random() * 9, 1)
        else:
            h, p = self.cfg["ping"]["host"], int(self.cfg["ping"]["port"])
            t = time.perf_counter()
            try:
                _, w = await asyncio.wait_for(asyncio.open_connection(h, p), 2.5)
                ms = round((time.perf_counter() - t) * 1000, 1)
                w.close()
            except Exception:
                ms = None
        await self.hub.send("ping", {"ms": ms})

    # ---------------- weather
    async def tick_weather(self):
        loc = self.cfg["location"]
        try:
            d = await self.fetch_weather(loc)
        except Exception as e:
            if self.demo:
                d = self.fake_weather(loc)
            else:
                raise e
        await self.hub.send("wx", d)

    async def fetch_weather(self, loc):
        params = {
            "latitude": loc["lat"], "longitude": loc["lon"], "timezone": "auto", "timeformat": "unixtime",
            "forecast_days": 2,
            "current": "temperature_2m,apparent_temperature,weather_code,is_day,precipitation,relative_humidity_2m",
            "hourly": "temperature_2m,weather_code,precipitation_probability,is_day",
            "minutely_15": "precipitation",
            "daily": "temperature_2m_max,temperature_2m_min,sunrise,sunset",
        }
        async with self.http.get("https://api.open-meteo.com/v1/forecast", params=params) as r:
            r.raise_for_status()
            d = await r.json()
        cur, hr, dy = d["current"], d["hourly"], d["daily"]
        now = time.time()
        code = int(cur.get("weather_code") or 0)
        raining = (cur.get("precipitation") or 0) > 0.05 or code in RAIN_CODES
        start = end = None
        mt = (d.get("minutely_15") or {}).get("time") or []
        mp = (d.get("minutely_15") or {}).get("precipitation") or []
        if not raining:
            for t, p in zip(mt, mp):
                if t < now:
                    continue
                if t - 900 > now + 3 * 3600:
                    break
                if p is not None and p >= 0.2:
                    start = max(t - 900, now)
                    break
            if start is None:
                for t, pp in zip(hr["time"], hr["precipitation_probability"]):
                    if t + 3600 < now or pp is None:
                        continue
                    if t > now + 3 * 3600:
                        break
                    if pp >= 60:
                        start = max(t, now)
                        break
        else:
            for t, p in zip(mt, mp):
                if t <= now:
                    continue
                if t > now + 4 * 3600:
                    break
                if p is not None and p < 0.05:
                    end = t - 900
                    break
        probs = [pp for t, pp in zip(hr["time"], hr["precipitation_probability"])
                 if pp is not None and now - 3600 < t <= now + 3 * 3600]
        hourly = []
        for t, tc, wc, isd in zip(hr["time"], hr["temperature_2m"], hr["weather_code"], hr["is_day"]):
            if t + 3600 > now and len(hourly) < 6:
                hourly.append({"t": t, "temp": round(tc), "code": wc, "day": bool(isd)})
        return {
            "name": loc["name"], "temp": round(cur["temperature_2m"]), "feels": round(cur["apparent_temperature"]),
            "code": code, "day": bool(cur.get("is_day", 1)), "hum": cur.get("relative_humidity_2m"),
            "hi": round(dy["temperature_2m_max"][0]), "lo": round(dy["temperature_2m_min"][0]),
            "rain": {"now": raining, "start": start, "end": end, "prob": max(probs) if probs else None},
            "hourly": hourly, "ts": int(now),
        }

    def fake_weather(self, loc):
        now = time.time()
        return {"name": loc["name"], "temp": 29, "feels": 34, "code": 2, "day": 7 <= time.localtime().tm_hour < 19,
                "hum": 74, "hi": 32, "lo": 24,
                "rain": {"now": False, "start": now + 24 * 60, "end": None, "prob": 80},
                "hourly": [], "ts": int(now)}

    # ---------------- F1
    async def tick_f1(self):
        try:
            d = await self.fetch_f1()
        except Exception as e:
            if self.demo:
                d = self.fake_f1()
            else:
                raise e
        await self.hub.send("f1", d)

    async def _j(self, path):
        async with self.http.get(f"https://api.jolpi.ca/ergast/f1/{path}") as r:
            r.raise_for_status()
            return (await r.json())["MRData"]

    @staticmethod
    def _ts(date, tm):
        tm = (tm or "12:00:00Z").replace("Z", "+00:00")
        if "+" not in tm and "-" not in tm[1:]:
            tm += "+00:00"
        return dt.datetime.fromisoformat(f"{date}T{tm}").timestamp()

    async def fetch_f1(self):
        now = time.time()
        races = (await self._j("current.json?limit=100"))["RaceTable"]["Races"]
        nxt = next((r for r in races if self._ts(r["date"], r.get("time")) + 3 * 3600 > now), None)
        if nxt is None and races:
            await asyncio.sleep(0.4)
            try:
                year = int(races[0]["season"]) + 1
                more = (await self._j(f"{year}.json?limit=100"))["RaceTable"]["Races"]
                nxt = next((r for r in more if self._ts(r["date"], r.get("time")) > now), None)
            except Exception:
                nxt = None
        await asyncio.sleep(0.4)
        sl = (await self._j("current/driverStandings.json?limit=100"))["StandingsTable"]["StandingsLists"]
        standings, season = [], None
        if sl:
            season = sl[0].get("season")
            for s in sl[0]["DriverStandings"]:
                drv, cons = s["Driver"], (s.get("Constructors") or [{}])[-1]
                standings.append({
                    "pos": int(s["position"]) if str(s.get("position", "")).isdigit() else None,
                    "id": drv.get("driverId"), "code": drv.get("code") or drv.get("familyName", "")[:3].upper(),
                    "first": drv.get("givenName"), "last": drv.get("familyName"),
                    "team": cons.get("name"), "teamId": cons.get("constructorId"),
                    "pts": float(s.get("points") or 0), "wins": int(s.get("wins") or 0),
                })
        await asyncio.sleep(0.4)
        last = None
        try:
            lr = (await self._j("current/last/results.json"))["RaceTable"]["Races"]
            if lr:
                r0 = lr[0]
                res = r0.get("Results") or []
                last = {"name": r0["raceName"], "round": int(r0["round"]),
                        "top": [{"pos": int(x["position"]), "code": x["Driver"].get("code"),
                                 "id": x["Driver"]["driverId"], "teamId": x["Constructor"]["constructorId"]}
                                for x in res[:3]]}
                fav = next((x for x in res if x["Driver"]["driverId"] == self.cfg.get("f1_favourite")), None)
                if fav:
                    last["fav"] = {"pos": fav.get("positionText"), "pts": float(fav.get("points") or 0)}
        except Exception:
            pass
        out = {"season": season, "standings": standings, "last": last, "fav": self.cfg.get("f1_favourite"),
               "next": None, "total": len(races)}
        if nxt:
            sess = []
            for k, label in F1_SESSIONS:
                if k in nxt and isinstance(nxt[k], dict):
                    sess.append({"k": label, "ts": self._ts(nxt[k]["date"], nxt[k].get("time"))})
            race_ts = self._ts(nxt["date"], nxt.get("time"))
            sess.append({"k": "Race", "ts": race_ts})
            sess.sort(key=lambda x: x["ts"])
            c = nxt.get("Circuit", {})
            out["next"] = {"name": nxt["raceName"], "round": int(nxt["round"]), "season": nxt.get("season"),
                           "circuit": c.get("circuitName"), "locality": c.get("Location", {}).get("locality"),
                           "country": c.get("Location", {}).get("country"), "race": race_ts, "sessions": sess}
        return out

    def fake_f1(self):
        now = time.time()
        base = now + 2 * 86400 + 5 * 3600
        names = [("NOR", "Lando", "Norris", "mclaren", "norris"), ("PIA", "Oscar", "Piastri", "mclaren", "piastri"),
                 ("VER", "Max", "Verstappen", "red_bull", "max_verstappen"), ("RUS", "George", "Russell", "mercedes", "russell"),
                 ("LEC", "Charles", "Leclerc", "ferrari", "leclerc"), ("HAM", "Lewis", "Hamilton", "ferrari", "hamilton"),
                 ("ANT", "Kimi", "Antonelli", "mercedes", "antonelli"), ("SAI", "Carlos", "Sainz", "williams", "sainz"),
                 ("ALB", "Alexander", "Albon", "williams", "albon"), ("HUL", "Nico", "Hulkenberg", "audi", "hulkenberg"),
                 ("ALO", "Fernando", "Alonso", "aston_martin", "alonso"), ("GAS", "Pierre", "Gasly", "alpine", "gasly")]
        pts = [341, 322, 298, 251, 214, 168, 121, 64, 58, 47, 41, 30]
        st = [{"pos": i + 1, "id": n[4], "code": n[0], "first": n[1], "last": n[2], "team": n[3], "teamId": n[3],
               "pts": float(pts[i]), "wins": 0} for i, n in enumerate(names)]
        sess = [{"k": "Practice 1", "ts": base - 2 * 86400 - 4 * 3600}, {"k": "Sprint Qualifying", "ts": base - 2 * 86400},
                {"k": "Sprint", "ts": base - 86400 - 4 * 3600}, {"k": "Qualifying", "ts": base - 86400},
                {"k": "Race", "ts": base}]
        return {"season": "2026", "standings": st, "fav": "sainz", "total": 24,
                "last": {"name": "Demo Grand Prix", "round": 21,
                         "top": [{"pos": 1, "code": "NOR", "id": "norris", "teamId": "mclaren"},
                                 {"pos": 2, "code": "VER", "id": "max_verstappen", "teamId": "red_bull"},
                                 {"pos": 3, "code": "LEC", "id": "leclerc", "teamId": "ferrari"}],
                         "fav": {"pos": "6", "pts": 8.0}},
                "next": {"name": "Qatar Grand Prix", "round": 22, "season": "2026", "circuit": "Lusail International Circuit",
                         "locality": "Lusail", "country": "Qatar", "race": base, "sessions": sess}}

    # ---------------- photos
    async def tick_photos(self):
        d = Path(os.path.expandvars(os.path.expanduser(self.cfg["photos_dir"])))

        def scan():
            try:
                d.mkdir(parents=True, exist_ok=True)
                return sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXT)
            except Exception:
                return []

        files = await self._io(scan)
        self.photos = files
        v = hashlib.sha1("|".join(f"{p.name}:{p.stat().st_size}" for p in files).encode()).hexdigest()[:10]
        await self.hub.send("photos", {"n": len(files), "v": v, "dir": str(d)})

    # ---------------- adb
    async def tick_adb(self):
        port = str(self.cfg["port"])
        proc = await asyncio.create_subprocess_exec(
            "adb", "reverse", f"tcp:{port}", f"tcp:{port}",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            creationflags=0x08000000 if IS_WIN else 0)
        ok = (await proc.wait()) == 0
        if ok != self.adb_ok:
            self.adb_ok = ok
            if ok:
                log.info("USB phone connected - open http://localhost:%s/?k=%s on it", port, self.cfg["token"])

    # ---------------- HTTP / WS
    def authed(self, request) -> bool:
        return secrets.compare_digest(request.query.get("k", ""), self.cfg["token"])

    async def ws_handler(self, request):
        if not self.authed(request):
            return web.Response(status=403, text="bad token")
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=1 << 20)
        await ws.prepare(request)
        hello = {
            "t": "hello", "demo": self.demo, "fav": self.cfg.get("f1_favourite"), "ver": VERSION,
            "lyoff": float(self.cfg.get("lyrics_offset", 0.3) or 0),
            **self.tiles_payload(),
            "hook": {"key": self.cfg.get("hook_key"), "lan": self.lan_ip(), "port": self.cfg.get("port")},
            "forza": {"port": (self.cfg.get("forza") or {}).get("listen"),
                      "auto": (self.cfg.get("forza") or {}).get("auto_page", True)},
        }
        await ws.send_str(json.dumps(hello))
        for msg in list(self.hub.state.values()):
            await ws.send_str(json.dumps(msg, separators=(",", ":")))
        self.hub.clients.add(ws)
        log.info("Phone connected (%s)", request.remote)
        try:
            async for m in ws:
                if m.type == WSMsgType.TEXT:
                    try:
                        await self.act(json.loads(m.data), ws)
                    except Exception as e:
                        log.warning("action failed: %s", e)
                        await ws.send_str(json.dumps({"t": "toast", "msg": "That didn't work", "err": True}))
        finally:
            self.hub.clients.discard(ws)
            log.info("Phone disconnected")
        return ws

    async def act(self, m: dict, ws):
        a = m.get("a")
        P = self.plat
        if a == "media":
            await P.media_cmd(m.get("cmd"), m.get("v"))
            self.media_sent = None
            await asyncio.sleep(0.15)
            await self.tick_media()
        elif a == "vol":
            if "set" in m:
                await P.vol_set(float(m["set"]))
            elif m.get("mute"):
                await P.vol_mute()
            await self.push_volume()
        elif a == "outputs":
            await ws.send_str(json.dumps({"t": "outputs", "list": await P.outputs()}))
        elif a == "output":
            await P.output_set(str(m.get("id", "")))
            await asyncio.sleep(0.25)
            lst = await P.outputs()
            await ws.send_str(json.dumps({"t": "outputs", "list": lst}))
            await self.push_volume()
            cur = next((o["name"] for o in lst if o["on"]), None)
            if cur:
                await ws.send_str(json.dumps({"t": "toast", "msg": out_label(cur), "icon": "check"}))
        elif a == "tile":
            lst = self.cfg.get(m.get("list"), []) if m.get("list") in TILE_SLOTS else []
            i = int(m.get("i", -1))
            if 0 <= i < len(lst):
                await self.run_tile(lst[i], ws)
        elif a == "tile_save":
            await self.tile_save(m.get("list"), int(m.get("i", -1)), m.get("tile") or {})
        elif a == "tile_reset":
            await self.tile_save(m.get("list"), int(m.get("i", -1)), None)
        elif a == "startapps":
            try:
                lst = await P.start_apps()
            except Exception as e:
                log.info("start apps: %s", e)
                lst = []
            await ws.send_str(json.dumps({"t": "startapps", "list": lst}))
        elif a == "reveal":
            name = safe_filename(str(m.get("name", "")))
            p = self.drop_dir() / name
            if p.exists():
                await P.reveal(str(p))
        elif a == "procs":   # the Health page is open: keep sampling for a bit
            self._procs_on = time.monotonic() + 15
            if m.get("now"):
                try:
                    await ws.send_str(json.dumps({"t": "procs", "list": await P.procs()}))
                except Exception:
                    pass
        elif a == "kill":
            exes = [str(x) for x in (m.get("exe") or [])][:6]
            n = await P.kill(exes) if exes else 0
            name = app_nice(exes[0]) if exes else "app"
            await ws.send_str(json.dumps({"t": "toast", "msg": f"Ended {name}" if n else f"Couldn't end {name}",
                                          "icon": "xmark", "err": not n}))
            await asyncio.sleep(0.6)
            self._procs_on = time.monotonic() + 15
            await self.tick_procs()
        elif a == "focus":
            await self.focus_cmd(m)
        elif a == "note_open":
            if not await P.focus_named(str(m.get("app", ""))):
                await ws.send_str(json.dumps({"t": "toast", "msg": f"Couldn't find {m.get('app', 'that app')}", "icon": "xmark", "err": True}))
        elif a == "hook_toggle":
            hid = str(m.get("id", ""))
            act = (self.cfg.get("hook_actions") or {}).get(hid)
            cur = self.hooks.get(hid)
            if act and cur is not None:
                new = not bool(cur.get("value"))
                url = act.get("on" if new else "off") or act.get("toggle")
                if url:
                    try:
                        async with self.http.get(url, timeout=ClientTimeout(total=4)) as r:
                            ok = r.status < 400
                    except Exception:
                        ok = False
                    if ok:
                        cur["value"], cur["ts"] = new, time.time()
                        self._hooks_dirty = True
                    else:
                        await ws.send_str(json.dumps({"t": "toast", "msg": f"{cur.get('label', hid)} didn't answer", "icon": "xmark", "err": True}))
            await self.push_hooks()
        elif a == "call":
            call = (self._ctx_last or {}).get("call")
            ok = bool(call) and await P.call_action(call["key"], str(m.get("cmd")))
            if not ok:
                what = {"cam": "Camera", "hand": "Raise hand", "leave": "Leave"}.get(m.get("cmd"), "That")
                await ws.send_str(json.dumps({"t": "toast", "msg": f"{what} isn't available for {call['app'] if call else 'this call'}",
                                              "icon": "xmark", "err": True}))
        elif a == "radio":
            cmd = m.get("cmd")
            if cmd == "queue":
                try:
                    q = await self.radio_queue()
                except Exception as e:
                    log.debug("radio queue: %s", e)
                    q = {"tracks": [], "cursor": None}
                await ws.send_str(json.dumps({"t": "radioq", **q}, separators=(",", ":")))
            else:
                try:
                    await self.radio_cmd(cmd, m.get("v"))
                except Exception as e:
                    log.warning("radio %s failed: %s", cmd, e)
                    await ws.send_str(json.dumps({"t": "toast", "msg": "Universal Radio not responding", "err": True}))
                if cmd != "gain":
                    await asyncio.sleep(0.3)
                self._radio_sent_at = 0
                await self.tick_radio()
        elif a == "avol":
            await P.appv_set(float(m.get("set", 1)))
            self.media_sent = None
            await self.tick_media()
        elif a == "mic":
            await P.mic_toggle()
            await self.push_volume()
        elif a == "app":
            app = next((x for x in self.cfg.get("apps", []) if x.get("id") == m.get("id")), None)
            if app:
                res = await P.open_app(app)
                msg = f"Switched to {app['label']}" if res == "focused" else f"Opening {app['label']}"
                await ws.send_str(json.dumps({"t": "toast", "msg": msg, "icon": "check"}))
        elif a == "macro":
            mac = next((x for x in self.cfg.get("macros", []) if x.get("id") == m.get("id")), None)
            if mac:
                typ, val = mac.get("type", "keys"), mac.get("value", "")
                if typ == "keys":
                    await P.keys(val)
                elif typ == "text":
                    await P.text(val)
                elif typ == "run":
                    await P.launch(val)
        elif a == "sys":
            v = m.get("v")
            if v in ("gclip", "gshot"):
                tool = CAP_KEYS.get(self.cfg.get("capture_tool"), CAP_KEYS["gamebar"])
                await P.keys(tool["clip" if v == "gclip" else "shot"])
                asyncio.create_task(self._cap_watch(v))
            else:
                await P.sys_action(v)
        elif a == "caps":
            items = await self._io(self._scan_caps)
            await ws.send_str(json.dumps({"t": "caps", "list": items, "tool": self.cfg.get("capture_tool", "gamebar"),
                                          "dirs": [str(d) for d in self.cap_dirs() if d.is_dir()]}))
        elif a == "captool":
            tool = m.get("tool") if m.get("tool") in CAP_KEYS else "gamebar"
            self.cfg["capture_tool"] = tool
            await self._io(self._persist_cfg_key, "capture_tool", tool)
        elif a == "dvoice":
            if self.discord:
                await self.discord.action(m.get("cmd"))
        elif a == "discord_setup":
            cid, sec = str(m.get("id") or "").strip(), str(m.get("secret") or "").strip()
            if not re.fullmatch(r"\d{15,22}", cid) or len(sec) < 16:
                await ws.send_str(json.dumps({"t": "toast", "msg": "Check the Client ID and Secret", "err": True}))
                return
            self.cfg["discord"] = {"client_id": cid, "client_secret": sec}
            await self._io(self._persist_cfg_key, "discord", self.cfg["discord"])
            await ws.send_str(json.dumps({"t": "toast", "msg": "Now tap Authorize in Discord on your PC", "icon": "check"}))
        elif a == "mode":
            await P.mode_set(m.get("v"))
            await asyncio.sleep(0.3)
            await self.tick_laptop()
        elif a == "forza":
            msg = await P.forza(m.get("v"))
            if msg:
                await ws.send_str(json.dumps({"t": "toast", "msg": msg, "icon": "car"}))
            await asyncio.sleep(1.5)
            await self.hub.send("fzapp", {"running": await P.forza_running()})
        elif a == "carname":
            await self._io(self.save_car_name, int(m.get("ord", 0)), str(m.get("name", "")))
            await ws.send_str(json.dumps({"t": "toast", "msg": "Car saved", "icon": "check"}))
        elif a == "clip_get":
            text = await P.clip_get()
            await ws.send_str(json.dumps({"t": "clip", "text": (text or "")[:20000]}))
        elif a == "clip_set":
            await P.clip_set(str(m.get("text", ""))[:100000])
            if m.get("paste"):
                await asyncio.sleep(0.1)
                await P.keys("ctrl+v")
            await ws.send_str(json.dumps({"t": "toast", "msg": "Sent to PC", "icon": "check"}))

    async def art_handler(self, request):
        item = self.art.get(request.match_info["h"])
        if not item:
            raise web.HTTPNotFound()
        return web.Response(body=item[0], content_type=item[1],
                            headers={"Cache-Control": "public, max-age=86400"})

    async def photo_handler(self, request):
        if not self.authed(request):
            raise web.HTTPForbidden()
        try:
            p = self.photos[int(request.match_info["i"])]
        except (ValueError, IndexError):
            raise web.HTTPNotFound()
        return web.FileResponse(p, headers={"Cache-Control": "public, max-age=3600"})


# --------------------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------------------

MANIFEST = {
    "name": "DeskDeck", "short_name": "DeskDeck", "start_url": "/", "scope": "/",
    "display": "fullscreen", "orientation": "landscape", "background_color": "#000000",
    "theme_color": "#000000",
    "icons": [{"src": "/s/icon-192.png", "sizes": "192x192", "type": "image/png"},
              {"src": "/s/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}],
}


def build_app(engine: Engine) -> web.Application:
    app = web.Application()

    async def index(request):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        if engine.authed(request):
            # iOS gives Home Screen web apps their own storage, so the start URL itself must carry the key
            k = engine.cfg["token"]
            html = html.replace('href="/manifest.webmanifest"', f'href="/manifest.webmanifest?k={k}"')
        return web.Response(text=html, content_type="text/html", headers={"Cache-Control": "no-cache"})

    async def manifest(request):
        m = dict(MANIFEST)
        if engine.authed(request):
            m["start_url"] = f"/?k={engine.cfg['token']}"
        return web.json_response(m, content_type="application/manifest+json", headers={"Cache-Control": "no-cache"})

    @web.middleware
    async def nocache(request, handler):
        resp = await handler(request)
        if request.path.startswith("/s/") and not request.path.startswith("/s/fonts/"):
            resp.headers["Cache-Control"] = "no-cache"
        return resp

    app.middlewares.append(nocache)
    app.router.add_get("/", index)
    app.router.add_get("/ws", engine.ws_handler)
    app.router.add_get("/art/{h}", engine.art_handler)
    app.router.add_get("/rart/{h}", engine.rart_handler)
    app.router.add_get("/yt/{vid}", engine.yt_thumb_handler)
    app.router.add_get("/ca.crt", engine.ca_handler)
    app.router.add_get("/setup", engine.setup_handler)
    for path, h in (("/hook/value", engine.hook_value), ("/hook/notify", engine.hook_notify),
                    ("/hook/page", engine.hook_page), ("/hook/clear", engine.hook_clear), ("/api/do", engine.do_handler)):
        app.router.add_route("GET", path, h)
        app.router.add_route("POST", path, h)
    app.router.add_get("/photo/{i}", engine.photo_handler)
    app.router.add_post("/api/upload", engine.upload_handler)
    app.router.add_get("/cap/{id}", engine.cap_handler)
    app.router.add_get("/capthumb/{id}", engine.capthumb_handler)
    app.router.add_get("/manifest.webmanifest", manifest)
    app.router.add_static("/s/", WEB, show_index=False)
    app.on_startup.append(engine.start)
    app.on_cleanup.append(engine.stop)
    return app


def banner(cfg, demo):
    port, tok = cfg["port"], cfg["token"]
    lan = f"http://{lan_ip()}:{port}/?k={tok}"
    usb = f"http://localhost:{port}/?k={tok}"
    print()
    print(f"  DeskDeck {VERSION}" + ("  (demo mode)" if demo else ""))
    print("  " + "-" * 52)
    print(f"  Wi-Fi :  {lan}")
    print(f"  USB   :  {usb}")
    if cfg.get("adb_reverse"):
        print("           " + ("adb found - USB link is automatic" if shutil.which("adb")
                               else "install adb (platform-tools) for the USB link"))
    print("  " + "-" * 52)
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(lan)
        qr.print_ascii(invert=True)
    except Exception:
        pass
    print("  Ctrl+C to stop\n")


def main():
    ap = argparse.ArgumentParser(description="DeskDeck PC agent")
    ap.add_argument("--demo", action="store_true", help="fake data, runs on any OS")
    ap.add_argument("--demo-forza", action="store_true", help="fake Forza telemetry")
    ap.add_argument("--demo-game", action="store_true", help="pretend a game is running (Gaming page)")
    ap.add_argument("--demo-f1", action="store_true", help="pretend an F1 race is live (F1 page)")
    ap.add_argument("--port", type=int)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="  %(asctime)s  %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    cfg = load_config()
    if args.port:
        cfg["port"] = args.port
    demo = args.demo
    if not demo and not IS_WIN:
        print("! Real mode needs Windows - starting in demo mode.")
        demo = True
    if args.demo_f1:
        cfg["_demo_f1"] = True
    engine = Engine(cfg, demo, args.demo_forza, args.demo_game)
    banner(cfg, demo)
    try:
        asyncio.run(serve(engine, cfg))
    except KeyboardInterrupt:
        pass


async def serve(engine, cfg):
    runner = web.AppRunner(build_app(engine), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, cfg["host"], cfg["port"]).start()
    hp = int(cfg.get("https_port") or 0)
    if hp:
        try:
            ip = lan_ip()
            paths = await asyncio.get_running_loop().run_in_executor(None, ensure_certs, [ip])
            if paths:
                import ssl
                ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                ctx.load_cert_chain(*map(str, paths))
                engine.ssl_ctx, engine._cert_ip = ctx, ip
                await web.TCPSite(runner, cfg["host"], hp, ssl_context=ctx).start()
                print(f"  iPad  :  https://{ip}:{hp}/?k={cfg['token']}")
                print(f"           first time: open http://{ip}:{cfg['port']}/setup?k={cfg['token']} on the iPad\n")
            else:
                log.info("HTTPS off - run: pip install cryptography")
        except Exception as e:
            log.warning("HTTPS not started: %s", e)
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    main()
