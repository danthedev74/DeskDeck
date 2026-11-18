"""DeskDeck tray launcher: runs agent.py hidden, with a system-tray menu."""
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "deskdeck.log"
NOWIN = 0x08000000

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_mutex = _k32.CreateMutexW(None, False, "DeskDeckTrayMutex")
if ctypes.get_last_error() == 183:  # already running
    sys.exit(0)

import psutil
import pystray
from PIL import Image

EXE = Path(sys.executable)
PY = EXE.with_name("python.exe") if EXE.name.lower() == "pythonw.exe" else EXE
PYW = EXE.with_name("pythonw.exe")
STARTUP = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "DeskDeck.lnk"


def kill_old_agents():
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            cl = " ".join(p.info["cmdline"] or [])
            if "agent.py" in cl and p.info["pid"] != os.getpid():
                p.kill()
        except Exception:
            pass


class Agent:
    def __init__(self):
        self.p = None
        self.want = False
        self.fails = 0
        self.started = 0.0

    def start(self):
        self.stop()
        log = open(LOG, "w", encoding="utf-8", errors="replace")
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        self.p = subprocess.Popen([str(PY), "-u", str(ROOT / "agent.py")], cwd=str(ROOT), env=env,
                                  stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  creationflags=NOWIN)
        self.started = time.time()
        self.want = True

    def stop(self):
        self.want = False
        p, self.p = self.p, None
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(5)
            except Exception:
                p.kill()

    def watch(self, icon):
        while True:
            time.sleep(3)
            p = self.p
            if self.want and p is not None and p.poll() is not None:
                quick = time.time() - self.started < 20
                self.fails = self.fails + 1 if quick else 0
                if self.fails >= 3:
                    self.want = False
                    icon.notify("DeskDeck keeps stopping. Open 'View log' from the tray menu.", "DeskDeck")
                    continue
                self.start()


def cfg():
    try:
        return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def phone_link():
    c = cfg()
    return f"http://localhost:{c.get('port', 8765)}/?k={c.get('token', '')}"


def lan_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def ipad_link():
    c = cfg()
    hp = c.get("https_port", 8766) or 0
    if hp:
        return f"https://{lan_ip()}:{hp}/?k={c.get('token', '')}"
    return f"http://{lan_ip()}:{c.get('port', 8765)}/?k={c.get('token', '')}"


def setup_link():
    c = cfg()
    return f"http://{lan_ip()}:{c.get('port', 8765)}/setup?k={c.get('token', '')}"


def _copy(icon, text, what):
    subprocess.run("clip", input=text.encode(), shell=True, creationflags=NOWIN)
    icon.notify(f"{what} copied to clipboard", "DeskDeck")


agent = Agent()


def on_open(icon, item):
    webbrowser.open(phone_link())


def on_copy(icon, item):
    _copy(icon, phone_link(), "Phone link")


def on_copy_ipad(icon, item):
    _copy(icon, ipad_link(), "iPad link (Wi-Fi)")


def on_copy_setup(icon, item):
    _copy(icon, setup_link(), "iPad setup link")


def on_restart(icon, item):
    agent.fails = 0
    agent.start()
    icon.notify("Restarted", "DeskDeck")


def on_folder(icon, item):
    os.startfile(str(ROOT))


def on_log(icon, item):
    if LOG.exists():
        os.startfile(str(LOG))


def is_startup(item):
    return STARTUP.exists()


def on_startup(icon, item):
    if STARTUP.exists():
        STARTUP.unlink()
        return
    import win32com.client
    s = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(STARTUP))
    s.TargetPath = str(PYW)
    s.Arguments = f'"{ROOT / "tray.pyw"}"'
    s.WorkingDirectory = str(ROOT)
    s.IconLocation = str(ROOT / "deskdeck.ico")
    s.Save()


# ---------------- updates from GitHub releases
KEEP = {"config.json", "cars.json", "hooks.json", "focus.json", "fh6_cars.cache.json", "deskdeck.log", "deskdeck.ico"}
KEEP_DIRS = {"certs", "__pycache__", ".git"}


def local_version():
    try:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return "0"


def _vt(v):
    return tuple(int(x) for x in __import__("re").findall(r"\d+", v or "0")[:3]) or (0,)


def check_update(icon, quiet=False):
    import shutil
    import tempfile
    import urllib.request
    import zipfile
    repo = (cfg().get("update_repo") or "").strip()
    if not repo:  # only ever install from a repo you named yourself
        if not quiet:
            icon.notify('Set "update_repo" in config.json (e.g. "yourname/deskdeck") to get updates.', "DeskDeck")
        return
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "DeskDeck"})
        rel = json.loads(urllib.request.urlopen(req, timeout=15).read().decode())
    except Exception as e:
        if not quiet:
            icon.notify(f"Couldn't check for updates ({repo}): {e}", "DeskDeck")
        return
    tag = rel.get("tag_name") or ""
    if _vt(tag) <= _vt(local_version()):
        if not quiet:
            icon.notify(f"You're up to date ({local_version()})", "DeskDeck")
        return
    asset = next((a.get("browser_download_url") for a in rel.get("assets") or [] if a.get("name", "").lower().endswith(".zip")), None)
    url = asset or rel.get("zipball_url")
    icon.notify(f"Updating to {tag}...", "DeskDeck")
    tmp = Path(tempfile.mkdtemp(prefix="deskdeck-up-"))
    try:
        zp = tmp / "u.zip"
        req = urllib.request.Request(url, headers={"User-Agent": "DeskDeck"})
        zp.write_bytes(urllib.request.urlopen(req, timeout=120).read())
        with zipfile.ZipFile(zp) as z:
            for n in z.namelist():  # refuse anything that would land outside the temp folder
                if n.startswith("/") or ".." in Path(n).parts:
                    raise RuntimeError("bad archive")
            z.extractall(tmp / "x")
        src = next((p.parent for p in (tmp / "x").rglob("agent.py")), None)
        if src is None:
            raise RuntimeError("no agent.py in the release")
        agent.stop()
        for f in src.rglob("*"):
            rel_p = f.relative_to(src)
            if rel_p.parts[0] in KEEP_DIRS or (len(rel_p.parts) == 1 and rel_p.name in KEEP):
                continue
            dst = ROOT / rel_p
            if f.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)
        subprocess.run([str(PY), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "-r",
                        str(ROOT / "requirements.txt")], cwd=str(ROOT), creationflags=NOWIN, timeout=600)
        agent.fails = 0
        agent.start()
        icon.notify(f"Updated to {tag}. If the tray menu looks old, quit and reopen DeskDeck.", "DeskDeck")
    except Exception as e:
        icon.notify(f"Update failed: {e}", "DeskDeck")
        if not agent.want:
            agent.start()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def on_update(icon, item):
    threading.Thread(target=check_update, args=(icon,), daemon=True).start()


def auto_update(icon):
    time.sleep(90)
    while True:
        if cfg().get("update_repo") and cfg().get("auto_update", True):
            check_update(icon, quiet=True)
        time.sleep(24 * 3600)


def on_quit(icon, item):
    agent.stop()
    icon.stop()


def setup(icon):
    icon.visible = True
    icon.notify("Running in the background. Right-click the tray icon for options.", "DeskDeck")


def main():
    kill_old_agents()
    agent.start()
    menu = pystray.Menu(
        pystray.MenuItem("DeskDeck is running", lambda: None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open on this PC", on_open, default=True),
        pystray.MenuItem("Copy phone link (USB)", on_copy),
        pystray.MenuItem("Copy iPad link (Wi-Fi)", on_copy_ipad),
        pystray.MenuItem("Copy iPad setup link", on_copy_setup),
        pystray.MenuItem("Restart", on_restart),
        pystray.MenuItem("Check for updates", on_update),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Start with Windows", on_startup, checked=is_startup),
        pystray.MenuItem("Open folder", on_folder),
        pystray.MenuItem("View log", on_log),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit DeskDeck", on_quit),
    )
    icon = pystray.Icon("DeskDeck", Image.open(ROOT / "web" / "icon-192.png"), "DeskDeck", menu)
    threading.Thread(target=agent.watch, args=(icon,), daemon=True).start()
    threading.Thread(target=auto_update, args=(icon,), daemon=True).start()
    icon.run(setup)


main()
