"""
Colossal Macro - grind macro for Attack on Titan Revolution (Roblox).

Routines (pick one in the app):
    Blood Awakening  ability 2 -> (look up) -> dash -> strafe left -> shift (ability 5) -> shifted ability 4 -> ability 5 loop
    Shiki            ability 2 -> (look up) -> dash -> strafe -> ability 3 -> buy time until ability 4 -> ability 4 -> shift ...
    Universal        ability 2 -> (look up) -> dash -> strafe -> ability 3 -> look down -> ability 4 -> shift ...
    Female Raid      skip cutscenes, buffs, shift, ability cycle, heatwave, open the chests, finish
Every mission / raid ends with the retry button: the macro reads the result + loot, clicks retry and goes again.

Extras: loot + win/loss counters, Discord webhook / bot (with !commands), auto-reconnect, stuck-mission failsafe.
Hotkeys (changeable): F8 start, F6 pause / resume, F7 stop.  Settings: Documents\\Colossal Macro\\config.json
"""

import ctypes
import datetime
import io
import json
import math
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from ctypes import wintypes

import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageGrab, ImageTk

import build_optimiser as bo

APP_NAME = "Colossal Macro"
VERSION = "1.2 (beta)"
ROBLOX_PLACE_ID = 13379208636  # Attack on Titan Revolution


# =============================================================================
#  Windows basics: DPI awareness, folders
# =============================================================================

def _make_dpi_aware():
    # Physical pixels everywhere: screenshots, clicks and the Tk windows all agree.
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


_make_dpi_aware()
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ColossalMacro.App")
except Exception:
    pass


def resource_path(*parts):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def documents_dir():
    buf = ctypes.create_unicode_buffer(260)
    try:
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
            return buf.value
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Documents")


DATA_DIR = os.path.join(documents_dir(), APP_NAME)
PICTURES_DIR = os.path.join(DATA_DIR, "pictures")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
LOG_PATH = os.path.join(DATA_DIR, "last_session_log.txt")
GUIDE_FILE = "HOW TO USE.txt"
FEEDBACK_REPO = "arvz12/colossal-macro"  # Feedback opens a filled-in issue here (GitHub emails the owner)
# GitHub keeps a filled-in issue link through its sign-in page only while the link, encoded once more for the
# login page, stays under about 7600 characters (tested Nov 2026); 6800 leaves room. The log is cut to fit.
FEEDBACK_URL_MAX = 6800
DISCORD_INVITE = "https://discord.gg/j2C5R3QBXk"  # the official Colossal Macro server (permanent invite)


# =============================================================================
#  Keyboard / mouse input (SendInput with scan codes - what Roblox listens to)
# =============================================================================

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ULONG_PTR = ctypes.c_size_t

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                                     ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
user32.SetCursorPos.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
user32.GetCursorPos.restype = wintypes.BOOL
user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
user32.FindWindowW.restype = wintypes.HWND
user32.GetForegroundWindow.argtypes = ()
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.IsIconic.argtypes = (wintypes.HWND,)
user32.IsIconic.restype = wintypes.BOOL
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.ShowWindow.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.GetWindowRect.restype = wintypes.BOOL
user32.EnumDisplayMonitors.argtypes = (wintypes.HDC, ctypes.POINTER(wintypes.RECT), MONITORENUMPROC, wintypes.LPARAM)
user32.EnumDisplayMonitors.restype = wintypes.BOOL
user32.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.POINTER(MONITORINFO))
user32.GetMonitorInfoW.restype = wintypes.BOOL
user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

# Key names used everywhere in the app (and in config.json) -> Windows virtual-key codes.
VK = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "backspace": 0x08, "capslock": 0x14,
    "ctrl": 0xA2, "rctrl": 0xA3, "shift": 0xA0, "rshift": 0xA1, "alt": 0xA4, "ralt": 0xA5,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC, ";": 0xBA, "'": 0xDE,
    ",": 0xBC, ".": 0xBE, "/": 0xBF,
}
for _c in "abcdefghijklmnopqrstuvwxyz0123456789":
    VK[_c] = ord(_c.upper())
for _i in range(1, 25):
    VK["f%d" % _i] = 0x6F + _i
for _i in range(10):
    VK["num%d" % _i] = 0x60 + _i
EXTENDED_VK = {0x26, 0x28, 0x25, 0x27, 0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22, 0xA3, 0xA5}


def key_display(name):
    if not name:
        return "-"
    special = {"space": "Space", "ctrl": "Ctrl", "rctrl": "Right Ctrl", "shift": "Shift",
               "rshift": "Right Shift", "alt": "Alt", "ralt": "Right Alt", "enter": "Enter",
               "esc": "Esc", "tab": "Tab", "backspace": "Backspace", "capslock": "Caps Lock",
               "pageup": "Page Up", "pagedown": "Page Down"}
    if name in special:
        return special[name]
    if name.startswith("num"):
        return "Num " + name[3:]
    return name.upper() if len(name) <= 3 else name.capitalize()


def _send(inputs):
    arr = (INPUT * len(inputs))(*inputs)
    return user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def key_event(name, up):
    vk = VK.get(name)
    if vk is None:
        raise ValueError("unknown key '%s'" % name)
    scan = user32.MapVirtualKeyW(vk, 0) & 0xFF
    flags = KEYEVENTF_SCANCODE
    if up:
        flags |= KEYEVENTF_KEYUP
    if vk in EXTENDED_VK:
        flags |= KEYEVENTF_EXTENDEDKEY
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = KEYBDINPUT(0, scan, flags, 0, 0)
    return _send([inp])


def mouse_move_rel(dx, dy):
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.mi = MOUSEINPUT(int(dx), int(dy), 0, MOUSEEVENTF_MOVE, 0, 0)
    _send([inp])


def mouse_button(down):
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP, 0, 0)
    _send([inp])


def mouse_click():
    mouse_button(True)
    time.sleep(0.02)
    mouse_button(False)


MOUSEEVENTF_WHEEL = 0x0800


def mouse_wheel(notches):
    """Scroll the wheel: notches > 0 up, < 0 down (where the cursor is)."""
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.mi = MOUSEINPUT(0, 0, ctypes.c_uint32(int(notches) * 120).value, MOUSEEVENTF_WHEEL, 0, 0)
    _send([inp])


def cursor_pos():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def key_is_down(name):
    vk = VK.get(name)
    return bool(vk) and bool(user32.GetAsyncKeyState(vk) & 0x8000)


def window_pid(hwnd):
    if not hwnd:
        return 0
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def roblox_window():
    return user32.FindWindowW(None, "Roblox")


def roblox_rect():
    """(left, top, right, bottom) of the Roblox window, or None."""
    hwnd = roblox_window()
    if not hwnd or user32.IsIconic(hwnd):
        return None
    r = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)) or r.right - r.left < 50 or r.bottom - r.top < 50:
        return None
    return r.left, r.top, r.right, r.bottom


def focus_roblox():
    """Bring the Roblox window to the front. Returns True / False, or None when there is none."""
    hwnd = roblox_window()
    if not hwnd:
        return None
    if user32.GetForegroundWindow() == hwnd:
        return True
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    # Windows only lets the app that got the last input switch windows: a quick Alt tap fixes that.
    key_event("alt", False)
    key_event("alt", True)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.2)
    return user32.GetForegroundWindow() == hwnd


CREATE_NO_WINDOW = 0x08000000


def close_roblox():
    """Force-close Roblox: the process that owns the Roblox window, plus any RobloxPlayerBeta.exe."""
    pid = window_pid(roblox_window())
    cmds = []
    if pid:
        cmds.append(["taskkill", "/F", "/PID", str(pid)])
    cmds.append(["taskkill", "/F", "/IM", "RobloxPlayerBeta.exe"])
    for cmd in cmds:
        try:
            subprocess.run(cmd, capture_output=True, timeout=10, creationflags=CREATE_NO_WINDOW)
        except Exception:
            pass


def launch_roblox_game():
    os.startfile("roblox://placeId=%d" % ROBLOX_PLACE_ID)


# =============================================================================
#  Screens
# =============================================================================

def list_monitors():
    mons = []

    def callback(hmon, hdc, lprect, lparam):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r = info.rcMonitor
            mons.append({"left": r.left, "top": r.top, "width": r.right - r.left,
                         "height": r.bottom - r.top, "primary": bool(info.dwFlags & 1)})
        return True

    try:
        user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(callback), 0)
    except Exception:
        mons = []
    if not mons:
        mons = [{"left": 0, "top": 0, "width": user32.GetSystemMetrics(0),
                 "height": user32.GetSystemMetrics(1), "primary": True}]
    mons.sort(key=lambda m: (not m["primary"], m["left"], m["top"]))
    return mons


def pick_monitor(cfg):
    mons = list_monitors()
    idx = cfg["app"].get("monitor", 0)
    return mons[idx] if 0 <= idx < len(mons) else mons[0]


def roblox_client_rect():
    """(left, top, right, bottom) of the inside of the Roblox window (no title bar / borders), or None."""
    hwnd = roblox_window()
    if not hwnd or user32.IsIconic(hwnd):
        return None
    r = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(r)):
        return None
    pt = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
        return None
    if r.right < 200 or r.bottom < 200:
        return None
    return pt.x, pt.y, pt.x + r.right, pt.y + r.bottom


def game_region(mon):
    """The part of `mon` to watch: the Roblox window when it's windowed on that monitor, else the whole monitor.
    Pictures keep the monitor's scale (the game's buttons don't simply shrink with the window - their sizes are
    learned instead)."""
    rect = roblox_client_rect()
    if rect:
        x0, y0 = max(rect[0], mon["left"]), max(rect[1], mon["top"])
        x1, y1 = min(rect[2], mon["left"] + mon["width"]), min(rect[3], mon["top"] + mon["height"])
        w, h = x1 - x0, y1 - y0
        if w >= 200 and h >= 200 and w * h < 0.97 * mon["width"] * mon["height"]:
            return {"left": x0, "top": y0, "width": w, "height": h, "primary": mon.get("primary", False),
                    "mon_height": mon["height"], "windowed": True}
    return mon


def monitor_label(i, m):
    return "Screen %d - %dx%d%s" % (i + 1, m["width"], m["height"], " (main)" if m["primary"] else "")


def grab_monitor(mon):
    """A PIL RGB screenshot of one monitor, native resolution (used by Capture and Discord screenshots)."""
    bbox = (mon["left"], mon["top"], mon["left"] + mon["width"], mon["top"] + mon["height"])
    on_main = mon["primary"] and mon["left"] == 0 and mon["top"] == 0
    return ImageGrab.grab(bbox=bbox, all_screens=not on_main)


def screenshot_png(mon, max_side=1280):
    """PNG bytes of the Roblox window (or the whole monitor when Roblox can't be found)."""
    rect = roblox_rect()
    img = ImageGrab.grab(bbox=rect, all_screens=True) if rect else grab_monitor(mon)
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def png_from_raw(raw, mon, max_side=1280):
    """PNG bytes of a screenshot already taken (BGRA, one monitor), cut to the Roblox window when it's on it."""
    img = raw[:, :, :3]
    rect = roblox_rect()
    if rect:
        x0, y0 = max(0, rect[0] - mon["left"]), max(0, rect[1] - mon["top"])
        x1, y1 = min(img.shape[1], rect[2] - mon["left"]), min(img.shape[0], rect[3] - mon["top"])
        if x1 - x0 >= 50 and y1 - y0 >= 50:
            img = img[y0:y1, x0:x1]
    h, w = img.shape[:2]
    f = min(1.0, float(max_side) / max(h, w))
    if f < 1.0:
        img = cv2.resize(img, (max(1, int(w * f)), max(1, int(h * f))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", np.ascontiguousarray(img))
    return buf.tobytes() if ok else None


# =============================================================================
#  Run log (runs.csv) and the stats report picture
# =============================================================================

RUN_LOG_HEADER = "time,routine,seconds,result,loot,failsafe,steps\n"
RUN_LOG_KEEP_DAYS = 14


def run_log_path():
    return os.path.join(DATA_DIR, "runs.csv")


def end_screen_path():
    return os.path.join(DATA_DIR, "last_end_screen.png")


def steps_text(steps):
    return "|".join("%s:%.2f" % (n, d) for n, d in (steps or []) if ":" not in n and "|" not in n and "," not in n)


def append_run_log(t, routine, seconds, result, loot, rescued, steps=None):
    """One line per finished run (also handy in Excel)."""
    path = run_log_path()
    line = "%d,%s,%.2f,%s,%s,%d,%s\n" % (int(t), routine, seconds or 0.0, result or "", "+".join(loot),
                                         1 if rescued else 0, steps_text(steps))
    os.makedirs(DATA_DIR, exist_ok=True)
    new = not os.path.isfile(path)
    with open(path, "a", encoding="utf-8") as fh:
        if new:
            fh.write(RUN_LOG_HEADER)
        fh.write(line)


def read_run_log(since=0.0, routine=None):
    """Finished runs from runs.csv as dicts (newest last), from `since` on, for one routine or all."""
    out = []
    try:
        with open(run_log_path(), "r", encoding="utf-8") as fh:
            for line in fh:
                p = line.rstrip("\n").split(",")
                if len(p) not in (6, 7) or p[0] == "time":
                    continue
                try:
                    t = float(p[0])
                    sec = float(p[2])
                except ValueError:
                    continue
                if t < since or (routine and p[1] != routine):
                    continue
                steps = []
                for part in (p[6].split("|") if len(p) == 7 and p[6] else []):
                    name, _, dur = part.rpartition(":")
                    try:
                        steps.append((name, float(dur)))
                    except ValueError:
                        pass
                out.append({"t": t, "routine": p[1], "seconds": sec, "result": p[3] or None,
                            "loot": [k for k in p[4].split("+") if k in LOOT_KINDS], "rescued": p[5] == "1",
                            "steps": steps})
    except OSError:
        pass
    return out


def trim_run_log(max_bytes=1500000):
    """Keep runs.csv small: when it gets big, drop runs older than RUN_LOG_KEEP_DAYS."""
    path = run_log_path()
    try:
        if os.path.getsize(path) <= max_bytes:
            return
        keep = read_run_log(time.time() - RUN_LOG_KEEP_DAYS * 86400)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(RUN_LOG_HEADER)
            for r in keep:
                fh.write("%d,%s,%.2f,%s,%s,%d,%s\n" % (int(r["t"]), r["routine"], r["seconds"], r["result"] or "",
                                                      "+".join(r["loot"]), 1 if r["rescued"] else 0,
                                                      steps_text(r.get("steps"))))
        os.replace(tmp, path)
    except OSError:
        pass


def good_run(r):
    """A run whose time means something (not rescued by the failsafe, not failed)."""
    return r["seconds"] > 0 and not r["rescued"] and r["result"] != "failed"


def run_hours(runs, now, max_hours=24):
    """Clock-hour buckets from the first hour with a run (at most `max_hours` back) up to the current hour."""
    cur = datetime.datetime.fromtimestamp(now).replace(minute=0, second=0, microsecond=0)
    first = cur - datetime.timedelta(hours=max_hours - 1)
    starts = [datetime.datetime.fromtimestamp(r["t"]).replace(minute=0, second=0, microsecond=0) for r in runs]
    starts = [s for s in starts if s >= first]
    if not starts:
        return []
    h = min(starts)
    buckets, index = [], {}
    while h <= cur:
        index[h] = len(buckets)
        buckets.append({"start": h, "partial": h == cur, "completed": 0, "failed": 0, "unknown": 0, "done": 0,
                        "times": [], "main": 0, "fragments": 0, "serums": 0, "time": 0.0})
        h += datetime.timedelta(hours=1)
    for r, s in zip(runs, [datetime.datetime.fromtimestamp(r["t"]).replace(minute=0, second=0, microsecond=0)
                           for r in runs]):
        b = buckets[index[s]] if s in index else None
        if b is None:
            continue
        b["done"] += 1
        b[r["result"] if r["result"] in ("completed", "failed") else "unknown"] += 1
        if good_run(r):
            b["times"].append(r["seconds"])
        for k in r["loot"]:
            if k in ("scroll", "vessel"):
                b["main"] += 1
            elif k in FRAGMENT_KINDS:
                b["fragments"] += 1
            elif k in SERUM_KINDS:
                b["serums"] += 1
    for b in buckets:
        b["time"] = sum(b["times"]) / len(b["times"]) if b["times"] else 0.0
    return buckets


# Chart colours (checked for colour-blind separation on the dark card): results use the status colours with the
# grey "not read" kept between them; loot uses three categorical hues; time is one series.
CH_BG, CH_CARD, CH_GRID = (11, 12, 16), (20, 22, 28), (38, 41, 50)
CH_TEXT, CH_MUTED, CH_DIM = (236, 238, 242), (140, 146, 160), (90, 97, 112)
CH_SERIES = {"completed": ("Completed", (12, 163, 12)), "unknown": ("Not read", (107, 113, 128)),
             "failed": ("Failed", (208, 59, 59)), "main": ("Scrolls", (57, 135, 229)),
             "fragments": ("Fragments", (217, 89, 38)), "serums": ("Serums", (25, 158, 112)),
             "time": ("Avg time", (144, 133, 233))}
_PIL_FONTS = {}


def pil_font(size, bold=False):
    key = (int(size), bold)
    f = _PIL_FONTS.get(key)
    if f is None:
        windir = os.environ.get("WINDIR", r"C:\Windows")
        try:
            f = ImageFont.truetype(os.path.join(windir, "Fonts", "seguisb.ttf" if bold else "segoeui.ttf"), int(size))
        except Exception:
            try:
                f = ImageFont.load_default(int(size))
            except Exception:
                f = ImageFont.load_default()
        _PIL_FONTS[key] = f
    return f


def nice_top(v, whole=False):
    """A round axis top at or above v (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8 x 10^n), so the bars use most of the height.
    `whole`: counts - the top and its half are whole numbers."""
    if v <= 0:
        return 2.0 if whole else 1.0
    mag = 10 ** math.floor(math.log10(v))
    for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12):
        top = m * mag
        if top >= v - 1e-9 and (not whole or (top >= 2 and abs(top / 2.0 - round(top / 2.0)) < 1e-9)):
            return top
    return 2.0 * math.ceil(v / 2.0)


def short_secs(v):
    v = int(round(v))
    return "%ds" % v if v < 100 else "%d:%02d" % (v // 60, v % 60)


def _mix(c, bg, t):
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c, bg))


def bar_chart(d, box, buckets, keys, title, ss, fmt, empty, bg=CH_CARD, whole=True):
    """Stacked bars per hour on ImageDraw `d` inside box (supersampled pixels): title, legend for 2+ series,
    recessive grid, rounded bar tops on the baseline, 2px gaps between stacked parts, a few direct labels."""
    x0, y0, x1, y1 = box
    d.text((x0, y0), title, font=pil_font(14 * ss, True), fill=CH_TEXT)
    ty = y0 + 26 * ss
    if len(keys) > 1:
        lf = pil_font(11 * ss)
        lx = x0
        for k in keys:
            name, col = CH_SERIES[k]
            d.rounded_rectangle((lx, ty + 4 * ss, lx + 10 * ss, ty + 14 * ss), radius=int(round(2 * ss)), fill=col)
            d.text((lx + 15 * ss, ty), name, font=lf, fill=CH_MUTED)
            lx += 15 * ss + d.textlength(name, font=lf) + 18 * ss
        ty += 22 * ss
    ptop, bottom = ty + 18 * ss, y1 - 20 * ss
    totals = [sum(b[k] for k in keys) for b in buckets]
    if not buckets or max(totals) <= 0:
        f = pil_font(12 * ss)
        d.text(((x0 + x1) / 2.0, (ptop + bottom) / 2.0), empty, font=f, fill=CH_DIM, anchor="mm")
        return
    tf = pil_font(10 * ss)
    top = nice_top(max(totals), whole)
    labels = [fmt(v) for v in (0, top / 2.0, top)]
    left = x0 + max(d.textlength(t, font=tf) for t in labels) + 10 * ss
    for i, v in enumerate((0, top / 2.0, top)):
        y = bottom - (bottom - ptop) * v / top
        d.line((left, y, x1, y), fill=CH_GRID if i else _mix(CH_GRID, CH_MUTED, 0.35), width=max(1, int(round(ss))))
        d.text((left - 8 * ss, y), labels[i], font=tf, fill=CH_DIM, anchor="rm")
    n = len(buckets)
    slot = (x1 - left) / float(n)
    bw = min(26 * ss, slot * 0.62)
    gap, r = 2 * ss, int(round(4 * ss))
    every = max(1, int(math.ceil(n / 8.0)))
    best = max(range(n), key=lambda i: totals[i])
    full = [i for i in range(n) if not buckets[i]["partial"] and totals[i] > 0]
    show = set(range(n)) if n <= 8 else {best} | ({full[-1]} if full else set())
    for i, b in enumerate(buckets):
        cx = left + slot * (i + 0.5)
        y = bottom
        parts = [(k, b[k]) for k in keys if b[k] > 0]
        for j, (k, v) in enumerate(parts):
            h = (bottom - ptop) * v / top
            col = CH_SERIES[k][1]
            if b["partial"]:
                col = _mix(col, bg, 0.45)
            ya, yb = y - h, y
            if j > 0:
                yb -= gap  # surface gap between stacked parts
            if yb - ya >= 1:
                if j == len(parts) - 1 and yb - ya > r:
                    d.rounded_rectangle((cx - bw / 2, ya, cx + bw / 2, yb), radius=r, fill=col)
                    d.rectangle((cx - bw / 2, yb - r, cx + bw / 2, yb), fill=col)
                else:
                    d.rectangle((cx - bw / 2, ya, cx + bw / 2, yb), fill=col)
            y -= h
        if i in show and totals[i] > 0:
            d.text((cx, y - 4 * ss), fmt(totals[i]), font=tf, fill=CH_TEXT if not b["partial"] else CH_MUTED, anchor="mb")
        if i % every == 0 or i == n - 1:
            txt = "now" if b["partial"] else b["start"].strftime("%H:00" if slot > 34 * ss else "%H")
            if i == n - 1 or i + every < n or n == 1:
                d.text((cx, bottom + 6 * ss), txt, font=tf, fill=CH_DIM, anchor="mt")


def line_chart(d, box, values, title, ss, fmt, empty):
    """Recent run times, oldest to newest: one 2px line, the average as a thin reference line, the best marked."""
    x0, y0, x1, y1 = box
    d.text((x0, y0), title, font=pil_font(14 * ss, True), fill=CH_TEXT)
    ptop, bottom = y0 + 46 * ss, y1 - 20 * ss
    if len(values) < 2:
        d.text(((x0 + x1) / 2.0, (ptop + bottom) / 2.0), empty, font=pil_font(12 * ss), fill=CH_DIM, anchor="mm")
        return
    lo, hi = min(values), max(values)
    span = max(hi - lo, 2.0)
    vmin, vmax = max(0.0, lo - span * 0.3), hi + span * 0.3
    tf = pil_font(10 * ss)
    ticks = (vmin, (vmin + vmax) / 2.0, vmax)
    left = x0 + max(d.textlength(fmt(v), font=tf) for v in ticks) + 10 * ss

    def ypos(v):
        return bottom - (bottom - ptop) * (v - vmin) / (vmax - vmin)
    for v in ticks:
        d.line((left, ypos(v), x1, ypos(v)), fill=CH_GRID, width=max(1, int(round(ss))))
        d.text((left - 8 * ss, ypos(v)), fmt(v), font=tf, fill=CH_DIM, anchor="rm")
    n = len(values)
    pts = [(left + (x1 - left) * i / float(n - 1), ypos(v)) for i, v in enumerate(values)]
    avg = sum(values) / n
    d.line((left, ypos(avg), x1, ypos(avg)), fill=_mix(CH_MUTED, CH_CARD, 0.35), width=max(1, int(round(ss))))
    # the average's value sits in the header (right), so it never covers the line
    d.text((x1, y0 + 4 * ss), "last %d runs  ·  avg %s (grey line)" % (n, fmt(avg)), font=tf, fill=CH_DIM,
           anchor="ra")
    col = CH_SERIES["time"][1]
    d.line(pts, fill=col, width=int(round(2 * ss)), joint="curve")
    bi = values.index(lo)
    bx, by = pts[bi]
    r = 4 * ss
    d.ellipse((bx - r - 2 * ss, by - r - 2 * ss, bx + r + 2 * ss, by + r + 2 * ss), fill=CH_CARD)
    d.ellipse((bx - r, by - r, bx + r, by + r), fill=col)
    d.text((bx, by + r + 5 * ss), "best " + fmt(lo), font=tf, fill=CH_TEXT, anchor="ma")
    d.text((left, bottom + 6 * ss), "older", font=tf, fill=CH_DIM, anchor="la")
    d.text((x1, bottom + 6 * ss), "latest", font=tf, fill=CH_DIM, anchor="ra")


def step_bars(d, box, runs, routine, ss, last=20):
    """Average time of each step over the last runs: where the time goes."""
    x0, y0, x1, y1 = box
    d.text((x0, y0), "Average time per step", font=pil_font(14 * ss, True), fill=CH_TEXT)
    sums = {}
    used = [r for r in runs if r.get("steps") and good_run(r)][-last:]
    for r in used:
        for name, dur in r["steps"]:
            sums.setdefault(name, []).append(dur)
    order = ["Start"] + ROUTINE_STEPS.get(routine, [])
    rows = [(n, sum(sums[n]) / len(sums[n])) for n in order if n in sums]
    rows += [(n, sum(v) / len(v)) for n, v in sums.items() if n not in order]
    top = y0 + 30 * ss
    if not rows:
        d.text(((x0 + x1) / 2.0, (top + y1) / 2.0), "Shows up after the next runs", font=pil_font(12 * ss),
               fill=CH_DIM, anchor="mm")
        return
    d.text((x1, y0 + 4 * ss), "last %d runs" % len(used), font=pil_font(10 * ss), fill=CH_DIM, anchor="ra")
    tf = pil_font(10 * ss)
    name_w = max(d.textlength(n, font=tf) for n, _ in rows) + 12 * ss
    val_w = d.textlength("00.0s", font=tf) + 8 * ss
    row_h = min(24 * ss, (y1 - top) / float(len(rows)))
    bh = max(4 * ss, min(10 * ss, row_h * 0.45))
    longest = max(v for _, v in rows) or 1.0
    col = CH_SERIES["time"][1]
    for i, (name, v) in enumerate(rows):
        cy = top + row_h * (i + 0.5)
        d.text((x0, cy), name, font=tf, fill=CH_MUTED, anchor="lm")
        w = max(bh, (x1 - val_w - x0 - name_w) * v / longest)
        c = col if v == longest else _mix(col, CH_CARD, 0.4)
        d.rounded_rectangle((x0 + name_w, cy - bh / 2, x0 + name_w + w, cy + bh / 2), radius=int(bh // 2), fill=c)
        d.text((x1, cy), "%.1fs" % v, font=tf, fill=CH_TEXT, anchor="rm")


def render_analytics(runs, routine, now, size, scale=1.0):
    """The Analytics page picture: missions / average time / loot per hour, recent run times and the average
    time of each step. Small sizes get the two-chart version."""
    if size[0] < 700 * scale or size[1] < 380 * scale:
        return render_report(runs, routine, now, size=size, compact=True, scale=scale)
    ss = 2
    W, H = int(size[0] * ss), int(size[1] * ss)
    k = scale * ss
    raid = routine == "Female Raid"
    word = "raids" if raid else "missions"
    CH_SERIES["main"] = ("Vessels" if raid else "Scrolls", CH_SERIES["main"][1])
    buckets = run_hours(runs, now)
    img = Image.new("RGB", (W, H), CH_CARD)
    d = ImageDraw.Draw(img)
    gx, gy = 34 * k, 30 * k
    mid = H * 0.5
    cw = (W - 2 * gx) / 3.0
    row1 = (["completed", "unknown", "failed"], "%s per hour" % word.capitalize(), lambda v: "%g" % v,
            "No %s yet" % word, True),            (["time"], "Average %s time" % word[:-1], short_secs, "No timed %s yet" % word, False),            (["main", "fragments", "serums"], "Loot per hour", lambda v: "%g" % v, "No loot read yet", True)
    for i, (keys, title, fmt, emp, whole) in enumerate(row1):
        bx = i * (cw + gx)
        bar_chart(d, (bx, 0, bx + cw, mid - gy / 2), buckets, keys, title, k, fmt, emp, whole=whole)
    times = [r["seconds"] for r in runs if good_run(r)][-40:]
    lw = (W - gx) * 0.56
    line_chart(d, (0, mid + gy / 2, lw, H), times, "Recent run times", k, short_secs,
               "Run times show up after 2 runs")
    step_bars(d, (lw + gx, mid + gy / 2, W, H), runs, routine, k)
    return img.resize((max(1, W // ss), max(1, H // ss)), Image.LANCZOS)


def report_numbers(runs, now):
    done = len(runs)
    comp = sum(1 for r in runs if r["result"] == "completed")
    fail = sum(1 for r in runs if r["result"] == "failed")
    times = [r["seconds"] for r in runs if good_run(r)]
    span_h = max(1.0, (now - min(r["t"] for r in runs)) / 3600.0) if runs else 1.0
    loot = {"main": 0, "fragments": 0, "serums": 0}
    for r in runs:
        for k in r["loot"]:
            loot["main" if k in ("scroll", "vessel") else "fragments" if k in FRAGMENT_KINDS else "serums"] += 1
    return {"done": done, "completed": comp, "failed": fail, "unknown": done - comp - fail,
            "rate": ("%d%%" % (100 * comp // (comp + fail))) if comp + fail else "-",
            "per_hour": "%.1f" % (done / span_h) if done else "-",
            "avg": fmt_run(sum(times) / len(times)) if times else "-", "best": fmt_run(min(times)) if times else "-",
            "rescued": sum(1 for r in runs if r["rescued"]), "loot": loot}


def render_report(runs, routine, now, session=None, size=(960, 840), compact=False, scale=1.0):
    """The stats picture: missions per hour, average mission time per hour, loot per hour and totals (or just the
    first two charts when `compact`). `runs` = the last 24 hours of one routine. Returns a PIL image."""
    ss = 2  # drawn at twice the size, then scaled down (smooth edges)
    W, H = int(size[0] * ss), int(size[1] * ss)
    k = scale * ss
    raid = routine == "Female Raid"
    word = "raids" if raid else "missions"
    CH_SERIES["main"] = ("Vessels" if raid else "Scrolls", CH_SERIES["main"][1])
    buckets = run_hours(runs, now)
    empty = "No %s in the last 24 hours yet" % word
    img = Image.new("RGB", (W, H), CH_CARD if compact else CH_BG)
    d = ImageDraw.Draw(img)
    if compact:
        pad = 4 * k
        if W >= 1.8 * H:  # wide and low (the main window's tab): side by side
            mid = W * 0.5
            box1, box2 = (pad, pad, mid - 12 * k, H - pad), (mid + 12 * k, pad, W - pad, H - pad)
        else:
            mid = H * 0.5
            box1, box2 = (pad, pad, W - pad, mid - 8 * k), (pad, mid + 8 * k, W - pad, H - pad)
        bar_chart(d, box1, buckets, ["completed", "unknown", "failed"], "%s per hour" % word.capitalize(), k,
                  lambda v: "%g" % v, empty if W < 1.8 * H else "No %s yet" % word)
        bar_chart(d, box2, buckets, ["time"], "Average %s time" % word[:-1], k, short_secs, "No timed %s yet" % word,
                  whole=False)
        return img.resize((max(1, W // ss), max(1, H // ss)), Image.LANCZOS)
    m = 20 * k
    d.text((m, m), "%s  \u00b7  %s" % (APP_NAME, routine), font=pil_font(19 * k, True), fill=CH_TEXT)
    d.text((W - m, m + 4 * k), "Last 24 hours  \u00b7  " + time.strftime("%Y-%m-%d %H:%M", time.localtime(now)),
           font=pil_font(12 * k), fill=CH_MUTED, anchor="ra")
    split = W * 0.69
    card_box = (m, 64 * k, split - 10 * k, H - m)
    d.rounded_rectangle(card_box, radius=int(14 * k), fill=CH_CARD)
    cx0, cy0, cx1, cy1 = card_box
    inner = (cx0 + 18 * k, cy0 + 16 * k, cx1 - 18 * k, cy1 - 12 * k)
    hgt = (inner[3] - inner[1]) / 3.0
    charts = ((["completed", "unknown", "failed"], "%s per hour" % word.capitalize(), lambda v: "%g" % v, empty),
              (["time"], "Average %s time (no failsafe / failed runs)" % word[:-1], short_secs, "No timed %s yet" % word),
              (["main", "fragments", "serums"], "Loot per hour", lambda v: "%g" % v, "No loot read yet"))
    for i, (keys, title, fmt, emp) in enumerate(charts):
        top = inner[1] + i * hgt
        bar_chart(d, (inner[0], top, inner[2], top + hgt - 14 * k), buckets, keys, title, k, fmt, emp,
                  whole=keys != ["time"])
    side = (split + 10 * k, 64 * k, W - m, H - m)
    d.rounded_rectangle(side, radius=int(14 * k), fill=CH_CARD)
    num = report_numbers(runs, now)
    sx0, sy, sx1 = side[0] + 18 * k, side[1] + 18 * k, side[2] - 18 * k
    lf, vf, hf = pil_font(12 * k), pil_font(13 * k, True), pil_font(10 * k, True)

    def head(text):
        nonlocal sy
        d.text((sx0, sy), text.upper(), font=hf, fill=CH_DIM)
        sy += 22 * k

    def row(name, value):
        nonlocal sy
        d.text((sx0, sy), name, font=lf, fill=CH_MUTED)
        d.text((sx1, sy), str(value), font=vf, fill=CH_TEXT, anchor="ra")
        sy += 25 * k

    head("Last 24 hours")
    row(word.capitalize(), num["done"])
    row("Completed", num["completed"])
    row("Failed", num["failed"])
    if num["unknown"]:
        row("Result not read", num["unknown"])
    row("Success rate", num["rate"])
    row("Per hour", num["per_hour"])
    row("Average time", num["avg"])
    row("Best time", num["best"])
    row("Failsafes", num["rescued"])
    sy += 10 * k
    head("Loot")
    row(CH_SERIES["main"][0], num["loot"]["main"])
    row("Fragments", num["loot"]["fragments"])
    row("Serums", num["loot"]["serums"])
    if session and session.get("start"):
        sy += 10 * k
        head("This session")
        row(word.capitalize(), session.get("retries", 0))
        row("Running for", fmt_dur(now - session["start"]))
    return img.resize((max(1, W // ss), max(1, H // ss)), Image.LANCZOS)


def report_png(routine, session=None, now=None):
    now = time.time() if now is None else now
    img = render_report(read_run_log(now - 24 * 3600, routine), routine, now, session)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# =============================================================================
#  Pictures the macro looks for (built-in ones are from a 1080p screen; others are scaled)
# =============================================================================

def _pic(label, group, files, threshold, how, mask=None):
    return {"label": label, "group": group, "files": files, "threshold": threshold, "how": how, "mask": mask}


_LOOT_HOW = "A loot icon on the end screen. Drag the box tightly around the icon."
PICTURES = {
    "start": _pic("Mission start icon", "Detection", {"normal": "mission_start.png", "low": "low/mission_start.png"}, 0.80,
                  "Your ability 2 icon (the yellow speedometer) on the skill bar, in a mission in human form. "
                  "A mission starts when the macro sees it."),
    "start_rage": _pic("Mission start icon (Order: Rage)", "Detection", {"normal": "start_rage.png"}, 0.75,
                       "Universal with the Rage preset only: your Order: Rage icon (the burning dagger) on key 2, in a "
                       "mission in human form. Built in - the mission starts when the macro sees it."),
    "retry": _pic("Retry button", "Detection", {"normal": "retry_text.png", "low": "low/retry_text.png"}, 0.90,
                  "The word RETRY on the end screen. Drag the box tightly around the word."),
    "retry_alt": _pic("Retry button with counter", "Detection", {"normal": "alt_retry_button.png"}, 0.85,
                      "The RETRY (0/1) button some end screens show. Drag the box around the whole button."),
    "grab": _pic("Streak in danger text", "Detection", {"normal": "grabbed_text.png"}, 0.70,
                 "The red YOUR STREAK IS IN DANGER text. When it shows, the macro presses ability 1 (escape grab).",
                 "red"),
    "completed": _pic("Result: Completed", "Results", {"normal": "result_completed.png"}, 0.70,
                      "The gold COMPLETED title on the end screen.", "gold"),
    "failed": _pic("Result: Failed", "Results", {"normal": "result_failed.png"}, 0.70,
                   "The FAILED title on the end screen.", "gold"),
    "scroll": _pic("Scroll", "Loot", {"normal": "loot_scroll.png", "low": "low/loot_scroll.png"}, 0.75, _LOOT_HOW),
    "vessel": _pic("Vessel (raids)", "Loot", {"normal": "loot_vessel.png"}, 0.75, _LOOT_HOW),
    "body": _pic("Body fragment", "Loot", {"normal": "loot_body.png", "low": "low/loot_body.png"}, 0.75, _LOOT_HOW),
    "defence": _pic("Defence fragment", "Loot", {"normal": "loot_defence.png"}, 0.75, _LOOT_HOW),
    "offence": _pic("Offence fragment", "Loot", {"normal": "loot_offence.png", "low": "low/loot_offence.png"}, 0.75, _LOOT_HOW),
    "support": _pic("Support fragment", "Loot", {"normal": "loot_support.png", "low": "low/loot_support.png"}, 0.75, _LOOT_HOW),
    "attack_serum": _pic("Attack serum", "Loot", {}, 0.75, _LOOT_HOW + " (No built-in picture - capture one to count it.)"),
    "armor_serum": _pic("Armor serum", "Loot", {"normal": "loot_armor_serum.png"}, 0.75, _LOOT_HOW),
    "female_serum": _pic("Female serum", "Loot", {"normal": "loot_female_serum.png"}, 0.75, _LOOT_HOW),
    "beast_serum": _pic("Beast serum", "Loot", {"normal": "loot_beast_serum.png"}, 0.75, _LOOT_HOW),
    "colossal_serum": _pic("Colossal serum", "Loot", {"normal": "loot_colossal_serum.png"}, 0.75, _LOOT_HOW),
    "shiki4": _pic("Shiki ability 4 icon", "Shiki", {"normal": "shiki_ability4.png"}, 0.80,
                   "Your ability 4 icon when it is ready. Shiki stops buying time as soon as it shows."),
    "raid_start": _pic("Raid start", "Female Raid", {"normal": "raid_start.png"}, 0.80,
                       "The picture that shows when a Female Raid begins."),
    "skip": _pic("Skip button", "Female Raid", {"normal": "skip.png"}, 0.67, "The cutscene skip button."),
    "finish": _pic("Finish button", "Female Raid", {"normal": "finish_button.png"}, 0.80,
                   "The finish button after the raid (with the chests)."),
    "heatwave": _pic("Heatwave", "Female Raid", {"normal": "heatwave.png"}, 0.80,
                     "The heatwave warning in the raid. Ability 1 is spammed while it shows."),
    "shifted": _pic("Shifted (titan bar)", "Smart waits", {"normal": "shifted_bar.png"}, 0.80,
                    "Your titan skill bar's ability 2 icon (the burning figure) - it shows where the speedometer was "
                    "once you're shifted into the Colossal. Built in, and with Smart shift wait on the macro saves "
                    "your own copy by itself during a run (Auto-learn). Used by 'Smart shift wait'."),
    "shifted4": _pic("Shifted ability 4 icon", "Smart waits", {"normal": "shifted_a4.png"}, 0.60,
                     "Your Colossal ability 4 icon (the burning titan) on the titan skill bar. With 'Stop ability 4 "
                     "spam once used' on, the spam stops when this icon dims (the attack went off). Built in."),
    "disconnect": _pic("Disconnected message", "Reconnect", {}, 0.75,
                       "Roblox's Disconnected message box. Needed for auto-reconnect."),
    "select": _pic("Select (game loaded)", "Reconnect", {}, 0.75,
                   "Something that only shows once AOTR has loaded (like the slot Select button)."),
    "play": _pic("Play (lobby)", "Reconnect", {}, 0.75,
                 "The Play button in the lobby, shown before 'Click play (lobby)' is clicked."),
}
PICTURE_GROUPS = ("Detection", "Smart waits", "Results", "Loot", "Shiki", "Female Raid", "Reconnect")
FRAGMENT_KINDS = ("body", "defence", "offence", "support")
SERUM_KINDS = ("attack_serum", "armor_serum", "female_serum", "beast_serum", "colossal_serum")
LOOT_KINDS = ("scroll", "vessel") + FRAGMENT_KINDS + SERUM_KINDS
LOOT_SHORT = {"scroll": "Scrolls", "vessel": "Vessels", "body": "Body", "defence": "Defence", "offence": "Offence",
              "support": "Support", "attack_serum": "Attack", "armor_serum": "Armor", "female_serum": "Female",
              "beast_serum": "Beast", "colossal_serum": "Colossal"}
RETRY_SCALES = (0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.3)  # windowed games can be smaller
START_SCALES = RETRY_SCALES
SCALE_OF = {"retry": "retry_scale", "retry_alt": "retry_scale", "start": "start_scale", "start_rage": "rage_scale"}


def loot_kinds_for(raid):
    return (("vessel",) if raid else ("scroll",)) + FRAGMENT_KINDS + SERUM_KINDS


def read_image(path):
    try:
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


def own_picture_path(key):
    return os.path.join(PICTURES_DIR, key + ".png")


def red_mask(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, (0, 120, 90), (10, 255, 255)) | cv2.inRange(hsv, (170, 120, 90), (180, 255, 255))


def gold_mask(bgr):
    return cv2.inRange(cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV), (12, 70, 150), (40, 255, 255))


MASKS = {"red": red_mask, "gold": gold_mask}


def gold_share(bgr):
    """Share of bright gold pixels (0-1). A ready ability icon is gold on dark; it dims once used."""
    return float(np.count_nonzero(gold_mask(bgr))) / max(1, bgr.shape[0] * bgr.shape[1])


def colour_sig(bgr):
    """(share of clearly coloured pixels, their mean hue 0-180) - hue None when there's hardly any colour."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    m = (hsv[..., 1] > 90) & (hsv[..., 2] > 80)
    share = float(m.mean()) if m.size else 0.0
    if share < 0.04:
        return share, None
    h = hsv[..., 0][m].astype(np.float32) * (2 * np.pi / 180.0)
    return share, (math.degrees(math.atan2(float(np.sin(h).mean()), float(np.cos(h).mean()))) / 2.0) % 180.0


def colour_match(tpl_bgr, roi_bgr, max_hue=22.0):
    """Same colour as the picture? (The fragments share one shape: blue, red, green and gold are told apart by
    colour; an empty dark spot has no colour at all.)"""
    ts, th = colour_sig(tpl_bgr)
    if th is None:
        return True  # a picture without real colour: nothing to compare
    rs, rh = colour_sig(roi_bgr)
    if rh is None or rs < 0.4 * ts:
        return False
    dh = abs(th - rh)
    return min(dh, 180.0 - dh) <= max_hue


def same_score(a, b):
    """How alike two pictures of the same size are (-1..1, brightness changes don't count)."""
    if a is None or b is None or a.shape != b.shape:
        return -1.0
    res = cv2.matchTemplate(a, b, cv2.TM_CCOEFF_NORMED)
    cv2.patchNaNs(res, -1.0)
    return float(res[0, 0])


def _resize(img, factor):
    interp = cv2.INTER_AREA if factor < 1 else cv2.INTER_CUBIC
    return cv2.resize(img, None, fx=factor, fy=factor, interpolation=interp)


def _half(img):
    return cv2.resize(img, (max(1, img.shape[1] // 2), max(1, img.shape[0] // 2)), interpolation=cv2.INTER_AREA)


def load_picture(key, scale):
    """[(quality, image at 1080p size, image at monitor size)], own_picture?
    Your own picture (captured at monitor size) wins over the built-in 1080p ones."""
    own = own_picture_path(key)
    if os.path.isfile(own):
        img = read_image(own)
        if img is not None and img.shape[0] >= 4 and img.shape[1] >= 4:
            at_1080 = img if abs(scale - 1.0) <= 0.01 else _resize(img, 1.0 / scale)
            return [("yours", at_1080, img)], True
    out = []
    for quality, rel in PICTURES[key]["files"].items():
        img = read_image(resource_path("assets", *rel.split("/")))
        if img is not None:
            native = img if abs(scale - 1.0) <= 0.01 else _resize(img, scale)
            out.append((quality, img, native))
    return out, False


# ---- screen capture: BitBlt straight into a numpy buffer (much faster than PIL) -------------

gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
SRCCOPY = 0x00CC0020


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


user32.GetWindowDC.argtypes = (wintypes.HWND,)
user32.GetWindowDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
user32.ReleaseDC.restype = ctypes.c_int
gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int)
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.BitBlt.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD)
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.GetDIBits.argtypes = (wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                            ctypes.POINTER(BITMAPINFO), wintypes.UINT)
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = (wintypes.HDC,)
gdi32.DeleteDC.restype = wintypes.BOOL


class ScreenGrabber:
    """Screenshots of one monitor as a BGRA numpy array. Layered windows (like the mini bar) are left out."""

    def __init__(self, mon):
        self.mon = mon
        self.w, self.h = mon["width"], mon["height"]
        self._small = {}
        self.srcdc = user32.GetWindowDC(None)
        self.memdc = gdi32.CreateCompatibleDC(self.srcdc)
        self.bmp = gdi32.CreateCompatibleBitmap(self.srcdc, self.w, self.h)
        if not (self.srcdc and self.memdc and self.bmp):
            self.close()
            raise OSError("could not set up screen capture")
        self.old = gdi32.SelectObject(self.memdc, self.bmp)
        self.bmi = BITMAPINFO()
        hdr = self.bmi.bmiHeader
        hdr.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        hdr.biWidth, hdr.biHeight = self.w, -self.h  # negative = top-down rows
        hdr.biPlanes, hdr.biBitCount, hdr.biCompression = 1, 32, 0
        self.bufs = [np.empty((self.h, self.w, 4), dtype=np.uint8) for _ in range(2)]
        self.flip = 0
        self.lock = threading.Lock()

    def grab(self):
        with self.lock:
            if not gdi32.BitBlt(self.memdc, 0, 0, self.w, self.h, self.srcdc, self.mon["left"], self.mon["top"], SRCCOPY):
                raise OSError("BitBlt failed (%d)" % ctypes.get_last_error())
            self.flip ^= 1  # two buffers, so the previous screenshot stays valid
            buf = self.bufs[self.flip]
            got = gdi32.GetDIBits(self.memdc, self.bmp, 0, self.h, buf.ctypes.data_as(ctypes.c_void_p),
                                  ctypes.byref(self.bmi), 0)
            if got != self.h:
                raise OSError("GetDIBits failed")
            return buf

    def grab_rect(self, x, y, w, h):
        """BGRA copy of a small part of the monitor (x, y relative to the monitor) - far cheaper than grab()."""
        w, h = max(1, int(w)), max(1, int(h))
        with self.lock:
            small = self._small.get((w, h))
            if small is None:
                if len(self._small) >= 24:
                    self._free_small()
                memdc = gdi32.CreateCompatibleDC(self.srcdc)
                bmp = gdi32.CreateCompatibleBitmap(self.srcdc, w, h)
                if not (memdc and bmp):
                    raise OSError("could not set up a small capture")
                old = gdi32.SelectObject(memdc, bmp)
                bmi = BITMAPINFO()
                hdr = bmi.bmiHeader
                hdr.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                hdr.biWidth, hdr.biHeight = w, -h
                hdr.biPlanes, hdr.biBitCount, hdr.biCompression = 1, 32, 0
                small = (memdc, bmp, old, bmi, np.empty((h, w, 4), dtype=np.uint8))
                self._small[(w, h)] = small
            memdc, bmp, old, bmi, buf = small
            if not gdi32.BitBlt(memdc, 0, 0, w, h, self.srcdc, self.mon["left"] + int(x), self.mon["top"] + int(y), SRCCOPY):
                raise OSError("BitBlt failed (%d)" % ctypes.get_last_error())
            if gdi32.GetDIBits(memdc, bmp, 0, h, buf.ctypes.data_as(ctypes.c_void_p), ctypes.byref(bmi), 0) != h:
                raise OSError("GetDIBits failed")
            return buf.copy()

    def _free_small(self):
        for memdc, bmp, old, _, _ in self._small.values():
            try:
                gdi32.SelectObject(memdc, old)
                gdi32.DeleteObject(bmp)
                gdi32.DeleteDC(memdc)
            except Exception:
                pass
        self._small.clear()

    def close(self):
        try:
            self._free_small()
        except Exception:
            pass
        try:
            if getattr(self, "old", None):
                gdi32.SelectObject(self.memdc, self.old)
            if self.bmp:
                gdi32.DeleteObject(self.bmp)
            if self.memdc:
                gdi32.DeleteDC(self.memdc)
            if self.srcdc:
                user32.ReleaseDC(None, self.srcdc)
        except Exception:
            pass
        self.bmp = self.memdc = self.srcdc = None


# ---- matching --------------------------------------------------------------------------------
#  Every screenshot gets a small grayscale copy (half of 1080p size, whatever the screen is). The
#  pictures are searched for on that copy (cheap), then the best few spots are scored on the real
#  screenshot in full colour - that full-size score is the one compared with the thresholds.

class Match:
    """Where a picture was seen, in pixels of the monitor (native resolution)."""
    __slots__ = ("cx", "cy", "score", "w", "h", "scale")

    def __init__(self, cx, cy, score, w, h, scale):
        self.cx, self.cy, self.score, self.w, self.h, self.scale = cx, cy, score, w, h, scale


class Shot:
    """One screenshot: the native BGRA pixels plus a half-1080p-size copy for searching."""

    def __init__(self, raw, scale):
        self.raw = raw
        self.f = 2.0 * scale  # native pixels per small pixel
        h, w = raw.shape[:2]
        self.small = cv2.resize(raw, (max(1, int(round(w / self.f))), max(1, int(round(h / self.f)))),
                                interpolation=cv2.INTER_AREA)
        self._gray = None
        self._masks = {}

    @property
    def gray_small(self):
        if self._gray is None:
            self._gray = cv2.cvtColor(self.small, cv2.COLOR_BGRA2GRAY)
        return self._gray

    def mask_small(self, kind):
        m = self._masks.get(kind)
        if m is None:
            m = MASKS[kind](cv2.cvtColor(self.small, cv2.COLOR_BGRA2BGR))
            self._masks[kind] = m
        return m

    def roi(self, x0, y0, x1, y1):
        return np.ascontiguousarray(self.raw[y0:y1, x0:x1, :3])


class Tpl:
    """One picture at one size: full colour at monitor size + a small grayscale copy (colour masks for
    the pictures that are matched on their red / gold pixels only)."""

    def __init__(self, native_bgr, bgr_1080, s, mask):
        self.s = s
        self.mask = mask
        small = _half(bgr_1080)
        if mask:
            self.full = MASKS[mask](native_bgr)
            self.small = MASKS[mask](small)
        else:
            self.full = native_bgr
            self.small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        self.h, self.w = self.full.shape[:2]


def _scores(img, tpl):
    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    cv2.patchNaNs(res, -1.0)
    return res


def verify(shot, tpl, x, y, margin):
    """Full-size score of `tpl` with its top-left corner near native (x, y)."""
    H, W = shot.raw.shape[:2]
    x0, y0 = max(0, int(x) - margin), max(0, int(y) - margin)
    x1, y1 = min(W, int(x) + tpl.w + margin), min(H, int(y) + tpl.h + margin)
    if x1 - x0 < tpl.w or y1 - y0 < tpl.h:
        return None
    roi = shot.roi(x0, y0, x1, y1)
    if tpl.mask:
        roi = MASKS[tpl.mask](roi)
        if not roi.any():
            return None
    _, score, _, loc = cv2.minMaxLoc(_scores(roi, tpl.full))
    return Match(x0 + loc[0] + tpl.w / 2.0, y0 + loc[1] + tpl.h / 2.0, float(score), tpl.w, tpl.h, tpl.s)


def search(shot, tpl, peaks=3, rows=None):
    """Best full-size match of `tpl` anywhere on the screen (or only between native rows `rows` = (y0, y1))."""
    src = shot.mask_small(tpl.mask) if tpl.mask else shot.gray_small
    off = 0
    if rows is not None:
        off = max(0, int(rows[0] / shot.f))
        src = src[off:max(off + 1, int(math.ceil(rows[1] / shot.f)))]
    th, tw = tpl.small.shape[:2]
    if th < 4 or tw < 4 or th > src.shape[0] or tw > src.shape[1]:
        return None
    if tpl.mask and not src.any():
        return None
    res = _scores(src, tpl.small)
    margin = int(3 * shot.f) + 2
    best = None
    for _ in range(peaks):
        _, s, _, loc = cv2.minMaxLoc(res)
        if s < 0.35:
            break
        m = verify(shot, tpl, loc[0] * shot.f, (loc[1] + off) * shot.f, margin)
        if m and (best is None or m.score > best.score):
            best = m
        x, y = loc
        res[max(0, y - th):y + th + 1, max(0, x - tw):x + tw + 1] = -1.0
    return best


class Detector:
    def __init__(self, cfg, log, save_cb=None, mon=None):
        self.cfg = cfg
        self.log = log
        self.save_cb = save_cb
        self.mon = mon if mon is not None else pick_monitor(cfg)
        self.scale = self.mon.get("mon_height", self.mon["height"]) / 1080.0  # windowed: still the monitor's
        self.base, self.own = {}, {}
        self._tpl_cache = {}
        self.hints = {}            # key -> (size, x, y): where it was seen last (native top-left)
        self.retry_scale = cfg.get("retry_scale")
        self.retry_scans = 0
        self.start_scale = cfg.get("start_scale")
        self.start_scans = 0
        self.rage_scale = cfg.get("rage_scale")
        self.rage_scans = 0
        self.checks = {}
        self._grab_failed = False
        self.grabber = ScreenGrabber(self.mon)

    def close(self):
        self.grabber.close()

    def pics(self, key):
        if key not in self.base:
            self.base[key], self.own[key] = load_picture(key, self.scale)
            if not self.base[key] and PICTURES[key]["files"]:
                self.log("Picture '%s' could not be loaded - that check is off" % PICTURES[key]["label"])
        return self.base[key]

    def has(self, key):
        return bool(self.pics(key))

    def threshold(self, key, override=None):
        th = PICTURES[key]["threshold"] if override is None else override
        return th - 0.05 if abs(self.scale - 1.0) > 0.01 else th

    def tpls(self, key, s):
        out = []
        for i, (_, bgr_1080, native) in enumerate(self.pics(key)):
            ck = (key, i, s)
            t = self._tpl_cache.get(ck)
            if t is None:
                mask = PICTURES[key]["mask"]
                if mask and self.own.get(key) and np.count_nonzero(MASKS[mask](native)) < 0.03 * native.shape[0] * native.shape[1]:
                    mask = None  # your picture isn't red / gold like the built-in one: match it as it is
                t = Tpl(native if s == 1.0 else _resize(native, s), bgr_1080 if s == 1.0 else _resize(bgr_1080, s),
                        s, mask)
                self._tpl_cache[ck] = t
            out.append(t)
        return out

    def grab(self):
        """A Shot of the monitor, or None when there is no usable picture right now."""
        try:
            raw = self.grabber.grab()
        except Exception as e:
            if not self._grab_failed:
                self._grab_failed = True
                self.log("Could not take a screenshot (%s) - waiting for the screen" % e)
            return None
        if self._grab_failed:
            self._grab_failed = False
            self.log("Screen is back - detection resumed")
        if not raw[::16, ::16, :3].any():
            return None  # black frame (monitor off / lock screen)
        return Shot(raw, self.scale)

    def find(self, key, shot, scales=(1.0,), full=True, threshold=None, rows=None):
        """A Match at or above the threshold, or None. Looks where it was last seen first (nearly free)."""
        if shot is None or not self.pics(key):
            return None
        th = self.threshold(key, threshold)
        hint = self.hints.get(key)
        if hint:
            margin = int(12 * self.scale) + 2
            for tpl in self.tpls(key, hint[0]):
                m = verify(shot, tpl, hint[1], hint[2], margin)
                if m and m.score >= th:
                    return m
        if not full:
            return None
        best = None
        for s in scales:
            for tpl in self.tpls(key, s):
                m = search(shot, tpl, rows=rows)
                if m and (best is None or m.score > best.score):
                    best = m
        if best and best.score >= th:
            self.hints[key] = (best.scale, best.cx - best.w / 2.0, best.cy - best.h / 2.0)
            return best
        return None

    def best_any(self, key, shot, scales=(1.0,), rows=None):
        """Best score at any of `scales`, even below the threshold (for Test detection)."""
        best = None
        for s in scales:
            for tpl in self.tpls(key, s):
                m = search(shot, tpl, rows=rows)
                if m and (best is None or m.score > best.score):
                    best = m
        return best

    def _every(self, name, n):
        self.checks[name] = self.checks.get(name, 0) + 1
        return self.checks[name] % n == 0

    def seen(self, key, shot=None, thorough=True, threshold=None):
        shot = self.grab() if shot is None else shot
        if shot is None:
            return None
        full = thorough or key not in self.hints or self._every(key, 3)
        return self.find(key, shot, full=full, threshold=threshold)

    def roi_find(self, key, threshold=None):
        """Look only where `key` was seen last, with a tiny screenshot (nearly free). None when it isn't there
        or hasn't been seen yet."""
        hint = self.hints.get(key)
        if not hint or not self.pics(key):
            return None
        tpls = self.tpls(key, hint[0])
        margin = int(12 * self.scale) + 2
        x0, y0 = max(0, int(hint[1]) - margin), max(0, int(hint[2]) - margin)
        x1 = min(self.mon["width"], int(hint[1]) + max(t.w for t in tpls) + margin)
        y1 = min(self.mon["height"], int(hint[2]) + max(t.h for t in tpls) + margin)
        if x1 - x0 < 4 or y1 - y0 < 4:
            return None
        try:
            raw = self.grabber.grab_rect(x0, y0, x1 - x0, y1 - y0)
        except Exception:
            return None
        if not raw[::4, ::4, :3].any():
            return None  # black (loading / monitor off)
        roi = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
        th = self.threshold(key, threshold)
        best = None
        for tpl in tpls:
            src = MASKS[tpl.mask](roi) if tpl.mask else roi
            if src.shape[0] < tpl.h or src.shape[1] < tpl.w or (tpl.mask and not src.any()):
                continue
            _, score, _, loc = cv2.minMaxLoc(_scores(src, tpl.full))
            if best is None or score > best.score:
                best = Match(x0 + loc[0] + tpl.w / 2.0, y0 + loc[1] + tpl.h / 2.0, float(score), tpl.w, tpl.h, tpl.s)
        return best if best and best.score >= th else None

    def look(self, key, full_every=1, threshold=None):
        """Cheap check: where it was seen last first; a full-screen search only every `full_every`-th call."""
        m = self.roi_find(key, threshold)
        if m is not None:
            return m
        if not self._every("look:" + key, max(1, full_every)):
            return None
        shot = self.grab()
        if shot is None:
            return None
        if key not in ("start", "start_rage"):
            return self.find(key, shot, threshold=threshold)
        name = "rage_scale" if key == "start_rage" else "start_scale"
        learned = getattr(self, name)
        m = self.find(key, shot, self.start_scales(key), threshold=threshold)
        if m and (learned is None or abs(m.scale - learned) > 0.001):
            # A new size: the first one that passes may be a step off - keep the best nearby size.
            near = [round(m.scale + d_, 3) for d_ in (-0.05, -0.025, 0.025, 0.05)]
            better = self.best_any(key, shot, near)
            if better and better.score > m.score:
                m = better
                self.hints[key] = (m.scale, m.cx - m.w / 2.0, m.cy - m.h / 2.0)
            setattr(self, name, m.scale)
            self.cfg[name] = m.scale
            self.log("%s matched at size x%.2f (score %.2f) - remembered" % (PICTURES[key]["label"], m.scale, m.score))
            if self.save_cb:
                self.save_cb()
        return m

    def start_scales(self, key="start"):
        """Sizes to try for a start icon: the remembered one (now and then another), or a first guess and the
        others in turn until it has been seen - a windowed game can draw its skill bar smaller or bigger."""
        rage = key == "start_rage"
        if rage:
            self.rage_scans += 1
            n, learned = self.rage_scans, self.rage_scale
        else:
            self.start_scans += 1
            n, learned = self.start_scans, self.start_scale
        if learned is not None:
            out = [learned]
            if n % 16 == 0:
                others = [s for s in START_SCALES if abs(s - learned) > 0.001]
                out.append(others[(n // 16) % len(others)])
            return out
        first = 1.0
        if rage and self.start_scale is not None and self.pics(key) and not self.own.get(key):
            first = self.start_scale  # the built-in Order: Rage icon sits on the same skill bar as the speedometer
        others = [s for s in START_SCALES if abs(s - first) > 0.001]
        return [first] if n % 2 else [first, others[(n // 2) % len(others)]]

    def titan_scales(self):
        """Sizes for the titan bar icons: around the size the speedometer was seen at."""
        hint = self.hints.get("start") or self.hints.get("start_rage")
        base = hint[0] if hint else (self.start_scale or self.rage_scale or 1.0)
        return tuple(round(base * s, 3) for s in TITAN_SCALES)

    def start_keys(self, raid):
        if raid:
            return ("skip", "raid_start")
        if self.cfg.get("routine") == "Universal" and self.cfg["timings"]["Universal"].get("rage"):
            return ("start_rage", "start")
        return ("start",)

    def start_visible(self, raid, full_every=1):
        return any(self.look(key, full_every) is not None for key in self.start_keys(raid))

    def start_still_there(self, raid):
        """Is the start marker still where it was? (tiny screenshots only)"""
        return any(self.roi_find(key) is not None for key in self.start_keys(raid))

    def find_retry(self, shot):
        for key in ("retry", "retry_alt"):
            m = self.find(key, shot, full=False)  # where it was seen last
            if m:
                return m
        self.retry_scans += 1
        n = self.retry_scans
        if self.retry_scale is not None:
            scales = [self.retry_scale]
            if n % 16 == 0:  # now and then try another size, in case the screen changed
                others = [s for s in RETRY_SCALES if abs(s - self.retry_scale) > 0.001]
                scales.append(others[(n // 16) % len(others)])
        else:
            others = [s for s in RETRY_SCALES if s != 1.0]
            scales = [1.0] if n % 2 else [others[(n // 2) % len(others)]]
        best = None
        for key in ("retry", "retry_alt"):
            m = self.find(key, shot, scales)
            if m and (best is None or m.score > best.score):
                best = m
        if best and (self.retry_scale is None or abs(best.scale - self.retry_scale) > 0.001):
            self.retry_scale = best.scale
            self.cfg["retry_scale"] = best.scale
            self.log("Retry button matched at size x%.2f (score %.2f) - remembered" % (best.scale, best.score))
            if self.save_cb:
                self.save_cb()
        return best

    def band(self, keys, above=1.5, below=2.5):
        """Native rows (y0, y1) around where any of `keys` was seen this session, or None (not seen yet)."""
        spans = []
        for key in keys:
            hint = self.hints.get(key)
            if hint and self.pics(key):
                h = self.tpls(key, hint[0])[0].h
                spans.append((hint[2] - above * h, hint[2] + (1 + below) * h))
        if not spans:
            return None
        return max(0, min(a for a, _ in spans)), min(self.mon["height"], max(b for _, b in spans))

    def end_scales(self):
        """Sizes for end-screen pictures (results, loot): normal, plus the size the retry button was found at -
        the end screen's text and icons are usually scaled the same way."""
        rs = self.retry_scale
        return (1.0,) if not rs or abs(rs - 1.0) < 0.001 else (1.0, rs)

    def find_grab(self, shot):
        if not self.pics("grab"):
            return None
        full = "grab" not in self.hints or self._every("grab", 2)
        return self.find("grab", shot, (1.0,), full=full)

    def to_screen(self, x, y):
        return self.mon["left"] + int(x), self.mon["top"] + int(y)

    def forget(self, key):
        """Load `key` again next time (its picture file changed)."""
        self.base.pop(key, None)
        self.own.pop(key, None)
        self.hints.pop(key, None)
        for ck in [ck for ck in self._tpl_cache if ck[0] == key]:
            del self._tpl_cache[ck]

    @staticmethod
    def box_around(cx, cy, w, h, k=1.0):
        """(x0, y0, x1, y1): a box k times w x h around (cx, cy)."""
        return cx - k * w / 2.0, cy - k * h / 2.0, cx + k * w / 2.0, cy + k * h / 2.0

    def grab_box(self, x0, y0, x1, y1):
        """(BGR pixels, x0, y0) of a part of the monitor (native pixels); pixels are None when there's nothing."""
        x0, y0 = max(0, int(round(x0))), max(0, int(round(y0)))
        x1, y1 = min(self.mon["width"], int(round(x1))), min(self.mon["height"], int(round(y1)))
        if x1 - x0 < 4 or y1 - y0 < 4:
            return None, x0, y0
        try:
            raw = self.grabber.grab_rect(x0, y0, x1 - x0, y1 - y0)
        except Exception:
            return None, x0, y0
        if not raw[::4, ::4, :3].any():
            return None, x0, y0  # black (loading / monitor off)
        return cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR), x0, y0

    def near_find(self, key, box, scales=(1.0,), threshold=None):
        """Best match of `key` inside `box` (a tiny screenshot of just that part), or None below the threshold."""
        if not self.pics(key):
            return None
        roi, x0, y0 = self.grab_box(*box)
        if roi is None:
            return None
        th = self.threshold(key, threshold)
        best = None
        for s in scales:
            for tpl in self.tpls(key, s):
                src = MASKS[tpl.mask](roi) if tpl.mask else roi
                if src.shape[0] < tpl.h or src.shape[1] < tpl.w or (tpl.mask and not src.any()):
                    continue
                _, score, _, loc = cv2.minMaxLoc(_scores(src, tpl.full))
                if best is None or score > best.score:
                    best = Match(x0 + loc[0] + tpl.w / 2.0, y0 + loc[1] + tpl.h / 2.0, float(score), tpl.w, tpl.h, tpl.s)
        return best if best and best.score >= th else None

    def slot2_box(self):
        """(cx, cy, w, h) of the skill bar's ability 2 slot - where the speedometer was seen at the mission
        start (native pixels) - or None when it hasn't been seen."""
        for key in ("start", "start_rage"):  # both sit on key 2
            hint = self.hints.get(key)
            if hint and self.pics(key):
                tpl = self.tpls(key, hint[0])[0]
                return hint[1] + tpl.w / 2.0, hint[2] + tpl.h / 2.0, tpl.w, tpl.h
        return None


# =============================================================================
#  Settings
# =============================================================================

ROUTINES = ("Blood Awakening", "Shiki", "Universal", "Female Raid")
TIMING_SECTIONS = ("Shared",) + ROUTINES
KEY_ROWS = [
    ("start", "Start / manual start", "Starts the macro. While it waits for a mission, starts the routine right away."),
    ("pause", "Pause / resume", "Pauses everything and lets go of all keys."),
    ("stop", "Stop", "Stops the macro (the app stays open). Also stops a Build optimiser scan."),
    ("scan_stop", "Stop build scan", "Stops a Build optimiser scan straight away (moving the mouse does too)."),
    ("ability1", "Ability 1 / escape grab", "Escape grab in missions; ability 1 in the Female Raid."),
    ("ability2", "Ability 2", "First key of every mission. While shifted it ejects (used by the failsafe)."),
    ("ability3", "Ability 3", "Shiki and Universal press it after the strafe. Also used in the raid."),
    ("ability4", "Ability 4", "Ability 4 / the shifted ability 4 (the big Colossal attack)."),
    ("ability5", "Ability 5 (shift / titan)", "Shifts into the titan, then pressed over and over until the mission ends."),
    ("dash", "Dash", "Spammed right after ability 2."),
    ("left", "Strafe / move left", "Double-tapped for strafes. Held while shifted when 'Move while shifted' is Left."),
    ("right", "Move right", "Held while shifted when 'Move while shifted' is Right."),
    ("lock", "Shift lock", "Used by Look up, Look down, Fix shift lock and the failsafe."),
    ("skip", "Skip cutscene", "Spammed in the Female Raid when the skip button shows."),
]
HOTKEYS = ("start", "pause", "stop", "scan_stop")
DEFAULT_KEYS = {"start": "f8", "pause": "f6", "stop": "f7", "scan_stop": "esc", "ability1": "1", "ability2": "2", "ability3": "3",
                "ability4": "4", "ability5": "5", "dash": "space", "left": "a", "right": "d", "lock": "ctrl",
                "skip": "e"}


class Field:
    def __init__(self, group, key, label, kind, default, lo=None, hi=None, help=""):
        self.group, self.key, self.label, self.kind = group, key, label, kind
        self.default, self.lo, self.hi, self.help = default, lo, hi, help


def _skip_ability2():
    return Field("Start", "skip_ability2", "Skip ability 2", "bool", False,
                 help="On: the mission starts without ability 2 (and without the wait after it).")


def _fast_mode():
    return Field("Retry", "fast_mode", "Fast mode", "bool", False,
                 help="On: retry is clicked the moment it is seen (checked every 0.1s, no second look), the result "
                      "and loot are read from that one screenshot, and the next start skips the 1s settle wait.")


def _shift_fields():
    g = "Shift sequence"
    return [
        Field(g, "shift_spam_time", "Ability 5 spam time", "sec", 5.0, 0, 60, "How long ability 5 is spammed so the shift is used."),
        Field(g, "shift_spam_interval", "Ability 5 spam interval", "sec", 0.2, 0.02, 2, "Pause between those presses."),
        Field(g, "shift_spam_extra", "Extra spam inside the wait", "sec", 4.0, 0, 60,
              "Ability 5 keeps being pressed this long, inside the wait below."),
        Field(g, "shifted4_at", "Wait for the shift", "sec", 17.0, 0, 60,
              "Seconds after the ability 5 spam before the shifted ability 4 starts."),
        Field(g, "shifted4_time", "Shifted ability 4 spam time", "sec", 8.0, 0, 60, "How long the shifted ability 4 is spammed."),
        Field(g, "shifted4_interval", "Shifted ability 4 interval", "sec", 0.2, 0.02, 2, "Pause between those presses."),
        Field(g, "shifted4_to5", "Wait before ability 5", "sec", 3.0, 0, 60,
              "Pause after the shifted ability 4, before the last ability 5 loop."),
        Field(g, "ability5_interval", "Ability 5 press interval", "sec", 1.0, 0.05, 10,
              "How often ability 5 is pressed (while moving) until the retry button shows up."),
        Field("Smart waits", "smart_shift", "Smart shift wait", "bool", False,
              help="On: instead of the fixed waits above, the macro watches your skill bar and goes on the moment "
                   "you're shifted (the titan bar shows). The Colossal bar is built in, and during the first run the "
                   "macro saves your own picture of it (Auto-learn). If it never shows, it waits no longer than the "
                   "fixed version would."),
        Field("Smart waits", "smart_shift_delay", "Delay after the shift is seen", "sec", 0.3, 0, 10,
              "Short pause between seeing the shift and the shifted ability 4."),
        Field("Smart waits", "smart_a4", "Stop ability 4 spam once used", "bool", False,
              help="On: while the shifted ability 4 is spammed, the macro watches its icon on the titan bar and stops "
                   "the spam the moment the icon dims (the attack went off), then goes on to ability 5 - which still "
                   "taps ability 4 a few times, just in case. If the icon isn't found it spams the full time."),
    ]


FIELDS = {
    "Shared": [
        Field("Start", "fix_shift_lock", "Fix shift lock at start", "bool", False,
              help="On: the shift-lock key is pressed once the moment the mission starts, before anything else."),
        Field("Start", "no_bicorn", "No Feathered Bicorn", "bool", False,
              help="Turn on if you don't have the Feathered Bicorn. Blood Awakening, Shiki and Universal then look up "
                   "right before the opening dash (shift-lock key, mouse up, shift-lock key), so the dash still "
                   "reaches the titans. It's the last part of 'Wait after ability 2', so it adds no time. Off = no "
                   "look up (have the Bicorn? leave it off)."),
        Field("Start", "look_up_time", "Look up total time", "sec", 0.5, 0.2, 5,
              "No Feathered Bicorn only: the whole look up (both shift-lock presses and the mouse move) takes this long."),
        Field("Start", "look_up_pixels", "Look up amount", "pix", 150, 1, 2000,
              "No Feathered Bicorn only: how far the mouse moves up, in pixels. More = the dash goes higher."),
        Field("Start", "after_ability2", "Wait after ability 2", "sec", 1.5, 0, 30,
              "Nothing else happens during this wait, then the dashing starts."),
        Field("Dashing", "dash_time", "Dash spam time", "sec", 8.2, 0, 60, "How long the dash key is spammed."),
        Field("Dashing", "dash_hold", "Hold per press", "range", (0.065, 0.09), 0.01, 1,
              "How long each dash press is held (min - max, random in between)."),
        Field("Dashing", "dash_gap", "Gap between presses", "range", (0.05, 0.08), 0, 1,
              "Pause between two dash presses (min - max, random in between)."),
        Field("Strafe", "tap_gap", "Double-tap gap", "range", (0.06, 0.12), 0, 1,
              "Pause between the two presses of one strafe, like A-A (min - max)."),
        Field("Shifted", "move_shifted", "Move while shifted", "choice", "Right", ("Right", "Left", "Stand"), None,
              "The direction the titan walks in while ability 5 is pressed at the end. Stand = no key held."),
        Field("Retry", "retry_click_time", "Retry click spam time", "sec", 0.8, 0.05, 10,
              "The retry button is clicked over and over this long instead of once."),
        Field("Retry", "retry_click_interval", "Retry click interval", "sec", 0.1, 0.02, 2, "Pause between those clicks."),
        Field("Retry", "hands_off", "Max hands off after retry", "sec", 7.0, 0, 60,
              "After the retry click the macro goes on as soon as the end screen is gone (at least 1s, at most "
              "this long). Nothing is pressed meanwhile; if retry is still showing after 3s it is clicked again."),
    ],
    "Blood Awakening": [
        _skip_ability2(), _fast_mode(),
        Field("Strafe left", "strafe_left_time", "Strafe left time", "sec", 8.0, 0, 60,
              "After the dashing, the left key is double-tapped over and over this long, then the shift starts. 0 = off."),
        Field("Strafe left", "strafe_gap", "Gap between strafes", "range", (0.15, 0.25), 0, 5, "Random pause between two strafes."),
        Field("Speed finder", "speed_finder", "Speed finder (shorter dash / strafe)", "bool", False,
              help="On: the macro tries a shorter Strafe left time, then a shorter Dash spam time (Shared), 1s at a "
                   "time with 3 runs per try, and keeps a shorter time only when those runs really finished faster and "
                   "none needed the failsafe. The log says what it is trying. It turns itself off when nothing faster "
                   "is left. While it's on it sets those two times itself."),
    ] + _shift_fields(),
    "Shiki": [
        _skip_ability2(), _fast_mode(),
        Field("Ability 3", "after_strafe", "Wait after strafe", "sec", 0.3, 0, 10, "Pause between the strafe and ability 3."),
        Field("Buying time", "cooldown", "Buying time", "sec", 15.0, 0, 120,
              "Seconds of strafing after ability 3 (the ability 4 cooldown)."),
        Field("Buying time", "cooldown_margin", "Cooldown margin", "sec", 0.3, 0, 10, "Tiny extra so ability 4 is surely off cooldown."),
        Field("Buying time", "strafe_gap", "Gap between strafes", "range", (0.15, 0.25), 0, 5,
              "Pause between the strafes while buying time (min - max)."),
        Field("Ability 4 icon", "icon_after", "Look for the icon after", "sec", 3.0, 0, 120,
              "Start looking for the ability 4 icon this long after ability 3."),
        Field("Ability 4 icon", "icon_interval", "Icon check interval", "sec", 0.25, 0.05, 10, "Seconds between two looks for the icon."),
        Field("Ability 4 icon", "icon_threshold", "Icon match threshold", "num", 0.8, 0.3, 1, "Lower it if the icon isn't being detected."),
        Field("Ability 4", "ability4_time", "Ability 4 spam time", "sec", 2.0, 0, 30, "How long ability 4 is spammed once the icon is seen."),
        Field("Ability 4", "ability4_interval", "Ability 4 spam interval", "sec", 0.1, 0.02, 5, "Pause between those presses."),
        Field("Ability 4", "after_ability", "Wait after ability 4", "sec", 0.6, 0, 10, "Pause before the shift sequence starts."),
    ] + _shift_fields(),
    "Universal": [
        _skip_ability2(), _fast_mode(),
        Field("Ability 3", "after_strafe", "Wait after strafe", "sec", 0.0, 0, 10, "Pause between the strafe and ability 3."),
        Field("Look down", "look_time", "Look down time", "sec", 2.0, 0, 20, "Seconds the mouse is dragged down (shift lock, mouse down, shift lock)."),
        Field("Look down", "look_pixels", "Pixels per step", "pix", 15, 1, 200, "Pixels the mouse moves down every 0.01 s."),
        Field("Ability 4", "ability4_time", "Ability 4 spam time", "sec", 3.5, 0, 30, "How long ability 4 is spammed after looking down."),
        Field("Ability 4", "ability4_interval", "Ability 4 spam interval", "sec", 0.1, 0.02, 5, "Pause between those presses."),
        Field("Ability 4", "after_ability", "Wait after ability 4", "sec", 0.6, 0, 10, "Pause before the shift sequence starts."),
        Field("Order: Rage", "rage", "Key 2 is Order: Rage", "bool", False,
              help="On (Rage preset): Order: Rage is on key 2 instead of Order: Advance and is pressed at the same "
                   "moment. The mission start is then spotted by the Order: Rage icon (built in)."),
    ] + _shift_fields(),
    "Female Raid": [
        Field("Chests", "chest1", "Chest 1", "spot", None,
              help="Screen spot of chest 1. Pick it with the Pick button (click on the chest) - the raid needs it."),
        Field("Chests", "chest2", "Chest 2", "spot", None, help="Screen spot of chest 2."),
        Field("Chests", "open_chest2", "Open chest 2", "bool", True, help="On: chest 2 is opened too. Off: only chest 1."),
        Field("Chests", "chest_click_time", "Chest click spam time", "sec", 2.0, 0, 30, "A chest is clicked over and over this long."),
        Field("Chests", "chest_click_interval", "Chest click interval", "sec", 0.1, 0.02, 5, "Pause between those clicks."),
        Field("Chests", "finish_wait", "Max wait for finish button", "sec", 30.0, 1, 300,
              "After clicking a chest the macro waits up to this long for the finish button (= chest opened)."),
        Field("Finish button", "finish_click_time", "Finish click spam time", "sec", 2.0, 0, 30,
              "The finish button is clicked over and over this long."),
        Field("Finish button", "finish_click_interval", "Finish click interval", "sec", 0.1, 0.02, 5, "Pause between those clicks."),
        _fast_mode(),
        Field("Skip button", "skip_spam_time", "Skip spam time", "sec", 2.0, 0, 30,
              "How long the skip key is spammed every time the skip button shows up."),
        Field("Skip button", "skip_spam_interval", "Skip spam interval", "sec", 0.1, 0.02, 5, "Pause between those presses."),
        Field("Heatwave", "skip_number", "Wait for heatwave after skip no.", "int", 3, 2, 50,
              "After this skip button (the first one is no. 1) ability 3 is pressed once and the macro starts "
              "watching for the heatwave; while it shows, ability 1 is spammed."),
        Field("Heatwave", "heatwave_interval", "Ability 1 spam interval", "sec", 0.1, 0.02, 5, "Pause between those presses."),
        Field("Heatwave", "heatwave_repeat", "Pause before it can repeat", "sec", 16.0, 0, 300,
              "Seconds that must pass after one heatwave before the next one is handled. 0 = no pause."),
        Field("Buffing / pre-shift", "open_a1_time", "First ability 1 spam time", "sec", 2.0, 0, 60,
              "After the first skip: ability 1 is spammed this long first."),
        Field("Buffing / pre-shift", "a3_time", "Ability 3 spam time", "sec", 2.5, 0, 60, "Then ability 3 is spammed this long."),
        Field("Buffing / pre-shift", "a3_interval", "Ability 3 spam interval", "sec", 0.1, 0.02, 5, "Pause between those presses."),
        Field("Buffing / pre-shift", "a5_time", "Ability 5 spam time", "sec", 3.0, 0, 60, "Then ability 5 is spammed this long."),
        Field("Buffing / pre-shift", "a5_interval", "Ability 5 spam interval", "sec", 0.1, 0.02, 5, "Pause between those presses."),
        Field("Buffing / pre-shift", "a5_extra", "Extra ability 5 spam while shifting", "sec", 3.0, 0, 60,
              "Ability 5 keeps being pressed this long inside the wait below."),
        Field("Opening", "wait_time", "Wait before ability 1", "sec", 17.0, 0, 120, "Pause after the ability 5 spam."),
        Field("Opening", "a1_time", "Ability 1 spam time", "sec", 4.0, 0, 60, "Then ability 1 is spammed this long."),
        Field("Opening", "a1_interval", "Ability 1 spam interval", "sec", 0.1, 0.02, 5, "Pause between those presses."),
        Field("Ability cycle", "random_gap", "Gap between abilities", "sec", 2.0, 0.05, 60,
              "After the opening, abilities 4, 3, 2 are pressed one after the other (then again from 4), one this "
              "often, until the raid ends."),
    ],
}

# "Speed" preset: only dead time is trimmed. Dash / strafe stay as they are - they depend on the map.
SPEED_PRESET = {"Shared": {"after_ability2": 0.7, "hands_off": 3.0},
                "routine": {"fast_mode": True, "smart_shift": True, "smart_shift_delay": 0.3, "smart_a4": True,
                            "shifted4_to5": 1.0}}

DEFAULT_FAILSAFE = {"enabled": True, "seconds": 120, "look_down": False, "look_time": 2.0,
                    "look_pixels": 15, "click_x": None, "click_y": None}
DEFAULT_APP = {"mini_bar": True, "minimize_on_start": True, "focus_roblox": True, "grab_check": True,
               "track_loot": True, "monitor": 0, "stop_runs": 0, "stop_hours": 0.0, "close_roblox_at_end": False,
               "theme": "Midnight", "accent": ""}
THEMES = {  # side = sidebar, field = inputs; accent = the theme's own accent (used when you haven't picked one)
    "Midnight": {"bg": "#0b0d12", "side": "#0e1117", "card": "#141821", "card2": "#1b202b", "hover": "#232937",
                 "edge": "#1f2430", "edge_hi": "#2a3140", "text": "#e8ebf1", "muted": "#8b93a3", "dim": "#5a6273",
                 "field": "#0f1219", "accent": "#4f8cff"},
    "Graphite": {"bg": "#0e0e10", "side": "#121214", "card": "#18181b", "card2": "#1f1f23", "hover": "#28282d",
                 "edge": "#232327", "edge_hi": "#2e2e33", "text": "#ececee", "muted": "#94949c", "dim": "#63636b",
                 "field": "#131315", "accent": "#a78bfa"},
    "Ocean": {"bg": "#07111a", "side": "#091520", "card": "#0d1b28", "card2": "#122334", "hover": "#182c41",
              "edge": "#142638", "edge_hi": "#1c3349", "text": "#e3eef7", "muted": "#84a0b8", "dim": "#557089",
              "field": "#0a1621", "accent": "#22d3ee"},
    "Forest": {"bg": "#08110d", "side": "#0a1510", "card": "#0f1c16", "card2": "#15251d", "hover": "#1b2f25",
               "edge": "#172820", "edge_hi": "#20362b", "text": "#e4f0e9", "muted": "#86a395", "dim": "#587366",
               "field": "#0b1611", "accent": "#34d399"},
    "Crimson": {"bg": "#120a0c", "side": "#160c0f", "card": "#1d1114", "card2": "#26171b", "hover": "#301d22",
                "edge": "#2a191d", "edge_hi": "#372228", "text": "#f3e8ea", "muted": "#ad8d93", "dim": "#7a5f65",
                "field": "#170d10", "accent": "#f43f5e"},
    "Light": {"bg": "#f3f4f7", "side": "#ffffff", "card": "#ffffff", "card2": "#f1f3f6", "hover": "#e7eaf0",
              "edge": "#e4e7ec", "edge_hi": "#d7dbe3", "text": "#131720", "muted": "#5b6475", "dim": "#8a93a4",
              "field": "#f6f7f9", "accent": "#2563eb"},
}
ACCENT_PRESETS = ("#4f8cff", "#8b5cf6", "#22d3ee", "#14b8a6", "#22c55e", "#f59e0b", "#f97316", "#f43f5e", "#ec4899")
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
DEFAULT_DISCORD = {"mode": "off", "url": "", "bot_token": "", "channel_id": "", "user_id": "", "mention": False,
                   "notify_mission": True, "screenshot": False, "notify_failsafe": True, "notify_error": True,
                   "notify_reconnect": True, "notify_graph": False}
RECONNECT_SHARED_SPOTS = (("pick_slot", "Pick a slot"), ("click_play", "Click play"),
                          ("choose_lobby", "Choose lobby"), ("click_play_lobby", "Click play (lobby)"))
RECONNECT_TAB_SPOTS = {
    "Missions": (("click_missions", "Click missions"), ("m_pick_outskirts", "Pick outskirts"),
                 ("m_create", "Create"), ("m_play", "Play")),
    "Raids": (("click_raids", "Click Raids"), ("r_pick_female_raid", "Pick female raid"),
              ("r_create", "Create"), ("r_play", "Play")),
}
RECONNECT_GATES = {"pick_slot": "select", "click_play_lobby": "play"}
RECONNECT_PLAY_KEYS = ("m_play", "r_play")
RECONNECT_PICTURES = ("disconnect", "select", "play")


def new_family_stats():
    return {"runs": 0, "retries": 0, "completed": 0, "failed": 0, "rescues": 0, "loot": {k: 0 for k in LOOT_KINDS}}


def clean_value(field, raw):
    """A saved / typed value checked against the field's limits, or None when it is unusable.
    (A 'spot' that isn't set is the valid value None - use clean_spot for those.)"""
    try:
        if field.kind == "bool":
            return bool(raw) if isinstance(raw, (bool, int)) else None
        if field.kind == "choice":
            return raw if raw in field.lo else None
        if field.kind == "range":
            a, b = float(raw[0]), float(raw[1])
            return (a, b) if field.lo <= a <= b <= field.hi else None
        if field.kind == "int":
            v = float(raw)
            return int(v) if v == int(v) and field.lo <= v <= field.hi else None
        v = float(raw)
        if not (field.lo <= v <= field.hi):
            return None
        return int(round(v)) if field.kind == "pix" else v
    except (TypeError, ValueError, IndexError):
        return None


def clean_spot(raw):
    if isinstance(raw, (list, tuple)) and len(raw) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in raw):
        return [raw[0], raw[1]]
    return None


def default_config():
    return {
        "routine": ROUTINES[0],
        "keys": dict(DEFAULT_KEYS),
        "timings": {sec: {f.key: f.default for f in FIELDS[sec]} for sec in TIMING_SECTIONS},
        "failsafe": dict(DEFAULT_FAILSAFE),
        "app": dict(DEFAULT_APP),
        "discord": dict(DEFAULT_DISCORD),
        "reconnect": {"enabled": False, "spots": {}, "click_delay": 2.5, "play_delay": 0.5},
        "retry_scale": None,
        "start_scale": None,
        "rage_scale": None,
        "stats": {"missions": new_family_stats(), "raids": new_family_stats(), "best": {}},
        "learned": {},  # things the macro worked out by itself (auto-learned picture, Speed finder progress)
        "optimiser": default_optimiser(),
    }


def default_optimiser():
    return {"playstyle": bo.PLAYSTYLES[0], "family": bo.FAMILIES[0], "capstones": [], "perks": {}, "memories": [],
            "scanned_at": None, "memories_at": None, "scan_rarities": list(DEFAULT_SCAN_RARITIES),
            "tutorial_seen": False}


DEFAULT_SCAN_RARITIES = ("Legendary", "Mythical", "Divine")  # Common, Rare and Epic are skipped unless turned on


def load_optimiser(saved):
    """The optimiser's saved settings and scan, cleaned (unknown perks / bad levels dropped)."""
    o = default_optimiser()
    if not isinstance(saved, dict):
        return o
    if saved.get("playstyle") in bo.PLAYSTYLES:
        o["playstyle"] = saved["playstyle"]
    if saved.get("family") in bo.FAMILIES:
        o["family"] = saved["family"]
    caps = saved.get("capstones")
    if isinstance(caps, list):
        o["capstones"] = [c for c in ("Offense", "Defense", "Support") if c in caps]
    perks = saved.get("perks")
    if isinstance(perks, dict):
        for n, lv in perks.items():
            if n in bo.PERKS and isinstance(lv, (int, float)) and 0 <= lv <= bo.MAX_LEVEL:
                o["perks"][n] = int(lv)
    mems = saved.get("memories")
    if isinstance(mems, list):
        o["memories"] = [m for m in bo.MEMORIES if m in mems]
    for k in ("scanned_at", "memories_at"):
        if isinstance(saved.get(k), (int, float)):
            o[k] = float(saved[k])
    rar = saved.get("scan_rarities")
    if isinstance(rar, list) and any(r in bo.RARITIES for r in rar):
        o["scan_rarities"] = [r for r in bo.RARITIES if r in rar]
    o["tutorial_seen"] = bool(saved.get("tutorial_seen", False))
    return o


def load_config():
    cfg = default_config()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
    except Exception:
        return cfg
    if not isinstance(saved, dict):
        return cfg
    if saved.get("routine") in ROUTINES:
        cfg["routine"] = saved["routine"]
    for name, val in (saved.get("keys") or {}).items():
        if name in cfg["keys"] and isinstance(val, str) and val in VK:
            cfg["keys"][name] = val
    if (saved.get("keys") or {}).get("grab") in VK and "ability1" not in (saved.get("keys") or {}):
        cfg["keys"]["ability1"] = saved["keys"]["grab"]  # v1.0 called it "grab"

    timings = saved.get("timings") or {}
    if timings and not any(isinstance(v, dict) for v in timings.values()):
        # v1.0 had one flat list (Blood Awakening only): split it into Shared + Blood Awakening.
        shared_keys = {f.key for f in FIELDS["Shared"]}
        timings = {"Shared": {k: v for k, v in timings.items() if k in shared_keys},
                   "Blood Awakening": {k: v for k, v in timings.items() if k not in shared_keys}}
    for sec in TIMING_SECTIONS:
        saved_sec = timings.get(sec) if isinstance(timings.get(sec), dict) else {}
        for f in FIELDS[sec]:
            if f.key not in saved_sec:
                continue
            v = clean_spot(saved_sec[f.key]) if f.kind == "spot" else clean_value(f, saved_sec[f.key])
            if v is not None:
                cfg["timings"][sec][f.key] = v
    for sec in ("Blood Awakening", "Shiki", "Universal"):
        saved_sec = timings.get(sec) if isinstance(timings.get(sec), dict) else {}
        if "smart_a4" not in saved_sec and cfg["timings"][sec].get("smart_shift"):
            cfg["timings"][sec]["smart_a4"] = True  # had the speed preset before this option existed

    fs = saved.get("failsafe") or {}
    for name in ("enabled", "look_down"):
        if isinstance(fs.get(name), bool):
            cfg["failsafe"][name] = fs[name]
    for name, lo, hi in (("seconds", 10, 3600), ("look_time", 0.1, 10), ("look_pixels", 1, 200)):
        try:
            v = float(fs.get(name))
            if lo <= v <= hi:
                cfg["failsafe"][name] = v
        except (TypeError, ValueError):
            pass
    if clean_spot([fs.get("click_x"), fs.get("click_y")]):
        cfg["failsafe"]["click_x"], cfg["failsafe"]["click_y"] = fs["click_x"], fs["click_y"]

    app = saved.get("app") or {}
    for name in ("mini_bar", "minimize_on_start", "focus_roblox", "grab_check", "track_loot", "close_roblox_at_end"):
        if isinstance(app.get(name), bool):
            cfg["app"][name] = app[name]
    if isinstance(app.get("stop_runs"), int) and not isinstance(app.get("stop_runs"), bool) and 0 <= app["stop_runs"] <= 100000:
        cfg["app"]["stop_runs"] = app["stop_runs"]
    if isinstance(app.get("stop_hours"), (int, float)) and not isinstance(app.get("stop_hours"), bool) \
            and 0 <= app["stop_hours"] <= 72:
        cfg["app"]["stop_hours"] = float(app["stop_hours"])
    if app.get("theme") in THEMES:
        cfg["app"]["theme"] = app["theme"]
    if isinstance(app.get("accent"), str) and (app["accent"] == "" or HEX_COLOR.match(app["accent"])):
        cfg["app"]["accent"] = app["accent"]
    if isinstance(app.get("monitor"), int) and app["monitor"] >= 0:
        cfg["app"]["monitor"] = app["monitor"]

    dc = saved.get("discord") or {}
    if dc.get("mode") in ("off", "webhook", "bot"):
        cfg["discord"]["mode"] = dc["mode"]
    for name in ("url", "bot_token", "channel_id", "user_id"):
        if isinstance(dc.get(name), str):
            cfg["discord"][name] = dc[name].strip()
    for name in ("mention", "notify_mission", "screenshot", "notify_failsafe", "notify_error", "notify_reconnect",
                 "notify_graph"):
        if isinstance(dc.get(name), bool):
            cfg["discord"][name] = dc[name]

    rc = saved.get("reconnect") or {}
    if isinstance(rc.get("enabled"), bool):
        cfg["reconnect"]["enabled"] = rc["enabled"]
    valid_spots = {k for k, _ in RECONNECT_SHARED_SPOTS} | {k for tab in RECONNECT_TAB_SPOTS.values() for k, _ in tab}
    for name, val in (rc.get("spots") or {}).items():
        if name in valid_spots and clean_spot(val):
            cfg["reconnect"]["spots"][name] = clean_spot(val)
    for name in ("click_delay", "play_delay"):
        try:
            v = float(rc.get(name))
            if 0 <= v <= 60:
                cfg["reconnect"][name] = v
        except (TypeError, ValueError):
            pass

    cfg["optimiser"] = load_optimiser(saved.get("optimiser"))
    for name in ("start_scale", "rage_scale"):
        ss_ = saved.get(name)
        if isinstance(ss_, (int, float)) and 0.5 <= ss_ <= 2:
            cfg[name] = float(ss_)
    rs = saved.get("retry_scale")
    if isinstance(rs, (int, float)) and 0.5 <= rs <= 2:
        cfg["retry_scale"] = float(rs)

    st = saved.get("stats") or {}
    for fam in ("missions", "raids"):
        src = st.get(fam) or {}
        for name in ("runs", "retries", "completed", "failed", "rescues"):
            try:
                cfg["stats"][fam][name] = max(0, int(src.get(name, 0)))
            except (TypeError, ValueError):
                pass
        for kind in LOOT_KINDS:
            try:
                cfg["stats"][fam]["loot"][kind] = max(0, int((src.get("loot") or {}).get(kind, 0)))
            except (TypeError, ValueError):
                pass
    best = st.get("best") if isinstance(st.get("best"), dict) else {}
    for routine, val in best.items():
        if routine in ROUTINES and isinstance(val, (int, float)) and 1 <= val <= 36000:
            cfg["stats"]["best"][routine] = float(val)
    ln = saved.get("learned") if isinstance(saved.get("learned"), dict) else {}
    if isinstance(ln.get("shifted"), bool):
        cfg["learned"]["shifted"] = ln["shifted"]
    fd = ln.get("finder")
    if isinstance(fd, dict) and fd.get("knob") in ("strafe", "dash"):
        clean = {"knob": fd["knob"]}
        for name in ("base", "trial"):
            vals = fd.get(name) if isinstance(fd.get(name), list) else []
            clean[name] = [float(v) for v in vals if isinstance(v, (int, float)) and 1 <= v <= 36000][-10:]
        tv, pv = fd.get("trial_value"), fd.get("prev_value")
        if isinstance(tv, (int, float)) and isinstance(pv, (int, float)) and 0 <= tv <= 60 and 0 <= pv <= 60:
            clean["trial_value"], clean["prev_value"] = float(tv), float(pv)
        else:
            clean["trial"] = []
        cfg["learned"]["finder"] = clean
    old = saved.get("totals") or {}  # v1.0
    if old and not st:
        for name, new in (("missions", "runs"), ("retries", "retries"), ("rescues", "rescues")):
            try:
                cfg["stats"]["missions"][new] = max(0, int(old.get(name, 0)))
            except (TypeError, ValueError):
                pass
    # settings from a newer version are kept as they are (running an older copy must never wipe them)
    for k, v in saved.items():
        if k not in cfg and k != "totals":
            cfg[k] = v
    return cfg


_save_lock = threading.Lock()


def save_config(cfg):
    with _save_lock:
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            data = json.loads(json.dumps(cfg))  # snapshot (tuples -> lists)
            tmp = CONFIG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp, CONFIG_PATH)
            return True
        except Exception:
            return False


def reconnect_missing(cfg, raid):
    """What auto-reconnect still needs before it can work (empty list = ready)."""
    missing = [PICTURES[k]["label"] + " picture" for k in RECONNECT_PICTURES if not os.path.isfile(own_picture_path(k))]
    spots = cfg["reconnect"]["spots"]
    tab = "Raids" if raid else "Missions"
    for key, name in RECONNECT_SHARED_SPOTS:
        if not spots.get(key):
            missing.append(name)
    for key, name in RECONNECT_TAB_SPOTS[tab]:
        if not spots.get(key):
            missing.append("%s > %s" % (tab, name))
    return missing


# =============================================================================
#  Discord (webhook or bot)
# =============================================================================

DISCORD_API = "https://discord.com/api/v10"
DISCORD_UA = "DiscordBot (https://discord.com, 1.1) ColossalMacro"
BOT_PREFIX = "!"
BOT_POLL_SECONDS = 2.0
BOT_COMMANDS_TEXT = "!start  !pause  !resume  !stop  !reconnect  !screenshot  !stats  !graph  !status  !help"
COLOR_GOOD, COLOR_BAD, COLOR_NEUTRAL, COLOR_WARN = 0x39C97A, 0xEF5B5B, 0x8B92A5, 0xF0B23C


def webhook_valid(url):
    url = (url or "").strip()
    return url.startswith("https://") and "/api/webhooks/" in url


def discord_ids(raw):
    return [p for p in re.split(r"[,\s]+", (raw or "").strip()) if p.isdigit()]


def discord_ready(d):
    if d["mode"] == "webhook":
        return webhook_valid(d["url"])
    if d["mode"] == "bot":
        return len(d["bot_token"].strip()) >= 20 and d["channel_id"].strip().isdigit()
    return False


def build_discord_request(d, text="", embed=None, png=None, ping=False):
    """(url, body bytes, headers) for one message - kept separate so it can be checked without sending."""
    ids = discord_ids(d["user_id"])
    uid = ids[0] if (ping and d["mention"] and ids) else ""
    payload = {"content": (("<@%s> " % uid) if uid else "") + (text or ""),
               "allowed_mentions": {"users": [uid]} if uid else {"parse": []}}
    embeds = [dict(embed)] if embed else []
    if png:
        if not embeds:
            embeds = [{"title": "Screenshot", "color": COLOR_NEUTRAL}]
        embeds[0]["image"] = {"url": "attachment://screen.png"}
        payload["attachments"] = [{"id": 0, "filename": "screen.png"}]
    if embeds:
        payload["embeds"] = embeds
    headers = {"User-Agent": DISCORD_UA}
    if d["mode"] == "bot":
        url = "%s/channels/%s/messages" % (DISCORD_API, d["channel_id"].strip())
        headers["Authorization"] = "Bot " + d["bot_token"].strip()
    else:
        url = d["url"].strip()
    data = json.dumps(payload).encode("utf-8")
    if png:
        b = uuid.uuid4().hex
        body = b"".join([
            ("--%s\r\nContent-Disposition: form-data; name=\"payload_json\"\r\nContent-Type: application/json\r\n\r\n" % b).encode(),
            data, b"\r\n",
            ("--%s\r\nContent-Disposition: form-data; name=\"files[0]\"; filename=\"screen.png\"\r\nContent-Type: image/png\r\n\r\n" % b).encode(),
            png, b"\r\n", ("--%s--\r\n" % b).encode()])
        headers["Content-Type"] = "multipart/form-data; boundary=" + b
    else:
        body = data
        headers["Content-Type"] = "application/json"
    return url, body, headers


def discord_error_text(e):
    if isinstance(e, urllib.error.HTTPError):
        hints = {401: "the bot token is wrong", 403: "the bot can't post in that channel",
                 404: "the webhook / channel doesn't exist (check the URL or channel ID)", 429: "rate limited, slow down"}
        return "Discord said %d - %s" % (e.code, hints.get(e.code, "request refused"))
    return str(e)


class Discord:
    """Sends messages in the background and (bot mode) listens for !commands."""

    def __init__(self, cfg, log, on_command, monitor):
        self.cfg = cfg
        self.log = log
        self.on_command = on_command
        self.monitor = monitor          # () -> monitor dict, for screenshots
        self.q = queue.Queue()
        self._bot_stop = None
        self._bot_sig = None
        self._fail_logged = 0.0
        threading.Thread(target=self._worker, name="discord", daemon=True).start()

    def ready(self):
        return discord_ready(self.cfg["discord"])

    def send(self, text="", embed=None, screenshot=False, ping=False, png=None):
        """Queue a message. screenshot=True takes one when it is sent; png= sends that picture instead."""
        if self.ready():
            self.q.put((text, embed, screenshot, ping, png, None, None))

    def test(self, d, done):
        """Send a test message with the (maybe unsaved) settings `d`; done(ok, message) runs on this thread."""
        if not discord_ready(d):
            done(False, "Fill in a webhook URL, or a bot token + channel ID first")
            return
        self.q.put(("Test message from Colossal Macro - notifications work.", None, False, True, None, dict(d), done))

    def _worker(self):
        while True:
            text, embed, screenshot, ping, png, d, done = self.q.get()
            try:
                if screenshot and png is None:
                    try:
                        png = screenshot_png(self.monitor())
                    except Exception as e:
                        self.log("Discord: no screenshot (%s)" % e)
                self._post(d or self.cfg["discord"], text, embed, png, ping)
                if done:
                    done(True, "Sent - check your Discord")
            except Exception as e:
                msg = discord_error_text(e)
                if done:
                    done(False, msg)
                elif time.time() - self._fail_logged > 60:
                    self._fail_logged = time.time()
                    self.log("Discord: message not sent (%s)" % msg)

    def _post(self, d, text, embed, png, ping):
        for attempt in range(3):
            url, body, headers = build_discord_request(d, text, embed, png, ping)
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    r.read()
                return
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:
                    try:
                        wait_s = float(json.loads(e.read().decode("utf-8") or "{}").get("retry_after", 2))
                    except Exception:
                        wait_s = 2.0
                    time.sleep(min(30.0, wait_s))
                    continue
                raise

    # ---- bot commands ----------------------------------------------------------------------------
    def restart_bot(self):
        d = self.cfg["discord"]
        sig = (d["mode"], d["bot_token"].strip(), d["channel_id"].strip())
        if sig == self._bot_sig:
            return
        self._bot_sig = sig
        if self._bot_stop is not None:
            self._bot_stop.set()
            self._bot_stop = None
        if d["mode"] == "bot" and discord_ready(d):
            stop = threading.Event()
            self._bot_stop = stop
            threading.Thread(target=self._bot_loop, args=(stop, sig[1], sig[2]), name="discord-bot", daemon=True).start()

    def _api_get(self, path, token):
        req = urllib.request.Request(DISCORD_API + path, headers={"Authorization": "Bot " + token, "User-Agent": DISCORD_UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8") or "[]")

    def _bot_loop(self, stop, token, channel):
        last = None
        warned = {}
        while not stop.is_set():
            try:
                if last is None:
                    first = self._api_get("/channels/%s/messages?limit=1" % channel, token)
                    last = int(first[0]["id"]) if first else 0
                    self.log("Discord bot: listening for commands (%s)" % BOT_COMMANDS_TEXT)
                else:
                    msgs = self._api_get("/channels/%s/messages?after=%d&limit=20" % (channel, last), token)
                    for m in sorted(msgs, key=lambda m: int(m["id"])):
                        last = max(last, int(m["id"]))
                        self._handle(m, warned)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    try:
                        stop.wait(min(30.0, float(json.loads(e.read().decode("utf-8") or "{}").get("retry_after", 5))))
                    except Exception:
                        stop.wait(5)
                    continue
                self.log("Discord bot: %s - check Settings > Discord" % discord_error_text(e))
                stop.wait(60)
                continue
            except Exception:
                stop.wait(10)
                continue
            stop.wait(BOT_POLL_SECONDS)

    def _handle(self, m, warned):
        author = m.get("author") or {}
        if author.get("bot"):
            return
        text = (m.get("content") or "").strip()
        if not text:
            if not warned.get("empty") and not m.get("attachments") and not m.get("embeds"):
                warned["empty"] = True
                self.send("I can't read messages yet: turn on MESSAGE CONTENT INTENT for the bot "
                          "(Discord Developer Portal > your app > Bot).")
            return
        if not text.startswith(BOT_PREFIX) or len(text) < 2:
            return
        cmd = text[1:].split()[0].lower()
        allowed = discord_ids(self.cfg["discord"]["user_id"])
        if str(author.get("id")) not in allowed:
            if not allowed and not warned.get("noid"):
                warned["noid"] = True
                self.send("Commands are off: put your Discord user ID in Colossal Macro > Settings > Discord first.")
            return
        self.on_command(cmd)


# =============================================================================
#  The macro itself (runs in its own thread)
# =============================================================================

ROUTINE_STEPS = {
    "Blood Awakening": ["Ability 2", "Dashing", "Strafe left", "Shift", "Shifted 4", "Ability 5", "Retry"],
    "Shiki": ["Ability 2", "Dashing", "Strafe", "Ability 3", "Buying time", "Ability 4", "Shift", "Shifted 4",
              "Ability 5", "Retry"],
    "Universal": ["Ability 2", "Dashing", "Strafe", "Ability 3", "Looking down", "Ability 4", "Shift", "Shifted 4",
                  "Ability 5", "Retry"],
    "Female Raid": ["Using buffs", "Shifting", "Killing Eren", "Killing Female", "Opening chests", "Retry"],
}
SCAN_INTERVAL = 0.5
FAST_SCAN_INTERVAL = 0.1
FULL_SCAN_EVERY = 3             # full-screen retry search every 3rd scan (1.5s) until retry has been seen once
FULL_SCAN_EVERY_FAST = 8        # fast mode: every 8th (0.8s)
FULL_SCAN_EVERY_SEEN = 8        # once its spot is known the tiny check covers it: full search every 8th (4s)
FULL_SCAN_EVERY_SEEN_FAST = 30  # fast mode: every 30th (3s)
START_FULL_EVERY = 3            # mission start: full-screen search every 3rd look until the icon has been seen once
START_FULL_EVERY_SEEN = 10      # ...after that the icon's spot is checked and a full search runs every 10th look
GRAB_LOOK_INTERVAL = 1.5        # how often the 'streak in danger' text is looked for
HANDS_OFF_MIN = 1.0
RETRY_RECLICK_AFTER = 3.0
RETRY_CONFIRM_DELAY = 0.3
START_SETTLE_DELAY = 1.0
TITAN_SCALES = (0.9, 0.95, 1.0, 1.05, 1.1)  # sizes tried for the titan bar icons (they're found near the speedometer)
SHIFT_LOOK_INTERVAL = 0.2       # smart shift: how often the titan bar is looked for
A4_MIN_GOLD = 0.08              # ability 4 icon: it has to be seen lit up (ready) first...
A4_FIRED_RATIO = 0.5            # ...then 'used' = its gold pixels dropped to half of the brightest seen...
A4_FIRED_LOOKS = 2              # ...on this many looks in a row
A4_SAFETY_EVERY = 2.0           # after the spam was cut short, ability 5's loop still taps ability 4 this often...
A4_SAFETY_TIME = 8.0            # ...for this long, in case it hadn't really gone off
LEARN_MAX_TRIES = 3             # auto-learn tries per session for the Shifted picture
LEARN_STABLE_AFTER = 0.3        # the titan bar spot is looked at again this much later: it must not have changed
FINDER_RUNS = 3                 # Speed finder: runs per try
FINDER_STEP = 1.0               # ...seconds taken off per try
FINDER_KNOBS = {"strafe": ("Blood Awakening", "strafe_left_time", "Strafe left time", 2.0, "dash"),
                "dash": ("Shared", "dash_time", "Dash spam time", 3.0, "done")}  # section, key, label, floor, next
ICON_GONE_TIMEOUT = 20.0
FOLLOW_WINDOW_EVERY = 3.0      # while waiting for a mission: check the Roblox window's spot this often
START_HINT_AFTER = 45.0        # no start icon this long -> say once what is being looked for
RESCAN_RETRY_AFTER = 25.0       # still no mission this long after a retry click -> look for retry again
GRAB_REPEAT = 1.0
LOOT_SCAN_TIME = 1.0
LOOT_SCAN_STEP = 0.25
RESCUE_SPAM_TIME = 5.0
RESCUE_SPAM_INTERVAL = 0.1
RESCUE_WAIT_START = 2.0
RESCUE_WAIT = 15.0
RESCUE_CLICK_DELAY = 0.5
SHIFT_LOCK_HOLD = 0.06
SHIFT_LOCK_SETTLE = 0.15
RAID_LOOK_INTERVAL = 0.25
RAID_SKIP_FIRST_SPAM_TIME = 0.5
RAID_FAILSAFE_MAX_TIME = 180.0
RAID_FAILSAFE_AFTER_SEQUENCE = 180.0
RAID_FINISH_LOOK = 0.1
RAID_HEATWAVE_MISSES = 3
RECONNECT_CHECK_INTERVAL = 2.0
RECONNECT_CLOSE_WAIT = 3.0
RECONNECT_LOAD_WAIT = 25.0
RECONNECT_COOLDOWN = 60.0
RECONNECT_FIRST_DELAY = 2.0
RECONNECT_RESCUE_LIMIT = 120.0
RECONNECT_IMAGE_TIMEOUT = 120.0
RECONNECT_MAX_ATTEMPTS = 3


class StopMacro(Exception):
    pass


class RetryFound(Exception):
    def __init__(self, match, shot=None):
        super().__init__("retry")
        self.match = match
        self.shot = shot


class Disconnected(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class RaidFinished(Exception):
    pass


def median(vals):
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def fmt_run(seconds):
    """Run times with tenths: 0:31.4"""
    if seconds is None:
        return "-"
    m, sec = divmod(max(0.0, float(seconds)), 60)
    return "%d:%04.1f" % (m, sec)


def fmt_dur(seconds):
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)


def loot_text(found):
    if not found:
        return "nothing"
    return ", ".join(LOOT_SHORT[k] if k in ("scroll", "vessel") else PICTURES[k]["label"] for k in LOOT_KINDS if k in found)


class Engine:
    def __init__(self, cfg, out, discord=None):
        self.cfg = cfg
        self.out = out          # queue to the window
        self.discord = discord
        self.thread = None
        self.quit = False
        self.paused = False
        self.manual_start = False
        self.state = "idle"
        self.held = set()
        self.mission_t0 = None
        self.rescuing = False
        self.rescued = False
        self.rescue_t0 = None
        self.last_scan = 0.0
        self.last_grab = 0.0
        self.det = None
        self.routine = cfg["routine"]
        self.raid_mode = self.routine == "Female Raid"
        self.raid = {}
        self.skip_until = 0.0
        self.skip_thread = None
        self.reconnect_on = False
        self.reconnecting = False
        self.rc_request = False
        self.rc_next = 0.0
        self.run_steps = []
        self.smart_warned = False
        self.human_bar = None       # the ability 2 slot at the mission start (auto-learn checks against it)
        self.learn_pending = None   # (box, pixels, time) of a titan bar picture waiting for its second look
        self.learn_tries = 0
        self.result_misses = 0
        self.result_hint = False
        self.end_reads = 0
        self.scans = 0
        self.last_grab_look = 0.0
        self.session = self._new_session()

    @staticmethod
    def _new_session():
        s = new_family_stats()
        s.update({"start": None, "lengths": [], "paused": 0.0, "history": []})
        return s

    @property
    def family(self):
        return "raids" if self.raid_mode else "missions"

    # ---- messages ------------------------------------------------------------------------------
    def log(self, text):
        self.out.put(("log", text))

    def set_status(self, status):
        self.state = status
        self.out.put(("status", status))

    def set_step(self, name):
        if name and self.mission_t0 is not None and (not self.run_steps or self.run_steps[-1][0] != name):
            self.run_steps.append((name, time.time()))  # for the per-step breakdown of this run
        self.out.put(("step", name))

    def show(self, title, detail=""):
        self.out.put(("show", title, detail))

    def detail(self, text):
        self.out.put(("detail", text))

    def stats_changed(self):
        self.out.put(("stats",))

    def notify(self, text="", embed=None, screenshot=False, ping=False, kind=None, png=None):
        if self.discord is None:
            return
        d = self.cfg["discord"]
        if kind and not d.get(kind, True):
            return
        self.discord.send(text, embed, screenshot, ping, png)

    def png_wanted(self):
        d = self.cfg["discord"]
        return self.discord is not None and self.discord.ready() and d["notify_mission"] and d["screenshot"]

    def end_screen_png(self, shot):
        """PNG of the end screen for the Discord message (the screenshot from when retry was seen), or None."""
        if shot is None:
            return None
        try:
            return png_from_raw(shot.raw, self.det.mon)
        except Exception:
            return None

    def count(self, name, n=1):
        self.session[name] += n
        self.cfg["stats"][self.family][name] += n
        self.stats_changed()

    # ---- settings ------------------------------------------------------------------------------
    def sh(self, name):
        return self.cfg["timings"]["Shared"][name]

    def rt(self, name):
        return self.cfg["timings"][self.routine][name]

    def fast(self):
        return bool(self.cfg["timings"][self.routine].get("fast_mode"))

    def k(self, name):
        return self.cfg["keys"][name]

    def timeout(self):
        return max(10.0, float(self.cfg["failsafe"]["seconds"]))

    # ---- control (called by the window) ------------------------------------------------------
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self):
        if self.running():
            return False
        self.quit = False
        self.paused = False
        self.manual_start = False
        self.rc_request = False
        self.routine = self.cfg["routine"]
        self.raid_mode = self.routine == "Female Raid"
        self.session = self._new_session()
        self.session["start"] = time.time()
        self.learn_tries = 0
        self.result_misses = 0
        self.result_hint = False
        self.end_reads = 0
        self.thread = threading.Thread(target=self._main, name="macro", daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.quit = True
        self.paused = False

    def toggle_pause(self):
        if self.running():
            self.paused = not self.paused
            return self.paused
        return False

    def request_manual_start(self):
        if self.running() and self.state == "waiting":
            self.manual_start = True

    # ---- keys --------------------------------------------------------------------------------
    def key_down(self, name):
        key_event(name, False)
        self.held.add(name)

    def key_up(self, name):
        key_event(name, True)
        self.held.discard(name)

    def release_held(self):
        for name in list(self.held):
            try:
                key_event(name, True)
            except Exception:
                pass
        self.held.clear()

    def release_all(self):
        names = set(self.held)
        names.update(v for k, v in self.cfg["keys"].items() if k not in HOTKEYS)
        for name in names:
            try:
                key_event(name, True)
            except Exception:
                pass
        self.held.clear()

    # ---- the heartbeat: stop / pause / reconnect / failsafe / retry detection ------------------
    def tick(self, scan=True):
        """Returns how many seconds were spent paused (0 normally)."""
        if self.quit:
            raise StopMacro()
        paused_for = 0.0
        if self.paused:
            t0 = time.time()
            self.release_held()
            prev = self.state
            self.set_status("paused")
            self.log("Paused - press %s to resume" % key_display(self.k("pause")))
            while self.paused:
                if self.quit:
                    raise StopMacro()
                time.sleep(0.1)
            paused_for = time.time() - t0
            self.session["paused"] += paused_for
            if self.mission_t0 is not None:
                self.mission_t0 += paused_for  # paused time doesn't count toward the failsafe
            self.set_status(prev)
            self.log("Resumed")
        if cursor_pos() == (0, 0):
            self.log("Mouse is in the top-left corner - emergency stop")
            raise StopMacro()
        now = time.time()
        if self.reconnect_on and not self.reconnecting:
            if self.rc_request:
                self.rc_request = False
                raise Disconnected("the !reconnect command was used")
            if self.rescuing and self.rescue_t0 and now - self.rescue_t0 > RECONNECT_RESCUE_LIMIT:
                raise Disconnected("the failsafe has been running for %g minutes" % (RECONNECT_RESCUE_LIMIT / 60))
            if now >= self.rc_next:
                self.rc_next = now + RECONNECT_CHECK_INTERVAL
                if self.det.look("disconnect") is not None:
                    raise Disconnected("the Disconnected message was seen")
        if not scan:
            return paused_for
        if (not self.raid_mode and self.cfg["failsafe"]["enabled"] and not self.rescuing
                and self.mission_t0 is not None and now - self.mission_t0 > self.timeout()):
            self.rescue()
        if self.raid_mode and self.raid.get("active") and not self.raid.get("in_raid_wait") and not self.rescuing:
            self.raid_skip_poll()
        interval = FAST_SCAN_INTERVAL if self.fast() else SCAN_INTERVAL
        if time.time() - self.last_scan >= interval:
            self.scan_for_retry()
        return paused_for

    def wait(self, seconds, scan=True):
        end = time.time() + max(0.0, seconds)
        while True:
            end += self.tick(scan)
            remaining = end - time.time()
            if remaining <= 0:
                return
            time.sleep(min(0.05, remaining))

    def tap(self, name):
        self.key_down(name)
        try:
            self.wait(random.uniform(0.03, 0.07), scan=False)
        finally:
            self.key_up(name)

    def double_tap(self, name):
        self.tap(name)
        self.wait(random.uniform(*self.sh("tap_gap")), scan=False)
        self.tap(name)

    def spam_key_for(self, name, seconds, interval, label, waiter=None):
        waiter = waiter or self.wait
        end = time.time() + seconds
        while True:
            remaining = end - time.time()
            if remaining <= 0:
                return
            self.detail("Spamming %s... %.0fs left" % (label, remaining))
            self.tap(name)
            waiter(min(interval, max(remaining, 0.01)))

    # ---- screen checks -----------------------------------------------------------------------
    def scan_for_retry(self):
        """Is the retry button up? Usually a tiny screenshot of where it was last time; a full-screen search
        only every few scans (that's what kept the CPU busy before)."""
        self.last_scan = time.time()
        self.scans += 1
        fast = self.fast()
        m = self.det.roi_find("retry") or self.det.roi_find("retry_alt")
        shot = None
        if "retry" in self.det.hints or "retry_alt" in self.det.hints:
            every = FULL_SCAN_EVERY_SEEN_FAST if fast else FULL_SCAN_EVERY_SEEN
        else:
            every = FULL_SCAN_EVERY_FAST if fast else FULL_SCAN_EVERY
        if m is None and self.scans % every == 0:
            shot = self.det.grab()
            if shot is None:
                return
            m = self.det.find_retry(shot)
        if (self.cfg["app"]["grab_check"] and not self.raid_mode and self.mission_t0 is not None
                and time.time() - self.last_grab_look >= GRAB_LOOK_INTERVAL):
            self.last_grab_look = time.time()
            self.check_grabbed(shot)
        if not m:
            return
        if fast:
            raise RetryFound(m, shot if shot is not None else self.det.grab())
        time.sleep(RETRY_CONFIRM_DELAY)
        again = self.det.roi_find("retry") or self.det.roi_find("retry_alt")
        if again and abs(again.cx - m.cx) < 20 * self.det.scale and abs(again.cy - m.cy) < 20 * self.det.scale:
            raise RetryFound(again, None)

    def check_grabbed(self, shot=None):
        if time.time() - self.last_grab < GRAB_REPEAT:
            return
        found = self.det.roi_find("grab")
        if found is None:
            if shot is None:
                shot = self.det.grab()
            found = self.det.find_grab(shot) if shot is not None else None
        if found:
            self.last_grab = time.time()
            self.log("Streak in danger - pressing %s" % key_display(self.k("ability1")))
            self.tap(self.k("ability1"))

    # ---- mouse helpers -----------------------------------------------------------------------
    def press_lock(self, hold=SHIFT_LOCK_HOLD):
        name = self.k("lock")
        self.key_down(name)
        try:
            self.pause_for(hold)
        finally:
            self.key_up(name)

    def pause_for(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.tick(False)
            time.sleep(0.005)

    def fix_shift_lock(self):
        self.press_lock(SHIFT_LOCK_HOLD)
        self.pause_for(SHIFT_LOCK_SETTLE)

    def look_up(self, total, pixels):
        press, lock_wait, unlock_wait = 0.06, 0.08, 0.1
        move = max(0.05, total - 2 * press - lock_wait - unlock_wait)
        self.press_lock(press)
        self.pause_for(lock_wait)
        steps = max(1, int(move / 0.01))
        done = 0
        for i in range(1, steps + 1):
            self.tick(False)
            target = int(round(pixels * i / steps))
            if target > done:
                mouse_move_rel(0, -(target - done))
                done = target
            time.sleep(move / steps)
        self.press_lock(press)
        self.pause_for(unlock_wait)

    def look_down(self, seconds, pixels, step=0.01, settle=0.15):
        self.press_lock()
        self.pause_for(0.15)
        end = time.time() + seconds
        while time.time() < end:
            self.tick(False)
            mouse_move_rel(0, pixels)
            time.sleep(step)
        self.press_lock()
        if settle > 0:
            self.pause_for(settle)

    def click_spot(self, x, y):
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.05)
        mouse_move_rel(0, 1)  # Roblox only notices the cursor after a real move
        time.sleep(0.05)
        mouse_click()

    def park_cursor(self):
        """Move the mouse off the game's buttons after clicking. AOTR draws its own cursor where the mouse is, and
        left on RETRY it covers the word, so the next end screen's RETRY can't be seen."""
        if self.det is None:
            return
        m = self.det.mon
        user32.SetCursorPos(m["left"] + max(8, int(m["width"] * 0.03)), m["top"] + int(m["height"] * 0.5))
        time.sleep(0.02)
        mouse_move_rel(0, 1)  # a real move, so the game moves its cursor too

    def click_spam(self, x, y, seconds, interval, jitter=0, label="", between=None):
        if jitter:
            x += random.randint(-jitter, jitter)
            y += random.randint(-jitter, jitter)
        user32.SetCursorPos(int(x), int(y))
        time.sleep(random.uniform(0.08, 0.2))
        mouse_move_rel(0, 1)
        time.sleep(0.05)
        end = time.time() + seconds
        while True:
            if self.quit:
                raise StopMacro()
            mouse_click()
            remaining = end - time.time()
            if remaining <= 0:
                self.park_cursor()
                return
            if label:
                self.detail("Clicking %s... %.0fs left" % (label, remaining))
            t_click = time.time()
            if between is not None:
                between()
            time.sleep(max(0.0, min(interval, remaining) - (time.time() - t_click)))

    def failsafe_point(self):
        fs = self.cfg["failsafe"]
        if fs["click_x"] is not None and fs["click_y"] is not None:
            return fs["click_x"], fs["click_y"], "the picked spot"
        m = self.det.mon
        return m["left"] + m["width"] // 2, m["top"] + int(m["height"] * 0.8), "bottom-middle (50% X, 80% Y)"

    # ---- waiting for a mission ---------------------------------------------------------------
    def follow_window(self):
        """Windowed Roblox moved or was resized (or went fullscreen): watch the new spot. A new size can change the
        game's button sizes, so those are learned again."""
        region = game_region(pick_monitor(self.cfg))
        old = self.det.mon
        if all(region.get(k) == old.get(k) for k in ("left", "top", "width", "height")):
            return
        resized = (region["width"], region["height"]) != (old["width"], old["height"])
        self.det.close()
        if resized:
            self.cfg["retry_scale"] = None
            self.cfg["start_scale"] = None
            self.cfg["rage_scale"] = None
            self.out.put(("save",))
        self.det = Detector(self.cfg, self.log, save_cb=lambda: self.out.put(("save",)), mon=region)
        self.log("Roblox window %s - now watching %dx%d" % ("resized" if resized else "moved", region["width"],
                                                          region["height"]))

    def wait_for_mission_start(self, scan_retry):
        self.set_status("waiting")
        try:
            self.follow_window()
        except Exception as e:
            self.log("Could not follow the Roblox window (%s)" % e)
        self.set_step(None)
        if self.raid_mode:
            self.show("Waiting for the raid", "Looking for the skip button / raid start")
            self.log("Waiting for the raid to start (skip button / raid start picture)")
        else:
            self.show("Waiting for the mission", "Looking for the ability 2 icon")
            self.log("Waiting for the mission to start")
        waited_from = time.time()
        fast = self.fast()
        next_follow, hinted = waited_from + FOLLOW_WINDOW_EVERY, False
        while True:
            self.tick(scan=scan_retry or time.time() - waited_from > RESCAN_RETRY_AFTER)
            now = time.time()
            if now >= next_follow:
                # The window can be moved / resized while the next mission loads: keep watching the right spot.
                next_follow = now + FOLLOW_WINDOW_EVERY
                try:
                    self.follow_window()
                except Exception as e:
                    self.log("Could not follow the Roblox window (%s)" % e)
            if not hinted and not self.raid_mode and now - waited_from > START_HINT_AFTER:
                hinted = True
                rage = self.routine == "Universal" and self.rt("rage")
                self.log("Still waiting: the %s isn't showing on key 2 yet. If a mission is already running, check "
                         "that it is on key 2 and visible (or press %s to start by hand)"
                         % ("Order: Rage icon" if rage else "ability 2 icon (speedometer)", key_display(self.k("start"))))
            if self.manual_start:
                self.manual_start = False
                self.log("Manual start")
                return
            if self.cfg["app"].get("stop_hours"):
                reason = self.limit_reason()
                if reason:
                    self.end_session(reason)
            seen_before = any(k in self.det.hints for k in self.det.start_keys(self.raid_mode))
            if self.det.start_visible(self.raid_mode, START_FULL_EVERY_SEEN if seen_before else START_FULL_EVERY):
                self.log("Raid started" if self.raid_mode else "Mission started (ability 2 icon seen)")
                if not fast and not self.raid_mode:
                    self.wait(START_SETTLE_DELAY, scan=False)
                return
            time.sleep(0.1 if fast else 0.2)

    def focus_game(self):
        if not self.cfg["app"]["focus_roblox"]:
            return
        try:
            result = focus_roblox()
        except Exception:
            result = False
        if result is False:
            self.log("Could not bring Roblox to the front - click into the game")

    def begin_run(self):
        self.mission_t0 = time.time()
        self.run_steps = []
        self.rescued = False
        self.learn_pending = None
        self.human_bar = None
        if not self.raid_mode and self.det is not None:
            slot = self.det.slot2_box()
            if slot is not None:
                self.human_bar = self.det.grab_box(*self.det.box_around(*slot))[0]
        self.count("runs")
        self.set_status("running")
        self.focus_game()
        self.finder_apply()

    # ---- missions (Blood Awakening / Shiki / Universal) ----------------------------------------
    def run_mission(self):
        self.begin_run()
        r = self.routine
        if self.sh("fix_shift_lock"):
            self.show("Fixing shift lock", "%s once" % key_display(self.k("lock")))
            self.log("Fix shift lock: %s pressed once" % key_display(self.k("lock")))
            self.fix_shift_lock()

        self.set_step("Ability 2")
        look_time = self.sh("look_up_time") if self.sh("no_bicorn") else 0.0
        if self.rt("skip_ability2"):
            self.show("Ability 2", "Skipped (Skip ability 2 is on)")
            self.log("Ability 2 skipped")
        else:
            self.show("Ability 2", "Pressing %s" % key_display(self.k("ability2")))
            self.log("Ability 2")
            self.tap(self.k("ability2"))
            self.wait(max(0.0, self.sh("after_ability2") - look_time))  # the look up is the end of this wait
        if look_time:
            self.show("Looking up", "So the dash goes up - shift lock, mouse up, shift lock")
            self.log("No Feathered Bicorn: looking up before dashing (%gs, %dpx)" % (look_time, self.sh("look_up_pixels")))
            self.look_up(look_time, self.sh("look_up_pixels"))

        self.set_step("Dashing")
        self.log("Dashing for %gs" % self.sh("dash_time"))
        self.spam_dash(self.sh("dash_time"))

        left = self.k("left")
        if r == "Blood Awakening":
            self.set_step("Strafe left")
            left_time = self.rt("strafe_left_time")
            if left_time > 0:
                self.show("Strafe left", "Strafing %s for %gs" % (key_display(left), left_time))
                self.log("Strafing left (%s) for %gs" % (key_display(left), left_time))
                end = time.time() + left_time
                next_strafe = time.time()
                while True:
                    now = time.time()
                    remaining = end - now
                    if remaining <= 0:
                        break
                    self.detail("Strafing left... %.0fs left" % remaining)
                    if now >= next_strafe:
                        self.double_tap(left)
                        next_strafe = time.time() + random.uniform(*self.rt("strafe_gap"))
                    self.wait(0.05, scan=False)
            self.log("Going to the ability 5 shift")
        else:
            self.set_step("Strafe")
            self.show("Strafe", "Double-tap %s" % key_display(left))
            self.double_tap(left)
            self.wait(self.rt("after_strafe"), scan=False)
            self.set_step("Ability 3")
            self.show("Ability 3")
            self.log("Ability 3")
            self.tap(self.k("ability3"))
            if r == "Universal":
                self.set_step("Looking down")
                self.show("Looking down", "Shift lock, mouse down, shift lock")
                self.log("Universal: looking down")
                self.look_down(self.rt("look_time"), self.rt("look_pixels"), settle=0)
                self.set_step("Ability 4")
                self.show("Ability 4", "Spamming ability 4 for %gs" % self.rt("ability4_time"))
                self.log("Ability 4 spam for %gs" % self.rt("ability4_time"))
                self.spam_key_for(self.k("ability4"), self.rt("ability4_time"), self.rt("ability4_interval"), "ability 4")
                self.wait(self.rt("after_ability"))
            else:
                self.set_step("Buying time")
                self.show("Buying time", "Strafing %s until ability 4 is off cooldown" % key_display(left))
                self.log("Buying time for %.0fs (ability 4 cooldown)" % self.rt("cooldown"))
                icon_seen = self.buy_time()
                self.set_step("Ability 4")
                if icon_seen:
                    self.show("Ability 4", "Icon seen - spamming ability 4 for %gs" % self.rt("ability4_time"))
                    self.log("Ability 4 spam for %gs (icon seen)" % self.rt("ability4_time"))
                    self.spam_key_for(self.k("ability4"), self.rt("ability4_time"), self.rt("ability4_interval"), "ability 4")
                else:
                    self.show("Ability 4")
                    self.log("Ability 4")
                    self.tap(self.k("ability4"))
                self.wait(self.rt("after_ability"))
        self.shift_sequence()

    def buy_time(self):
        """Strafe for the length of ability 4's cooldown. True when the Shiki ability 4 icon showed early."""
        start = time.time()
        total = self.rt("cooldown") + self.rt("cooldown_margin")
        next_strafe = start
        next_look = start + self.rt("icon_after")
        use_icon = self.det.has("shiki4")
        left = self.k("left")
        while True:
            now = time.time()
            remaining = total - (now - start)
            if remaining <= 0:
                return False
            if use_icon and now >= next_look:
                next_look = now + self.rt("icon_interval")
                if self.det.look("shiki4", 2, threshold=self.rt("icon_threshold")) is not None:
                    self.log("Shiki ability 4 icon seen")
                    return True
            self.detail("Strafing %s... ability 4 ready in %.0fs" % (key_display(left), remaining))
            if now >= next_strafe:
                self.double_tap(left)
                next_strafe = time.time() + random.uniform(*self.rt("strafe_gap"))
            self.wait(0.05)

    def spam_dash(self, seconds):
        name = self.k("dash")
        end = time.time() + seconds
        while True:
            remaining = end - time.time()
            if remaining <= 0:
                return
            self.show("Dashing", "Spamming %s... %.0fs left" % (key_display(name), remaining))
            self.key_down(name)
            try:
                self.wait(random.uniform(*self.sh("dash_hold")), scan=False)
            finally:
                self.key_up(name)
            if time.time() >= end:
                return
            self.wait(random.uniform(*self.sh("dash_gap")), scan=False)

    def shift_sequence(self):
        key5 = self.k("ability5")
        spam_interval = self.rt("shift_spam_interval")
        self.set_step("Shift")
        self.show("Shift", "Spamming ability 5 so the shift is used")
        seen = None
        if self.rt("smart_shift") and self.det.has("shifted"):
            seen = self.smart_shift(key5, spam_interval)
        else:
            if self.rt("smart_shift") and not self.smart_warned:
                self.smart_warned = True
                self.log("Smart shift wait is on, but the 'Shifted' picture could not be loaded - using the fixed wait")
            self.fixed_shift(key5, spam_interval)
        self.learn_begin(seen)

        self.set_step("Shifted 4")
        self.show("Shifted 4", "Spamming shifted ability 4")
        early = self.spam_shifted4()
        self.show("Shifted 4", "Waiting %gs before ability 5" % self.rt("shifted4_to5"))
        self.wait(self.rt("shifted4_to5"))

        self.set_step("Ability 5")
        move = self.sh("move_shifted")
        hold = self.k("right") if move == "Right" else self.k("left") if move == "Left" else None
        hold_txt = ("holding " + key_display(hold)) if hold else "standing still"
        self.log("Ability 5 over and over + %s, until the mission ends" % hold_txt)
        interval5 = self.rt("ability5_interval")
        key4 = self.k("ability4")
        presses = 0
        next5 = time.time()
        safety_until = time.time() + A4_SAFETY_TIME if early else 0.0
        next4 = time.time() + min(0.5, interval5 / 2.0)
        released = False
        try:
            while True:
                now = time.time()
                timed_out = (self.cfg["failsafe"]["enabled"] and self.mission_t0 is not None
                             and now - self.mission_t0 > self.timeout())
                if hold:
                    if timed_out:
                        if not released:
                            self.key_up(hold)
                            released = True
                    elif hold not in self.held:  # first time, or again after a pause
                        self.key_down(hold)
                if now >= next5:
                    presses += 1
                    self.show("Ability 5", "Pressed x%d + %s - until the mission ends" % (presses, hold_txt))
                    self.tap(key5)
                    next5 = time.time() + interval5
                elif now < safety_until and now >= next4:
                    self.tap(key4)  # the ability 4 spam was cut short: one more try now and then, just in case
                    next4 = time.time() + A4_SAFETY_EVERY
                if self.learn_pending is not None:
                    self.learn_finish()  # still shifted here: the auto-learn's second look can happen now too
                self.wait(0.05)
        finally:
            if hold:
                try:
                    self.key_up(hold)
                except Exception:
                    pass

    def fixed_shift(self, key5, spam_interval):
        self.log("Ability 5 spam for %gs (shift)" % self.rt("shift_spam_time"))
        spam_end = time.time() + self.rt("shift_spam_time")
        while time.time() < spam_end:
            self.tap(key5)
            self.wait(spam_interval)

        self.log("Waiting %gs for the shift (then shifted ability 4)" % self.rt("shifted4_at"))
        shift_end = time.time() + self.rt("shifted4_at")
        extra_end = time.time() + self.rt("shift_spam_extra")
        while True:
            remaining = shift_end - time.time()
            if remaining <= 0:
                break
            self.show("Shift", "Waiting for the shift... %.0fs" % remaining)
            if time.time() < extra_end:
                self.tap(key5)
                self.wait(min(spam_interval, remaining))
            else:
                self.wait(min(0.5, remaining))

    def shift_visible(self):
        """Match of the 'Shifted' picture, or None. Looks only where the speedometer was (a tiny screenshot) when
        that spot is known - except for a picture you captured yourself, which may be anywhere on the screen."""
        slot = self.det.slot2_box()
        if slot is not None and (not self.det.own.get("shifted") or self.cfg["learned"].get("shifted")):
            return self.det.near_find("shifted", self.det.box_around(*slot, k=2.2), self.det.titan_scales())
        return self.det.look("shifted", 2)

    def smart_shift(self, key5, spam_interval):
        """Ability 5 until the 'Shifted' picture shows, then go on right away. Never longer than the fixed wait.
        Returns the Match when the shift was seen, else None."""
        if self.shift_visible() is not None:
            # Still human at this point, so the picture can't be right - don't trust it this run.
            self.log("The 'Shifted' picture already shows before the shift - using the fixed wait this run "
                     "(capture it again in Settings > Pictures > Smart waits if this keeps happening)")
            self.fixed_shift(key5, spam_interval)
            return None
        start = time.time()
        limit = start + self.rt("shift_spam_time") + self.rt("shifted4_at")
        spam_until = start + self.rt("shift_spam_time") + self.rt("shift_spam_extra")
        self.log("Ability 5 until the shift is seen (at most %gs)" % (limit - start))
        next_look = start + 0.3
        while True:
            now = time.time()
            if now >= limit:
                self.log("Shift picture not seen within %gs - going on" % (limit - start))
                return None
            if now >= next_look:
                next_look = now + SHIFT_LOOK_INTERVAL
                m = self.shift_visible()
                if m is not None:
                    self.log("Shift seen after %.1fs (%.1fs sooner than the fixed wait)" % (now - start, limit - now))
                    self.wait(self.rt("smart_shift_delay"))
                    return m
            self.show("Shift", "Waiting for the shift... %.0fs at most" % (limit - now))
            if now < spam_until:
                self.tap(key5)
                self.wait(min(spam_interval, max(0.01, limit - time.time())))
            else:
                self.wait(min(0.1, max(0.01, limit - time.time())))

    # ---- auto-learn: your own 'Shifted' picture ------------------------------------------------------------
    def learn_begin(self, seen):
        """Right after the shift, cut the titan bar's ability 2 slot (where the speedometer was) out of the screen.
        It becomes your own 'Shifted' picture once it passes the checks here and in learn_finish."""
        self.learn_pending = None
        if not self.rt("smart_shift") or self.learn_tries >= LEARN_MAX_TRIES:
            return
        if os.path.isfile(own_picture_path("shifted")):
            return  # you already have one (captured, or learned before)
        slot = self.det.slot2_box()
        if slot is None:
            return
        self.learn_tries += 1
        box = self.det.box_around(*slot)
        if seen is not None:  # the built-in picture was seen: cut exactly that
            box = self.det.box_around(seen.cx, seen.cy, seen.w, seen.h)
        pixels = self.det.grab_box(*box)[0]
        why = self.learn_reject(pixels)
        if why:
            self.log("Auto-learn: not saving the titan bar yet (%s) - trying again next run" % why)
            return
        self.learn_pending = (box, pixels, time.time())

    def learn_reject(self, pixels):
        """Why `pixels` can't be the titan bar's ability 2 slot, or None when it looks right."""
        if pixels is None:
            return "nothing on the screen there"
        if float(cv2.cvtColor(pixels, cv2.COLOR_BGR2GRAY).std()) < 12:
            return "that spot is plain"
        start = self.det.tpls("start", 1.0)
        if start:
            speedo = cv2.resize(start[0].full, (pixels.shape[1], pixels.shape[0]), interpolation=cv2.INTER_AREA)
            if same_score(pixels, speedo) >= 0.5:
                return "the speedometer is still there - not shifted yet"
        if same_score(pixels, self.human_bar) >= 0.5:
            return "it looks the same as before the shift"
        return None

    def learn_finish(self):
        """Second look at the same spot: only a still picture (the skill bar, not the game world) is kept."""
        box, pixels, t0 = self.learn_pending
        if time.time() - t0 < LEARN_STABLE_AFTER:
            return
        self.learn_pending = None
        again = self.det.grab_box(*box)[0]
        if same_score(pixels, again) < 0.9:
            self.log("Auto-learn: that spot keeps changing, so it isn't the skill bar - trying again next run")
            return
        try:
            os.makedirs(PICTURES_DIR, exist_ok=True)
            ok, buf = cv2.imencode(".png", pixels)
            if not ok:
                raise ValueError("PNG encoding failed")
            buf.tofile(own_picture_path("shifted"))
        except Exception as e:
            self.log("Auto-learn: could not save the picture (%s)" % e)
            return
        self.cfg["learned"]["shifted"] = True
        self.det.forget("shifted")
        self.out.put(("save",))
        self.log("Auto-learn: saved your 'Shifted' picture - from now on the shift wait ends the moment you're shifted")

    def spam_shifted4(self):
        """Shifted ability 4 spam. With 'Stop ability 4 spam once used' on it watches the ability 4 icon on the
        titan bar and stops once the icon dims (the attack went off). True when it stopped early."""
        key4 = self.k("ability4")
        total, interval = self.rt("shifted4_time"), self.rt("shifted4_interval")
        slot = self.det.slot2_box() if self.rt("smart_a4") and self.det.has("shifted4") else None
        self.log("Shifted ability 4 spam for %s%gs" % ("up to " if slot else "", total))
        start = time.time()
        end = start + total
        icon, next_find, peak, low = None, start, 0.0, 0
        while True:
            now = time.time()
            remaining = end - now
            if remaining <= 0:
                if slot is not None and icon is None:
                    self.log("Ability 4 icon not found on the titan bar - spammed the full %gs" % total)
                return False
            self.detail("Spamming shifted ability 4... %.0fs left" % remaining)
            self.tap(key4)
            if self.learn_pending is not None:
                self.learn_finish()
            if slot is not None:
                if icon is None and now >= next_find:
                    next_find = now + 0.3
                    cx, cy, w, h = slot  # ability 4 sits two slots right of ability 2
                    m = self.det.near_find("shifted4", (cx + 1.0 * w, cy - 0.85 * h, cx + 4.8 * w, cy + 0.85 * h),
                                           self.det.titan_scales())
                    if m is not None:
                        icon = self.det.box_around(m.cx, m.cy, m.w, m.h, 0.8)
                if icon is not None:
                    pixels = self.det.grab_box(*icon)[0]
                    if pixels is not None:
                        g = gold_share(pixels)
                        peak = max(peak, g)
                        low = low + 1 if peak >= A4_MIN_GOLD and g <= A4_FIRED_RATIO * peak else 0
                        if low >= A4_FIRED_LOOKS:
                            self.log("Shifted ability 4 went off after %.1fs - spam stopped (%.1fs sooner)"
                                     % (now - start, end - now))
                            return True
            self.wait(min(interval, max(remaining, 0.01)))

    # ---- Speed finder: shorter dash / strafe, kept only when runs really get faster -------------------------
    def finder_apply(self):
        """At a run start: while a shorter time is being tried, make sure it's the one in use."""
        if self.routine != "Blood Awakening":
            return
        st = self.cfg["learned"].get("finder") or {}
        spec = FINDER_KNOBS.get(st.get("knob"))
        trying = spec is not None and st.get("trial_value") is not None
        if not self.rt("speed_finder"):
            if st:
                if trying:  # it was turned off in the middle of a try: put the old time back
                    self.cfg["timings"][spec[0]][spec[1]] = st["prev_value"]
                    self.log("Speed finder is off - %s back to %gs" % (spec[2], st["prev_value"]))
                self.cfg["learned"]["finder"] = {}
                self.out.put(("save",))
            return
        if trying:
            self.cfg["timings"][spec[0]][spec[1]] = st["trial_value"]

    def finder_after_run(self, length, rescued, result):
        if self.routine != "Blood Awakening" or not self.rt("speed_finder"):
            return
        st = self.cfg["learned"].setdefault("finder", {})
        st.setdefault("knob", "strafe")
        st.setdefault("base", [])
        if FINDER_KNOBS.get(st["knob"]) is None:
            return
        label = FINDER_KNOBS[st["knob"]][2]
        bad = rescued or result == "failed" or not length
        if st.get("trial_value") is None:
            if not bad:
                st["base"].append(round(length, 2))
                del st["base"][:-FINDER_RUNS]
                if len(st["base"]) < FINDER_RUNS:
                    self.log("Speed finder: timing your current settings (%d/%d)" % (len(st["base"]), FINDER_RUNS))
                else:
                    self.finder_next(st)
        elif bad:
            self.finder_reject(st, "a run %s" % ("needed the failsafe" if rescued else "failed"))
        else:
            st.setdefault("trial", []).append(round(length, 2))
            n = len(st["trial"])
            if n < FINDER_RUNS:
                self.log("Speed finder: %s %gs - run %d/%d took %s" % (label, st["trial_value"], n, FINDER_RUNS,
                                                                        fmt_run(length)))
            else:
                old, new = median(st["base"]), median(st["trial"])
                if new <= old - FINDER_STEP / 2.0:
                    self.log("Speed finder: %s %gs is faster (%s vs %s) - kept" % (label, st["trial_value"],
                                                                                    fmt_run(new), fmt_run(old)))
                    st.update(base=st["trial"], trial=[], trial_value=None, prev_value=None)
                    self.finder_next(st)
                else:
                    self.finder_reject(st, "was not faster (%s vs %s)" % (fmt_run(new), fmt_run(old)))
        self.out.put(("save",))

    def finder_next(self, st):
        """Try the next shorter time, moving on to the next setting when one is at its lowest."""
        while True:
            spec = FINDER_KNOBS.get(st["knob"])
            if spec is None:
                self.finder_done()
                return
            sec, key, label, floor, nxt = spec
            cur = self.cfg["timings"][sec][key]
            value = round(cur - FINDER_STEP, 2)
            if value >= floor:
                st.update(trial_value=value, prev_value=cur, trial=[])
                self.cfg["timings"][sec][key] = value
                self.log("Speed finder: trying %s %gs (was %gs) for the next %d runs" % (label, value, cur, FINDER_RUNS))
                return
            st["knob"] = nxt

    def finder_reject(self, st, why):
        sec, key, label, floor, nxt = FINDER_KNOBS[st["knob"]]
        self.cfg["timings"][sec][key] = st["prev_value"]
        self.log("Speed finder: %s %gs %s - back to %gs" % (label, st["trial_value"], why, st["prev_value"]))
        st.update(trial=[], trial_value=None, prev_value=None, knob=nxt)
        self.finder_next(st)

    def finder_done(self):
        t = self.cfg["timings"]
        self.cfg["learned"]["finder"] = {}
        t["Blood Awakening"]["speed_finder"] = False
        self.log("Speed finder done: Strafe left time %gs, Dash spam time %gs. It turned itself off - turn it on "
                 "again to search once more." % (t["Blood Awakening"]["strafe_left_time"], t["Shared"]["dash_time"]))

    def raid_routine(self):
        self.begin_run()
        self.raid = {"skips": 0, "skip_visible": False, "last_look": 0.0, "last_skip_look": 0.0, "heatwave": False,
                     "next_a1": 0.0, "start_seen": False, "step": -1, "seq_done_t": None, "title": "Raid started",
                     "detail": "Waiting for the first skip", "active": True, "in_raid_wait": False}
        self.log("Female Raid: raid started")
        self.show(self.raid["title"], self.raid["detail"])
        try:
            self.raid_watch(force=True)
            while not self.raid["start_seen"]:
                self.raid_wait(0.05)
            self.log("First skip seen - using buffs")
            self.raid_sequence()
        except RaidFinished:
            pass
        finally:
            self.raid["active"] = False
            self.stop_skip_spam()
        self.show("Opening chests", "Finish clicked - waiting for the retry button")
        while True:
            self.wait(0.1)

    def raid_phase(self, step, title, detail_text=""):
        if step < self.raid["step"]:
            return
        self.raid.update(step=step, title=title, detail=detail_text)
        self.set_step(ROUTINE_STEPS["Female Raid"][step])
        self.show(title, detail_text)

    def raid_wait(self, seconds):
        end = time.time() + seconds
        while True:
            self.raid["in_raid_wait"] = True
            try:
                end += self.tick()
            finally:
                self.raid["in_raid_wait"] = False
            self.raid_watch()
            self.raid_failsafe_time_check()
            remaining = end - time.time()
            if remaining <= 0:
                return
            time.sleep(min(0.02, remaining))

    def raid_spam(self, key, seconds, interval, label):
        self.spam_key_for(key, seconds, interval, label, waiter=self.raid_wait)

    def raid_watch(self, force=False):
        now = time.time()
        if not force and now - self.raid["last_look"] < RAID_LOOK_INTERVAL:
            return
        self.raid["last_look"] = now
        self.raid["last_skip_look"] = now
        self.raid["looks"] = self.raid.get("looks", 0) + 1
        shot = self.det.grab()
        if shot is None:
            return
        if self.raid_skip_handle(shot):
            self.show(self.raid["title"], self.raid["detail"] or "Waiting for the skip / finish / retry button")
        # The finish button only matters at the end: a full look every 2nd time is plenty (saves CPU).
        fin = self.det.find("finish", shot, full=force or "finish" in self.det.hints or self.raid["looks"] % 2 == 0)
        if fin:
            self.raid_finish(fin)
            raise RaidFinished()
        if self.raid["heatwave"] and now >= self.raid["next_a1"] and self.det.find("heatwave", shot):
            self.log("Heatwave seen")
            self.raid_ability1_burst()

    def raid_skip_poll(self):
        now = time.time()
        if now - max(self.raid["last_skip_look"], self.raid["last_look"]) < RAID_LOOK_INTERVAL:
            return
        self.raid["last_skip_look"] = now
        shot = self.det.grab()
        if shot is not None:
            self.raid_skip_handle(shot)

    def raid_skip_handle(self, shot):
        if not self.det.find("skip", shot):
            self.raid["skip_visible"] = False
            return False
        new = not self.raid["skip_visible"]
        self.raid["skip_visible"] = True
        if new:
            self.raid["skips"] += 1
            self.raid["start_seen"] = True
            n = self.raid["skips"]
            e_time = RAID_SKIP_FIRST_SPAM_TIME if n == 1 else self.rt("skip_spam_time")
            self.skip_spam(e_time)
            self.log("Skip button seen (no. %d) - spamming %s for %gs" % (n, key_display(self.k("skip")), e_time))
            if n == 2:
                self.raid_phase(2, "Killing Eren", "Skip no. 2")
            if n == int(self.rt("skip_number")):
                self.show("Ability 3", "Skip no. %d: ability 3 once" % n)
                self.log("Skip no. %d: ability 3 once, now watching for the heatwave" % n)
                self.tap(self.k("ability3"))
                self.raid["heatwave"] = True
                self.raid_phase(3, "Killing Female titan", "Skip no. %d: waiting for heatwave" % n)
        return True

    def skip_spam(self, seconds):
        self.skip_until = time.time() + seconds
        if self.skip_thread is None or not self.skip_thread.is_alive():
            self.skip_thread = threading.Thread(target=self._skip_worker, name="skip", daemon=True)
            self.skip_thread.start()

    def stop_skip_spam(self):
        self.skip_until = 0.0

    def _skip_worker(self):
        while time.time() < self.skip_until and not self.quit:
            if self.paused or self.rescuing:
                time.sleep(0.05)
                continue
            try:
                key = self.k("skip")
                key_event(key, False)
                time.sleep(random.uniform(0.03, 0.06))
                key_event(key, True)
            except Exception:
                pass
            time.sleep(max(0.02, self.rt("skip_spam_interval")))

    def raid_sequence(self):
        t = self.rt
        self.raid_phase(0, "Using buffs", "Ability 1")
        self.log("Ability 1 spam for %gs" % t("open_a1_time"))
        self.raid_spam(self.k("ability1"), t("open_a1_time"), t("a1_interval"), "ability 1")
        self.log("Ability 3 spam for %gs" % t("a3_time"))
        self.raid_spam(self.k("ability3"), t("a3_time"), t("a3_interval"), "ability 3")
        self.log("Ability 5 spam for %gs" % t("a5_time"))
        self.raid_spam(self.k("ability5"), t("a5_time"), t("a5_interval"), "ability 5")
        self.log("Waiting %gs (ability 5 keeps spamming for the first %gs)" % (t("wait_time"), t("a5_extra")))
        end = time.time() + t("wait_time")
        extra_end = time.time() + t("a5_extra")
        while True:
            remaining = end - time.time()
            if remaining <= 0:
                break
            self.raid_phase(1, "Shifting", "Waiting... %.0fs" % remaining)
            if time.time() < extra_end:
                self.tap(self.k("ability5"))
                self.raid_wait(min(t("a5_interval"), remaining))
            else:
                self.raid_wait(min(0.5, remaining))
        self.raid["seq_done_t"] = time.time()
        self.log("Shifting + waiting done - raid failsafe in %g min" % (RAID_FAILSAFE_AFTER_SEQUENCE / 60))
        self.raid_phase(3, "Killing Female titan", "Ability 1 spam")
        self.log("Ability 1 spam for %gs" % t("a1_time"))
        self.raid_spam(self.k("ability1"), t("a1_time"), t("a1_interval"), "ability 1")
        self.log("Abilities 4 -> 3 -> 2 (over and over) until the raid ends")
        cycle = ((4, "ability4"), (3, "ability3"), (2, "ability2"))
        n = 0
        while True:
            num, key = cycle[n % 3]
            n += 1
            self.show(self.raid["title"], "Ability %d" % num)
            self.tap(self.k(key))
            self.raid_wait(t("random_gap"))

    def raid_ability1_burst(self):
        self.stop_skip_spam()
        self.show("Ability 1", "Ability 4 once, then ability 1")
        self.log("Ability 4 once, then ability 1 while the heatwave is visible")
        self.tap(self.k("ability4"))
        self.raid["in_raid_wait"] = True
        t_start = time.time()
        misses = 0
        try:
            while True:
                self.show("Ability 1", "Spamming ability 1 while the heatwave is visible (%.0fs)" % (time.time() - t_start))
                if self.det.look("heatwave", 2):
                    misses = 0
                    self.tap(self.k("ability1"))
                else:
                    misses += 1
                    if misses >= RAID_HEATWAVE_MISSES:
                        break
                self.wait(max(0.02, self.rt("heatwave_interval")))
                self.raid_failsafe_time_check()
        finally:
            self.raid["in_raid_wait"] = False
        self.log("Heatwave gone after %.1fs - ability 1 spam stopped" % (time.time() - t_start))
        self.raid["next_a1"] = time.time() + self.rt("heatwave_repeat")

    def raid_failsafe_time_check(self):
        t0 = self.mission_t0
        if t0 is None or self.rescuing or not self.cfg["failsafe"]["enabled"]:
            return
        now = time.time()
        if now - t0 > RAID_FAILSAFE_MAX_TIME:
            self.rescue("raid longer than %g min" % (RAID_FAILSAFE_MAX_TIME / 60))
        seq = self.raid.get("seq_done_t")
        if seq is not None and now - seq > RAID_FAILSAFE_AFTER_SEQUENCE:
            self.rescue("%g min after the shifting + waiting sequence" % (RAID_FAILSAFE_AFTER_SEQUENCE / 60))

    def raid_wait_finish_button(self, timeout):
        end = time.time() + timeout
        while True:
            remaining = end - time.time()
            if remaining <= 0:
                return None
            self.show("Opening chests", "Waiting for the finish button... %.0fs" % remaining)
            hit = self.det.look("finish", 2)
            if hit:
                return hit
            self.wait(RAID_FINISH_LOOK)

    def raid_finish(self, match):
        t = self.rt
        self.log("Finish button seen")
        self.raid_phase(4, "Opening chests", "Finish button seen")
        self.stop_skip_spam()
        for n, key in ((1, "chest1"), (2, "chest2")):
            if n == 2 and not t("open_chest2"):
                continue
            spot = t(key)
            if not spot:
                self.log("WARNING: Female Raid - chest %d spot is not set, not opening it" % n)
                continue
            self.log("Opening chest %d at %d, %d" % (n, spot[0], spot[1]))
            self.show("Opening chests", "Clicking chest %d" % n)
            self.click_spam(spot[0], spot[1], t("chest_click_time"), t("chest_click_interval"), 2, "chest %d" % n)
            hit = self.raid_wait_finish_button(t("finish_wait"))
            if hit:
                self.log("Chest %d open (finish button seen)" % n)
                match = hit
            else:
                self.log("WARNING: finish button not seen %gs after chest %d" % (t("finish_wait"), n))
        self.show("Opening chests", "Clicking the finish button")
        self.log("Clicking finish for %gs" % t("finish_click_time"))
        x, y = self.det.to_screen(match.cx, match.cy)
        self.click_spam(x, y, t("finish_click_time"), t("finish_click_interval"),
                        max(1, int(min(match.w, match.h)) // 4), "finish")

    # ---- stuck mission -----------------------------------------------------------------------
    def rescue(self, reason=None):
        """Mission longer than the failsafe time: spam ability 2 (eject), wait, maybe look at the ground,
        then click until the retry button shows up (that ends it with RetryFound)."""
        self.rescuing = True
        self.rescued = True
        self.rescue_t0 = time.time()
        self.count("rescues")
        prev_status = self.state
        self.set_status("rescue")
        self.stop_skip_spam()
        try:
            for name in (self.k("left"), self.k("right")):
                try:
                    self.key_up(name)
                except Exception:
                    pass
            fs = self.cfg["failsafe"]
            cx, cy, where = self.failsafe_point()
            ground = "looking at the ground, " if fs["look_down"] else ""
            why = reason or "mission longer than %gs" % self.timeout()
            self.log("Failsafe (%s) - ejecting, %sthen clicking %s (%d, %d) until retry shows up" % (why, ground, where, cx, cy))
            word = "Raid" if self.raid_mode else "Mission"
            self.notify(embed={"title": "%s #%d - stuck" % (word, self.cfg["stats"][self.family]["runs"]),
                               "description": "The failsafe kicked in (%s): ejecting and clicking until the retry "
                                              "button shows up." % why,
                               "color": COLOR_WARN}, ping=True, kind="notify_failsafe")
            self.show("Stuck mission", "Spamming ability 2 for %gs" % RESCUE_SPAM_TIME)
            spam_start = time.time()
            wait_end = spam_start + RESCUE_WAIT_START + RESCUE_WAIT
            self.spam_key_for(self.k("ability2"), RESCUE_SPAM_TIME, RESCUE_SPAM_INTERVAL, "ability 2")
            while True:
                remaining = wait_end - time.time()
                if remaining <= 0:
                    break
                self.show("Stuck mission", "Waiting %.0fs before %s" % (remaining, "looking down" if fs["look_down"] else "clicking"))
                self.wait(min(0.5, remaining))
            if fs["look_down"]:
                self.show("Stuck mission", "Looking at the ground")
                self.look_down(fs["look_time"], int(fs["look_pixels"]))
            self.show("Stuck mission", "Clicking until the retry button shows up")
            while True:
                self.tick(False)
                loop_start = time.time()
                self.scan_for_retry()
                if self.raid_mode:
                    fin = self.det.look("finish", 2)
                    if fin:
                        self.log("Raid failsafe: finish button seen - failsafe stopped")
                        self.rescuing = False
                        self.raid_finish(fin)
                        raise RaidFinished()
                self.click_spot(cx, cy)
                end = loop_start + RESCUE_CLICK_DELAY
                while time.time() < end:
                    self.tick(False)
                    time.sleep(0.05)
        finally:
            self.rescuing = False
            self.rescue_t0 = None
            if self.state == "rescue":
                self.set_status(prev_status)

    # ---- after the mission -------------------------------------------------------------------
    def loot_colour_ok(self, kind, shot, m):
        tpls = self.det.tpls(kind, m.scale)
        t = next((t for t in tpls if t.w == m.w and t.h == m.h), tpls[0])
        x0, y0 = int(round(m.cx - m.w / 2.0)), int(round(m.cy - m.h / 2.0))
        roi = shot.raw[max(0, y0):max(0, y0) + int(m.h), max(0, x0):max(0, x0) + int(m.w), :3]
        if roi.shape[0] < 4 or roi.shape[1] < 4 or t.mask:
            return roi.shape[0] >= 4 and roi.shape[1] >= 4
        return colour_match(t.full, np.ascontiguousarray(roi))

    def read_end_screen(self, shots):
        """(result or None, {loot kind: score}) from the end-screen screenshots taken around the retry click."""
        kinds = [k for k in loot_kinds_for(self.raid_mode) if self.det.has(k)]
        found, results = {}, {}
        scales = self.det.end_scales()
        # Searching the whole screen for every loot kind costs about a second a screenshot. Once loot (or the
        # result title) has been seen, only the strip around it is searched - the whole screen every 8th time.
        self.end_reads += 1
        full = self.end_reads % 8 == 1
        loot_rows = None if full else self.det.band(kinds)
        res_rows = None if full else self.det.band(("completed", "failed"), 0.5, 1.5)
        for cur in shots:
            hits = []
            for kind in kinds:
                m = self.det.find(kind, cur, scales, rows=loot_rows)
                if m is None:
                    continue
                if not self.loot_colour_ok(kind, cur, m):
                    self.det.hints.pop(kind, None)  # the shape matched but the colour is wrong: not this loot
                    continue
                hits.append((m.score, kind, m))
            # One icon is one loot kind: where two kinds matched the same spot, only the better match counts.
            kept = []
            for score, kind, m in sorted(hits, key=lambda h: -h[0]):
                if any(abs(m.cx - o.cx) < 0.6 * min(m.w, o.w) and abs(m.cy - o.cy) < 0.6 * min(m.h, o.h)
                       for _, _, o in kept):
                    continue
                kept.append((score, kind, m))
                if score > found.get(kind, 0):
                    found[kind] = score
            for res in ("completed", "failed"):
                if self.det.has(res):
                    m = self.det.best_any(res, cur, scales, rows=res_rows)
                    if m and m.score > results.get(res, -1):
                        results[res] = m.score
        result = None
        for res, score in results.items():
            if score >= self.det.threshold(res) and (result is None or score > results[result]):
                result = res
        return result, found

    def save_end_screen(self, shot):
        """Keep the end screen whose result wasn't recognised, to capture the result picture from later."""
        if shot is None:
            return
        try:
            ok, buf = cv2.imencode(".png", np.ascontiguousarray(shot.raw[:, :, :3]))
            if ok:
                os.makedirs(DATA_DIR, exist_ok=True)
                buf.tofile(end_screen_path())
                m = self.det.mon
                with open(end_screen_path() + ".json", "w", encoding="utf-8") as fh:
                    json.dump({k: m[k] for k in ("left", "top", "width", "height")}, fh)
        except Exception:
            pass

    # ---- session limits ------------------------------------------------------------------------------
    def limit_reason(self):
        """Why this session should end now (a limit in Settings > App), or None."""
        a = self.cfg["app"]
        runs = int(a.get("stop_runs") or 0)
        if runs and self.session["runs"] >= runs:
            return "%d %s done" % (runs, "raids" if self.raid_mode else "missions")
        hours = float(a.get("stop_hours") or 0)
        if hours and self.session["start"] and time.time() - self.session["start"] - self.session["paused"] >= hours * 3600:
            return "%g hour%s of running" % (hours, "" if hours == 1 else "s")
        return None

    def end_session(self, reason):
        close = self.cfg["app"].get("close_roblox_at_end")
        self.log("Stopping: %s.%s" % (reason, " Closing Roblox." if close else ""))
        self.notify("Colossal Macro stopped: %s. This session: %d done, %d completed, %d failed.%s"
                    % (reason, self.session["retries"], self.session["completed"], self.session["failed"],
                       " Roblox was closed." if close else ""), kind="notify_mission")
        if close:
            try:
                close_roblox()
            except Exception as e:
                self.log("Could not close Roblox (%s)" % e)
        raise StopMacro()

    def handle_retry(self, m, shot):
        found_at = time.time()
        length = found_at - self.mission_t0 if self.mission_t0 is not None else None
        steps = []
        for i, (name, t0) in enumerate(self.run_steps):
            t1 = self.run_steps[i + 1][1] if i + 1 < len(self.run_steps) else found_at
            steps.append((name, max(0.0, t1 - t0)))
        if self.run_steps and self.mission_t0 is not None and self.run_steps[0][1] - self.mission_t0 > 0.3:
            steps.insert(0, ("Start", self.run_steps[0][1] - self.mission_t0))
        self.run_steps = []
        self.mission_t0 = None
        was_rescued, self.rescued = self.rescued, False
        self.set_status("retrying")
        self.set_step("Retry")
        self.log("Retry found (score %.2f)%s" % (m.score, (" - took " + fmt_run(length)) if length else ""))
        if was_rescued:
            self.log("Stuck mission is over")
        # Retry is clicked first; the result and loot are read afterwards from screenshots of the end screen
        # (the one from when retry was seen, plus a few taken between the clicks), while the next one loads.
        result, found = None, {}
        track = self.cfg["app"]["track_loot"]
        want_png = self.png_wanted()
        first = shot if shot is not None else (self.det.grab() if track or want_png else None)
        # Is the old mission's start icon visible on the end screen? Only then is it worth waiting for it to go
        # away after the click - otherwise a fast-loading next mission would wait for nothing (up to 20s).
        icon_on_end = self.det.start_still_there(self.raid_mode)
        stop_reason = self.limit_reason()
        x, y = self.det.to_screen(m.cx, m.cy)
        self.show("Retry", "Clicking retry..." if not stop_reason else "Session limit reached - not clicking retry")
        clicked_at = time.time()
        frames = []
        keep_until = found_at + (0.0 if self.fast() else LOOT_SCAN_TIME)  # loot fades in: watch a little longer
        last_frame = [clicked_at]

        def keep_frame():
            # Only the newest screenshot that still shows the end screen is kept: reading one costs about a second
            # of CPU on a busy PC, and loot that faded in late is on the newest one anyway.
            now = time.time()
            if track and now < keep_until and now - last_frame[0] >= LOOT_SCAN_STEP:
                last_frame[0] = now
                f = self.det.grab()
                if f is not None and (self.det.find("retry", f, full=False) or self.det.find("retry_alt", f, full=False)):
                    frames[:] = [f]

        if stop_reason:
            self.log("Session limit reached (%s) - leaving the end screen as it is" % stop_reason)
        else:
            self.click_spam(x, y, self.sh("retry_click_time"), self.sh("retry_click_interval"),
                            max(1, int(min(m.w, m.h)) // 4), between=keep_frame)
            self.count("retries")
        if track:
            self.show("Retry clicked" if not stop_reason else "Last run", "Reading the result and loot...")
            try:
                result, found = self.read_end_screen([f for f in [first] + frames if f is not None])
            except Exception as e:  # never let reading the loot stop the grind
                result, found = None, {}
                self.log("Could not read the end screen (%s: %s) - carrying on" % (type(e).__name__, e))
            if result:
                self.count(result)
                self.log("Result: %s" % result.capitalize())
                self.result_misses = 0
            else:
                self.log("Result: not detected")
                self.result_misses += 1
                if self.result_misses >= 3 and not self.result_hint:
                    self.result_hint = True
                    self.log("Completed / Failed isn't being recognised on your screen. To fix it: Settings > "
                             "Pictures > Results > 'End screen' and drag a box around the COMPLETED (or FAILED) title "
                             "on your last end screen.")
            for kind in found:
                self.session["loot"][kind] += 1
                self.cfg["stats"][self.family]["loot"][kind] += 1
            self.log("Loot: %s" % (", ".join("%s (%.2f)" % (loot_text({k: 1}), found[k]) for k in LOOT_KINDS
                                             if k in found) or "nothing"))
            self.stats_changed()
            # Every end screen is kept (the newest one, where late loot has faded in): Settings > Pictures >
            # 'End screen' captures loot / result pictures from it, and it shows what the macro saw.
            self.save_end_screen(frames[-1] if frames else first)
        png = self.end_screen_png(first) if want_png else None
        frames = first = None
        if length and not was_rescued:
            self.session["lengths"].append(length)
            del self.session["lengths"][:-50]
        new_best = False
        bests = self.cfg["stats"].setdefault("best", {})
        if length and not was_rescued and result != "failed":
            prev = bests.get(self.routine)
            if prev is None or length < prev:
                bests[self.routine] = length
                new_best = prev is not None
                if new_best:
                    self.log("New best time: %s (was %s)" % (fmt_run(length), fmt_run(prev)))
        entry = {"n": self.cfg["stats"][self.family]["runs"], "time": length, "result": result,
                 "loot": [k for k in LOOT_KINDS if k in found], "rescued": was_rescued, "steps": steps,
                 "best": new_best}
        self.session["history"].append(entry)
        del self.session["history"][:-50]
        self.out.put(("run", entry))
        try:
            append_run_log(found_at, self.routine, length, result, entry["loot"], was_rescued, steps)
        except Exception as e:
            self.log("Could not write runs.csv (%s)" % e)
        self.finder_after_run(length, was_rescued, result)
        self.notify(embed=self.mission_embed(result, found, length, was_rescued, new_best), png=png,
                    kind="notify_mission")
        if stop_reason:
            self.end_session(stop_reason)
        # Go on as soon as the end screen is gone (the click worked) instead of always waiting the full time.
        word = "raid" if self.raid_mode else "mission"
        max_off = max(HANDS_OFF_MIN, self.sh("hands_off"))
        reclick_at = clicked_at + RETRY_RECLICK_AFTER
        self.show("Hands off", "Waiting for the next %s to load" % word)
        while time.time() - clicked_at < max_off:
            self.wait(0.25, scan=False)
            if time.time() - clicked_at < HANDS_OFF_MIN:
                continue
            still = self.det.roi_find("retry") or self.det.roi_find("retry_alt")
            if still is None:
                break
            if time.time() >= reclick_at:
                self.log("Retry is still showing - clicking it again")
                rx, ry = self.det.to_screen(still.cx, still.cy)
                self.click_spam(rx, ry, self.sh("retry_click_time"), self.sh("retry_click_interval"),
                                max(1, int(min(still.w, still.h)) // 4))
                reclick_at = time.time() + RETRY_RECLICK_AFTER
        deadline = time.time() + (ICON_GONE_TIMEOUT if icon_on_end else 0)
        while time.time() < deadline:
            self.tick(False)
            if not self.det.start_still_there(self.raid_mode):
                break
            time.sleep(0.2)

    def mission_embed(self, result, found, length, rescued, new_best=False):
        st = self.cfg["stats"][self.family]
        word = "Raid" if self.raid_mode else "Mission"
        head = {"completed": "Completed", "failed": "Failed"}.get(result, "Result not detected")
        if rescued:
            head += " (after the failsafe)"
        if new_best:
            head += "  -  NEW BEST"
        done = self.session["completed"] + self.session["failed"]
        rate = ("%d%%" % (100 * self.session["completed"] // done)) if done else "-"
        run = fmt_dur(time.time() - self.session["start"]) if self.session["start"] else "-"
        fields = [
            {"name": "This session", "value": "**%d** done" % self.session["retries"], "inline": True},
            {"name": "Completed / failed", "value": "%d / %d" % (self.session["completed"], self.session["failed"]), "inline": True},
            {"name": "Success rate", "value": rate, "inline": True},
            {"name": "%s time" % word, "value": "`%s`" % (fmt_run(length) if length else "--:--"), "inline": True},
            {"name": "Best", "value": "`%s`" % fmt_run(self.cfg["stats"].get("best", {}).get(self.routine)), "inline": True},
            {"name": "Run time", "value": "`%s`" % run, "inline": True},
            {"name": "Routine", "value": self.routine, "inline": True},
        ]
        return {"author": {"name": "%s %s" % (APP_NAME, VERSION)},
                "title": "%s #%d  -  %s" % (word, st["runs"], head),
                "description": "**Loot:** %s" % loot_text(found),
                "color": {"completed": COLOR_GOOD, "failed": COLOR_BAD}.get(result, COLOR_NEUTRAL),
                "fields": fields,
                "footer": {"text": APP_NAME},
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    # ---- reconnect ---------------------------------------------------------------------------
    def reconnect_steps(self):
        spots = self.cfg["reconnect"]["spots"]
        tab = "Raids" if self.raid_mode else "Missions"
        shared = {k for k, _ in RECONNECT_SHARED_SPOTS}
        steps = []
        for key, name in RECONNECT_SHARED_SPOTS + RECONNECT_TAB_SPOTS[tab]:
            xy = spots.get(key)
            if xy:
                steps.append((name if key in shared else "%s > %s" % (tab, name), xy, RECONNECT_GATES.get(key), key))
        return steps

    def reconnect_wait_for(self, gate, i, total, name):
        label = PICTURES[gate]["label"]
        give_up = time.time() + RECONNECT_IMAGE_TIMEOUT
        while self.det.seen(gate, thorough=True) is None:
            left = give_up - time.time()
            if left <= 0:
                self.log("Reconnect: the '%s' picture did not show within %gs - %s was not clicked"
                         % (label, RECONNECT_IMAGE_TIMEOUT, name))
                return False
            self.show("Reconnecting", "Step %d/%d: waiting for '%s' to show (%.0fs)" % (i, total, label, left))
            self.wait(0.5, scan=False)
        self.log("Reconnect: '%s' seen" % label)
        return True

    def reconnect_countdown(self, i, total, name, seconds):
        end = time.time() + seconds
        while True:
            remaining = end - time.time()
            if remaining <= 0:
                return
            self.show("Reconnecting", "Step %d/%d: %s in %.0fs" % (i, total, name, remaining))
            self.wait(min(0.5, remaining), scan=False)

    def reconnect_clicks(self):
        steps = self.reconnect_steps()
        total = len(steps)
        rc = self.cfg["reconnect"]
        for i, (name, (x, y), gate, key) in enumerate(steps, 1):
            if gate == "select":
                if not self.reconnect_wait_for(gate, i, total, name):
                    return False
                self.notify("Reconnected - the game has loaded, clicking through the lobby now.", kind="notify_reconnect")
                self.reconnect_countdown(i, total, name, RECONNECT_FIRST_DELAY)
            else:
                self.reconnect_countdown(i, total, name, rc["play_delay"] if key in RECONNECT_PLAY_KEYS else rc["click_delay"])
                if gate and not self.reconnect_wait_for(gate, i, total, name):
                    return False
            self.show("Reconnecting", "Step %d/%d: clicking %s" % (i, total, name))
            self.log("Reconnect step %d/%d: clicking %s (%d, %d)" % (i, total, name, x, y))
            self.click_spot(x, y)
        return True

    def reconnect_launch(self, reason):
        self.rescuing = False
        self.rescue_t0 = None
        self.mission_t0 = None
        self.raid["active"] = False
        self.stop_skip_spam()
        self.release_all()
        self.set_status("waiting")
        self.set_step(None)
        self.show("Reconnecting", "Closing Roblox")
        self.log("Reconnect: %s - closing Roblox and rejoining the game" % reason)
        close_roblox()
        self.wait(RECONNECT_CLOSE_WAIT, scan=False)
        self.show("Reconnecting", "Launching the game")
        self.log("Launching roblox://placeId=%d" % ROBLOX_PLACE_ID)
        try:
            launch_roblox_game()
        except Exception as e:
            self.log("Reconnect: could not launch Roblox (%s)" % e)
        end = time.time() + RECONNECT_LOAD_WAIT
        while True:
            remaining = end - time.time()
            if remaining <= 0:
                return
            if self.det.seen("select", thorough=True) is not None:
                self.log("Reconnect: game loaded early - skipping the rest of the load wait")
                return
            self.show("Reconnecting", "Waiting for the game to load... %.0fs" % remaining)
            self.wait(min(0.5, remaining), scan=False)

    def reconnect_rejoin(self, reason):
        self.reconnecting = True
        try:
            self.notify("Rejoining the game (%s)..." % reason, ping=True, kind="notify_reconnect")
            for attempt in range(1, RECONNECT_MAX_ATTEMPTS + 1):
                self.reconnect_launch(reason)
                self.log("Game launched - clicking through %d spots" % len(self.reconnect_steps()))
                if self.reconnect_clicks():
                    self.log("Rejoin done - waiting for the next %s" % ("raid" if self.raid_mode else "mission"))
                    return
                reason = "a reconnect picture did not show"
                if attempt < RECONNECT_MAX_ATTEMPTS:
                    self.log("Rejoining again (attempt %d/%d)" % (attempt + 1, RECONNECT_MAX_ATTEMPTS))
            self.log("Reconnect gave up after %d attempts - waiting for the next mission" % RECONNECT_MAX_ATTEMPTS)
            self.notify("Reconnect FAILED after %d attempts - please check the game." % RECONNECT_MAX_ATTEMPTS,
                        ping=True, kind="notify_reconnect")
        finally:
            self.reconnecting = False
            self.rc_next = time.time() + RECONNECT_COOLDOWN

    # ---- main loop ---------------------------------------------------------------------------
    def _main(self):
        error = None
        try:
            self.det = Detector(self.cfg, self.log, save_cb=lambda: self.out.put(("save",)),
                                mon=game_region(pick_monitor(self.cfg)))
            mon = self.det.mon
            self.log("Started: %s on %dx%d. Click into Roblox; the routine starts when the %s begins."
                     % (self.routine, mon["width"], mon["height"], "raid" if self.raid_mode else "mission"))
            if mon.get("windowed"):
                self.log("Roblox is windowed (%dx%d): only the game window is watched" % (mon["width"], mon["height"]))
            if abs(self.det.scale - 1.0) > 0.01:
                self.log("Screen is %dp: pictures are scaled x%.2f" % (mon["height"], self.det.scale))
            lim = []
            if self.cfg["app"].get("stop_runs"):
                lim.append("after %d %s" % (self.cfg["app"]["stop_runs"], "raids" if self.raid_mode else "missions"))
            if self.cfg["app"].get("stop_hours"):
                lim.append("after %g hours" % self.cfg["app"]["stop_hours"])
            if lim:
                self.log("Session limit: stops %s%s" % (" or ".join(lim), ", then closes Roblox"
                                                         if self.cfg["app"].get("close_roblox_at_end") else ""))
            trim_run_log()
            self.reconnect_on = False
            if self.cfg["reconnect"]["enabled"]:
                missing = reconnect_missing(self.cfg, self.raid_mode)
                if missing:
                    self.log("Reconnect is on but not set up (still needed: %s) - it stays off" % ", ".join(missing))
                else:
                    self.reconnect_on = True
                    self.log("Reconnect is ON: the game is rejoined on a disconnect, a long failsafe or !reconnect")
            if self.raid_mode:
                if not self.rt("chest1"):
                    self.log("WARNING: Female Raid - the chest 1 spot is not set (Settings > Timings > Female Raid)")
                elif self.rt("open_chest2") and not self.rt("chest2"):
                    self.log("WARNING: Female Raid - 'Open chest 2' is on but the chest 2 spot is not set")
            need_start, after_retry = True, False
            while True:
                try:
                    if need_start:
                        self.wait_for_mission_start(scan_retry=not after_retry)
                        need_start, after_retry = False, False
                    if self.raid_mode:
                        self.raid_routine()
                    else:
                        self.run_mission()
                    need_start = True
                except RetryFound as r:
                    self.release_held()
                    self.stop_skip_spam()
                    self.handle_retry(r.match, r.shot)
                    need_start, after_retry = True, True
                except Disconnected as d:
                    self.release_held()
                    self.stop_skip_spam()
                    self.reconnect_rejoin(d.reason)
                    need_start, after_retry = True, False
        except StopMacro:
            self.log("Stopped")
        except Exception as e:
            error = "%s: %s" % (type(e).__name__, e)
            self.log("Error: " + error)
            self.out.put(("trace", traceback.format_exc()))
        finally:
            self.mission_t0 = None
            self.rescuing = False
            self.paused = False
            self.stop_skip_spam()
            try:
                self.release_all()
            except Exception:
                pass
            if self.det is not None:
                self.det.close()
                self.det = None
            if error:
                self.notify("Colossal Macro stopped because of an error: %s" % error, ping=True, kind="notify_error")
            self.set_status("idle")
            self.set_step(None)
            self.out.put(("done",))


# =============================================================================
#  Window
# =============================================================================

BG = "#0b0c10"
CARD = "#14161c"
CARD2 = "#1b1e26"
HOVER = "#242832"
EDGE = "#22252e"
EDGE_HI = "#2f333d"
TEXT = "#eceef2"
MUTED = "#8c92a0"
DIM = "#5a6170"
ACCENT = "#ff6b2c"
ACCENT_HOVER = "#ff8048"
ACCENT_DARK = "#1a0c05"
ACCENT_BG = "#2c180d"
ACCENT_SOFT = "#ffb27f"
GOOD = "#3ccf80"
WARN = "#f2b544"
BAD = "#f06262"
FIELD_BG = "#0f1116"
SEG_DONE = "#6b3216"
KEY_COLOR = "#010101"  # colour keyed out of the rounded pop-up windows

STATUS_LOOK = {
    "idle": ("Idle", CARD2, MUTED),
    "waiting": ("Waiting", "#18233a", "#8fb3ff"),
    "running": ("Running", ACCENT_BG, ACCENT_SOFT),
    "retrying": ("Retrying", "#13301f", GOOD),
    "paused": ("Paused", "#33290f", WARN),
    "rescue": ("Failsafe", "#381616", BAD),
}

UI = {"scale": 1.0}


def px(n):
    return int(round(n * UI["scale"]))


FONT = "Segoe UI"
FONT_SEMI = "Segoe UI Semibold"
_FONTS = {}


def font_obj(spec):
    key = str(spec)
    f = _FONTS.get(key)
    if f is None:
        f = tkfont.Font(font=spec)
        _FONTS[key] = f
    return f


def _rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    ra, rb = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(int(round(ra[i] + (rb[i] - ra[i]) * t)) for i in range(3))


_IMAGES = {}


def rounded_image(w, h, r, fill, edge=None):
    """An anti-aliased rounded rectangle as a Tk image. fill / edge: a colour, a (top, bottom) gradient, or None.
    Corners are transparent, so they blend into whatever the widget sits on."""
    w, h = max(1, int(w)), max(1, int(h))
    r = max(0, min(int(r), h // 2, w // 2))
    key = (w, h, r, fill, edge)
    hit = _IMAGES.get(key)
    if hit is not None:
        return hit
    if len(_IMAGES) > 600:
        _IMAGES.clear()  # every widget keeps its own reference, so this only drops unused ones
    arr = np.zeros((h, w, 4), np.uint8)
    if fill is not None:
        outer = _shape_cov(w, h, r, 0)
        inner = _shape_cov(w, h, max(0, r - 1), 1) if edge is not None else outer
        rgb = _row_colors(fill, h) * inner[:, :, None]
        if edge is not None:
            rgb += _row_colors(edge, h) * (outer - inner)[:, :, None]
        safe = np.where(outer > 0, outer, 1.0)[:, :, None]
        arr[:, :, :3] = np.clip(rgb / safe + 0.5, 0, 255).astype(np.uint8)
        arr[:, :, 3] = np.clip(outer * 255 + 0.5, 0, 255).astype(np.uint8)
    photo = ImageTk.PhotoImage(Image.fromarray(arr, "RGBA"))
    _IMAGES[key] = photo
    return photo


_CORNERS = {}


def _corner_cov(r):
    """Anti-aliased coverage (0..1) of the top-left quarter of a circle of radius r, as an r x r tile."""
    tile = _CORNERS.get(r)
    if tile is None:
        ss = 4
        c = (np.arange(r * ss) + 0.5) / ss
        d = np.sqrt((c[None, :] - r) ** 2 + (c[:, None] - r) ** 2)
        tile = (d <= r).astype(np.float32).reshape(r, ss, r, ss).mean(axis=(1, 3))
        _CORNERS[r] = tile
    return tile


def _shape_cov(w, h, r, inset):
    """Coverage map of a rounded rectangle of radius r, inset by `inset` pixels on every side."""
    cov = np.zeros((h, w), np.float32)
    cov[inset:h - inset, inset:w - inset] = 1.0
    if r > 0 and w - 2 * inset >= 2 * r and h - 2 * inset >= 2 * r:
        t = _corner_cov(r)
        a, b = inset, inset + r
        cov[a:b, a:b] = t
        cov[a:b, w - b:w - a] = t[:, ::-1]
        cov[h - b:h - a, a:b] = t[::-1, :]
        cov[h - b:h - a, w - b:w - a] = t[::-1, ::-1]
    return cov


def _row_colors(spec, h):
    """(h, 1, 3) float colours for a solid colour or a (top, bottom) vertical gradient."""
    top, bottom = spec if isinstance(spec, tuple) else (spec, spec)
    a, b = np.array(_rgb(top), np.float32), np.array(_rgb(bottom), np.float32)
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None] if h > 1 else np.zeros((1, 1), np.float32)
    return (a + (b - a) * t)[:, None, :]


try:
    dwmapi = ctypes.WinDLL("dwmapi")
    dwmapi.DwmSetWindowAttribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
    dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
except Exception:
    dwmapi = None
user32.GetParent.argtypes = (wintypes.HWND,)
user32.GetParent.restype = wintypes.HWND


def dark_titlebar(win):
    """Dark title bar (Windows 10 1809+ / 11) instead of the white default."""
    if dwmapi is None:
        return
    try:
        hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
        on = ctypes.c_int(0 if UI.get("light") else 1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new / old Windows 10 builds)
            if dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
        r, g, b = _rgb(BG)
        color = ctypes.c_int(r | (g << 8) | (b << 16))
        dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), ctypes.sizeof(color))  # caption colour (Win 11)
    except Exception:
        pass


def present(win):
    """Show a window with the dark title bar already applied (no white flash)."""
    try:
        win.attributes("-alpha", 0.0)
    except tk.TclError:
        pass
    win.deiconify()
    win.update_idletasks()
    dark_titlebar(win)
    win.withdraw()
    win.deiconify()
    redraw_cards(win)
    try:
        win.attributes("-alpha", 1.0)
    except tk.TclError:
        pass


def fit_geometry(win, w, h):
    """Size + centre a window, never taller than the screen."""
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    w, h = min(w, sw - px(40)), min(h, int(sh * 0.9))
    win.geometry("%dx%d+%d+%d" % (w, h, max(0, (sw - w) // 2), max(0, (sh - h) // 2 - px(20))))


class RoundCard(tk.Frame):
    """A frame with an anti-aliased rounded background and a soft hairline. Children use bg=fill as usual."""

    def __init__(self, parent, fill=CARD, edge=(EDGE_HI, EDGE), radius=None, **kw):
        super().__init__(parent, bg=fill, **kw)
        self._canvas = tk.Canvas(self, bg=parent.cget("bg"), highlightthickness=0, bd=0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.lower(self._canvas)
        self._style = (fill, edge, px(14) if radius is None else radius)
        self._size = None
        self.bind("<Configure>", self._redraw, add="+")
        self.bind("<Map>", self._redraw, add="+")
        # A card inside a page that just appeared gets no Configure/Map of its own - but its canvas is exposed.
        self._canvas.bind("<Expose>", lambda e: self._redraw(), add="+")

    def _redraw(self, e=None):
        # Only cards that are on screen are drawn: hidden settings pages cost nothing until they're opened.
        if (e is not None and e.widget is not self) or not self.winfo_viewable():
            return
        w, h = self.winfo_width(), self.winfo_height()
        if (w, h) == self._size or w < 2 or h < 2:
            return
        self._size = (w, h)
        img = rounded_image(w, h, self._style[2], self._style[0], self._style[1])
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, image=img, anchor="nw")
        self._canvas.image = img


def redraw_cards(widget):
    """Draw the rounded cards inside `widget` that just became visible (a page / tab / window was shown)."""
    widget.update_idletasks()
    stack = [widget]
    while stack:
        w = stack.pop()
        if isinstance(w, RoundCard):
            w._redraw()
        stack.extend(w.winfo_children())


def card(parent, **kw):
    return RoundCard(parent, **kw)


def label(parent, text, size=10, color=TEXT, bold=False, bg=None, **kw):
    return tk.Label(parent, text=text, bg=bg or parent.cget("bg"), fg=color, font=(FONT_SEMI if bold else FONT, size), **kw)


class Pill(tk.Label):
    """A non-clickable rounded tag (the status badge)."""

    def __init__(self, parent, font=None):
        super().__init__(parent, bg=parent.cget("bg"), bd=0, padx=0, pady=0, compound="center",
                         font=font or (FONT_SEMI, 9))

    def set(self, text, fill, fg):
        f = font_obj(self.cget("font"))
        w, h = f.measure(text) + px(26), f.metrics("linespace") + px(10)
        img = rounded_image(w, h, h // 2, fill)
        self.configure(image=img, text=text, fg=fg, width=w, height=h)
        self.image = img


class Btn(tk.Label):
    """Rounded pill button: soft hover, pressed state, click on release."""
    # fill, hover, pressed, text colour
    STYLES = {
        "primary": (("#ff7c3f", "#f25c1d"), ("#ff8f58", "#ff6a2c"), ("#e65619", "#d84f15"), ACCENT_DARK),
        "normal": (CARD2, HOVER, "#171a21", TEXT),
        "ghost": (None, CARD2, HOVER, MUTED),
        "danger": ("#2b1618", "#3a1d20", "#231214", "#ff9393"),
    }

    def __init__(self, parent, text, command, style="normal", padx=None, pady=None, width=None, font=None, radius=None):
        super().__init__(parent, bg=parent.cget("bg"), bd=0, highlightthickness=0, padx=0, pady=0, compound="center",
                         font=font or (FONT_SEMI, 10), cursor="hand2")
        self.style_name = style
        self.command = command
        self.enabled = True
        self.hover = False
        self.pressed = False
        self.pad = (px(16) if padx is None else padx, px(8) if pady is None else pady)
        self.min_chars = width
        self.radius = radius
        self.actual_w = 0
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Configure>", self._on_resize)
        self.set_text(text)

    def set_text(self, text):
        self.text_ = text
        f = font_obj(self.cget("font"))
        w = f.measure(text) + 2 * self.pad[0]
        if self.min_chars:
            w = max(w, f.measure("0") * self.min_chars + 2 * self.pad[0])
        self.base = (w, f.metrics("linespace") + 2 * self.pad[1])
        self.configure(text=text, width=self.base[0], height=self.base[1])
        self._render()

    def _render(self):
        fill, hover, pressed, fg = self.STYLES[self.style_name]
        if not self.enabled:
            col, fg = (None if self.style_name == "ghost" else CARD2), DIM
        else:
            col = pressed if self.pressed else hover if self.hover else fill
        w, h = max(self.base[0], self.actual_w), self.base[1]
        img = rounded_image(w, h, h // 2 if self.radius is None else self.radius, col)
        self.configure(image=img, fg=fg)
        self.image = img

    def _on_resize(self, e):
        if e.width != self.actual_w:
            self.actual_w = e.width
            self._render()

    def _enter(self, _e):
        self.hover = True
        if self.enabled:
            self._render()

    def _leave(self, _e):
        self.hover = False
        self.pressed = False
        self._render()

    def _press(self, _e):
        if self.enabled:
            self.pressed = True
            self._render()

    def _release(self, e):
        if not self.pressed:
            return
        self.pressed = False
        inside = 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height()
        self._render()
        if inside and self.enabled and self.command:
            self.command()

    def set_enabled(self, on):
        self.enabled = on
        self.configure(cursor="hand2" if on else "arrow")
        self._render()


class Dropdown(Btn):
    """A pill that opens a menu of options."""

    def __init__(self, parent, var, options, command=None):
        self.var, self.options, self.on_pick = var, list(options), command
        super().__init__(parent, "%s   ▾" % var.get(), self._open, "normal", padx=px(14))
        self.menu = tk.Menu(self, tearoff=0, bg=CARD2, fg=TEXT, activebackground=ACCENT, activeforeground=ACCENT_DARK,
                            bd=0, font=(FONT, 10))
        for o in self.options:
            self.menu.add_command(label=o, command=lambda v=o: self._pick(v))

    def _open(self):
        self.menu.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height() + px(4))

    def _pick(self, v):
        self.var.set(v)
        self.set_text("%s   ▾" % v)
        if self.on_pick:
            self.on_pick(v)


class Toggle(tk.Canvas):
    """An iOS-style switch bound to a BooleanVar, with a short eased slide."""

    def __init__(self, parent, var, command=None):
        self.w, self.h = px(38), px(22)
        super().__init__(parent, width=self.w, height=self.h, bg=parent.cget("bg"), highlightthickness=0, bd=0,
                         cursor="hand2")
        self.var, self.command = var, command
        self.pos = 1.0 if var.get() else 0.0
        self._anim = None
        self.bind("<Button-1>", self._click)
        var.trace_add("write", lambda *a: self._animate())
        self._draw()

    def _click(self, _e):
        self.var.set(not self.var.get())
        if self.command:
            self.command()

    def _animate(self):
        target = 1.0 if self.var.get() else 0.0
        start, t0 = self.pos, time.time()
        if self._anim:
            self.after_cancel(self._anim)

        def step():
            t = min(1.0, (time.time() - t0) / 0.16)
            ease = 1 - (1 - t) ** 3
            self.pos = start + (target - start) * ease
            self._draw()
            self._anim = self.after(15, step) if t < 1.0 else None
        step()

    def _draw(self):
        if not self.winfo_exists():
            return
        q = round(self.pos * 8) / 8.0  # fewer distinct images
        track = rounded_image(self.w, self.h, self.h // 2, mix(HOVER, ACCENT, q))
        k = self.h - px(6)
        knob = rounded_image(k, k, k // 2, mix("#c9ccd4", "#ffffff", q))
        self.delete("all")
        self.create_image(0, 0, image=track, anchor="nw")
        self.create_image(px(3) + (self.w - k - px(6)) * self.pos, px(3), image=knob, anchor="nw")
        self.images = (track, knob)


class Segmented(tk.Frame):
    """A row of options in a rounded track; the picked one is a filled pill. options: values or (value, text)."""

    def __init__(self, parent, var, options, command=None, font=None, stretch=False, accent=True, track=FIELD_BG):
        super().__init__(parent, bg=parent.cget("bg"))
        self.var, self.command, self.stretch, self.accent = var, command, stretch, accent
        self.font = font or (FONT_SEMI, 9)
        self.enabled = True
        self.track = RoundCard(self, fill=track, edge=(EDGE, EDGE))
        self.track.pack(fill="x" if stretch else None)
        self.items = []
        for opt in options:
            value, text = opt if isinstance(opt, tuple) else (opt, opt)
            lbl = tk.Label(self.track, bg=track, bd=0, padx=0, pady=0, compound="center", font=self.font, cursor="hand2")
            lbl.pack(side="left", padx=(px(3), 0), pady=px(3), expand=stretch)
            item = {"value": value, "text": text, "label": lbl, "hover": False}
            lbl.bind("<Button-1>", lambda e, it=item: self._pick(it))
            lbl.bind("<Enter>", lambda e, it=item: self._hover(it, True))
            lbl.bind("<Leave>", lambda e, it=item: self._hover(it, False))
            self.items.append(item)
        tk.Frame(self.track, bg=track, width=px(3)).pack(side="left")
        self._seg_w = 0
        if stretch:
            self.track.bind("<Configure>", self._resize, add="+")
        var.trace_add("write", lambda *a: self.refresh())
        self.refresh()

    def _resize(self, e):
        if e.widget is not self.track:
            return
        w = int((e.width - px(3) * (len(self.items) + 1)) / max(1, len(self.items)))
        if w != self._seg_w:
            self._seg_w = w
            self.refresh()

    def _pick(self, item):
        if not self.enabled or self.var.get() == item["value"]:
            return
        self.var.set(item["value"])
        if self.command:
            self.command(item["value"])

    def _hover(self, item, on):
        item["hover"] = on
        self.refresh()

    def refresh(self):
        if not self.winfo_exists():
            return
        f = font_obj(self.font)
        cur = self.var.get()
        h = f.metrics("linespace") + px(10)
        for it in self.items:
            w = max(f.measure(it["text"]) + px(24), self._seg_w if self.stretch else 0)
            sel = it["value"] == cur
            if sel:
                col = (ACCENT if self.accent else HOVER) if self.enabled else CARD2
                fg = (ACCENT_DARK if self.accent else TEXT) if self.enabled else MUTED
            else:
                col = CARD2 if (it["hover"] and self.enabled) else None
                fg = MUTED if self.enabled else DIM
            img = rounded_image(w, h, h // 2, col)
            it["label"].configure(image=img, text=it["text"], fg=fg, width=w, height=h,
                                  cursor="hand2" if self.enabled else "arrow")
            it["label"].image = img

    def set_enabled(self, on):
        self.enabled = on
        self.refresh()


class ThinScrollbar(tk.Canvas):
    """A slim rounded scrollbar that hides itself when there is nothing to scroll."""

    def __init__(self, parent, command):
        super().__init__(parent, width=px(8), bg=parent.cget("bg"), highlightthickness=0, bd=0)
        self.command = command
        self.lo, self.hi = 0.0, 1.0
        self.hover = False
        self._drag = None
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))

    def set(self, lo, hi):
        self.lo, self.hi = float(lo), float(hi)
        self._draw()

    def _set_hover(self, on):
        self.hover = on
        self._draw()

    def _draw(self):
        self.delete("all")
        H = self.winfo_height()
        if self.hi - self.lo >= 0.999 or H < 20:
            return
        y0 = int(self.lo * H)
        y1 = max(y0 + px(24), int(self.hi * H))
        w = px(6) if self.hover or self._drag else px(4)
        img = rounded_image(w, y1 - y0, w // 2, MUTED if self.hover or self._drag else DIM)
        self.create_image((px(8) - w) // 2, y0, image=img, anchor="nw")
        self.image = img

    def _press(self, e):
        H = max(1, self.winfo_height())
        if not (self.lo * H <= e.y <= self.hi * H):
            span = self.hi - self.lo
            self.command("moveto", str(max(0.0, e.y / H - span / 2)))
        self._drag = (e.y, self.lo)

    def _motion(self, e):
        if self._drag:
            y, lo = self._drag
            self.command("moveto", str(max(0.0, lo + (e.y - y) / max(1, self.winfo_height()))))


def entry(parent, width=8, show=None):
    return tk.Entry(parent, width=width, bg=FIELD_BG, fg=TEXT, insertbackground=TEXT, relief="flat", show=show or "",
                    font=(FONT, 10), highlightthickness=1, highlightbackground=EDGE_HI, highlightcolor=ACCENT,
                    insertwidth=1, selectbackground=ACCENT_BG, selectforeground=TEXT)


class ScrollFrame(tk.Frame):
    def __init__(self, parent, bg=BG):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.bar = ThinScrollbar(self, self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar.pack(side="right", fill="y", padx=(px(6), 0))
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        # Every widget has its toplevel in its bindtags, so this sees the wheel over any child.
        self.winfo_toplevel().bind("<MouseWheel>", self._wheel, add="+")

    def _wheel(self, e):
        if not self.winfo_ismapped():
            return
        if self.inner.winfo_reqheight() <= self.canvas.winfo_height():
            return
        self.canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")


def keysym_to_name(keysym):
    k = keysym.lower()
    special = {"control_l": "ctrl", "control_r": "rctrl", "shift_l": "shift", "shift_r": "rshift",
               "alt_l": "alt", "alt_r": "ralt", "return": "enter", "escape": "esc", "space": "space",
               "tab": "tab", "backspace": "backspace", "caps_lock": "capslock", "up": "up", "down": "down",
               "left": "left", "right": "right", "insert": "insert", "delete": "delete", "home": "home",
               "end": "end", "prior": "pageup", "next": "pagedown", "grave": "`", "minus": "-",
               "equal": "=", "bracketleft": "[", "bracketright": "]", "backslash": "\\",
               "semicolon": ";", "apostrophe": "'", "comma": ",", "period": ".", "slash": "/"}
    if k in special:
        return special[k]
    if re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", k):
        return k
    if len(k) == 1 and k in VK:
        return k
    if k.startswith("kp_") and k[3:].isdigit():
        return "num" + k[3:]
    return None


class FloatingPill:
    """A borderless rounded pop-up (status bar, countdown). The square corners are keyed out."""

    def __init__(self, root, w, h, alpha=0.95):
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.configure(bg=KEY_COLOR)
        try:
            self.top.attributes("-transparentcolor", KEY_COLOR)
            self.top.attributes("-alpha", alpha)
        except tk.TclError:
            pass
        self.w, self.h = w, h
        self.canvas = tk.Canvas(self.top, width=w, height=h, bg=KEY_COLOR, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.bg_img = rounded_image(w, h, h // 2, CARD, (EDGE_HI, EDGE))
        self.canvas.create_image(0, 0, image=self.bg_img, anchor="nw")

    def place(self, x, y):
        self.top.geometry("%dx%d+%d+%d" % (self.w, self.h, x, y))

    def destroy(self):
        self.top.destroy()


class ScreenOverlay:
    """A frozen screenshot of one monitor: drag a box (mode 'box') or click a spot (mode 'point')."""

    def __init__(self, root, mon, image, mode, hint, on_done):
        self.mon, self.image, self.mode, self.on_done = mon, image, mode, on_done
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.geometry("%dx%d+%d+%d" % (mon["width"], mon["height"], mon["left"], mon["top"]))
        self.canvas = tk.Canvas(self.top, width=mon["width"], height=mon["height"], highlightthickness=0,
                                bd=0, cursor="crosshair", bg="black")
        self.canvas.pack()
        self.photo = ImageTk.PhotoImage(image)
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        f = font_obj((FONT_SEMI, 12))
        text = hint + "      Esc = cancel"
        w, h = f.measure(text) + px(48), f.metrics("linespace") + px(22)
        self.hint_img = rounded_image(w, h, h // 2, CARD, (EDGE_HI, EDGE))
        cx = mon["width"] // 2
        self.canvas.create_image(cx - w // 2, px(24), image=self.hint_img, anchor="nw")
        self.canvas.create_text(cx, px(24) + h // 2, text=text, fill=TEXT, font=(FONT_SEMI, 12))
        self.start = None
        self.rect = None
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.top.bind("<Escape>", lambda e: self._finish(None))
        self.top.after(50, self._grab_focus)

    def _grab_focus(self):
        try:
            self.top.focus_force()
            self.top.grab_set()
        except tk.TclError:
            pass

    def _press(self, e):
        if self.mode == "point":
            self._finish((self.mon["left"] + e.x, self.mon["top"] + e.y))
            return
        self.start = (e.x, e.y)
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(e.x, e.y, e.x, e.y, outline=ACCENT, width=2)

    def _drag(self, e):
        if self.mode == "box" and self.start and self.rect:
            self.canvas.coords(self.rect, self.start[0], self.start[1], e.x, e.y)

    def _release(self, e):
        if self.mode != "box" or not self.start:
            return
        x0, x1 = sorted((self.start[0], e.x))
        y0, y1 = sorted((self.start[1], e.y))
        if x1 - x0 < 8 or y1 - y0 < 8:
            self.start = None
            if self.rect:
                self.canvas.delete(self.rect)
                self.rect = None
            return
        self._finish(self.image.crop((x0, y0, x1, y1)))

    def _finish(self, result):
        try:
            self.top.grab_release()
        except tk.TclError:
            pass
        self.top.destroy()
        self.on_done(result)


class SettingsWindow:
    NAV = ("Keybinds", "Timings", "Pictures", "Failsafe", "Discord", "Reconnect", "App")

    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg
        self.top = tk.Toplevel(app.root)
        self.top.withdraw()
        self.top.title("%s - Settings" % APP_NAME)
        self.top.configure(bg=BG)
        self.top.minsize(px(660), px(480))
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        self.keys = dict(self.cfg["keys"])
        self.binding = None
        self.pages = {}
        self.nav_items = {}
        self.pic_rows = {}

        foot = tk.Frame(self.top, bg=BG)
        foot.pack(side="bottom", fill="x", padx=px(20), pady=(px(10), px(16)))
        Btn(foot, "Save", self.save, "primary", padx=px(22)).pack(side="right")
        Btn(foot, "Close", self.close, padx=px(18)).pack(side="right", padx=px(8))
        self.msg = label(foot, "", 9, MUTED, wraplength=px(500), justify="left")
        self.msg.pack(side="left")

        body = tk.Frame(self.top, bg=BG)
        body.pack(fill="both", expand=True, padx=(px(14), px(20)), pady=(px(18), 0))
        nav = tk.Frame(body, bg=BG)
        nav.pack(side="left", fill="y", padx=(0, px(16)))
        label(nav, "SETTINGS", 8, DIM, True).pack(anchor="w", padx=px(15), pady=(0, px(8)))
        for name in self.NAV:
            item = tk.Frame(nav, bg=BG, cursor="hand2")
            item.pack(fill="x", pady=px(1))
            bar = tk.Frame(item, bg=BG, width=px(3))
            bar.pack(side="left", fill="y", pady=px(7))
            lbl = tk.Label(item, text=name, bg=BG, fg=MUTED, font=(FONT_SEMI, 10), anchor="w",
                           padx=px(12), pady=px(7), width=11, cursor="hand2")
            lbl.pack(side="left", fill="x")
            for w in (item, bar, lbl):
                w.bind("<Button-1>", lambda e, n=name: self.show_page(n))
                w.bind("<Enter>", lambda e, n=name: self._nav_hover(n, True))
                w.bind("<Leave>", lambda e, n=name: self._nav_hover(n, False))
            self.nav_items[name] = (bar, lbl)
        self.content = tk.Frame(body, bg=BG)
        self.content.pack(side="left", fill="both", expand=True)
        self.page_name = None

        self.build_keys()
        self.build_timings()
        self.build_pictures()
        self.build_failsafe()
        self.build_discord()
        self.build_reconnect()
        self.build_app()
        self.show_page("Keybinds")
        self.top.bind("<KeyPress>", self._key)
        fit_geometry(self.top, px(800), px(720))
        if not app.headless:
            present(self.top)

    # ---- generic -----------------------------------------------------------------------------
    def _nav_hover(self, name, on):
        if name != self.page_name:
            self.nav_items[name][1].configure(fg=TEXT if on else MUTED)

    def show_page(self, name):
        for n, page in self.pages.items():
            page.pack_forget()
            bar, lbl = self.nav_items[n]
            bar.configure(bg=BG)
            lbl.configure(fg=MUTED)
        self.pages[name].pack(fill="both", expand=True)
        redraw_cards(self.pages[name])
        bar, lbl = self.nav_items[name]
        bar.configure(bg=ACCENT)
        lbl.configure(fg=TEXT)
        self.page_name = name
        if name == "Reconnect":
            self.refresh_reconnect_status()

    def note(self, text, color=MUTED):
        self.msg.configure(text=text, fg=color)

    def close(self):
        self.app.binding = False
        self.app.settings = None
        self.top.destroy()

    def page_title(self, parent, title, sub):
        label(parent, title, 17, TEXT, True).pack(anchor="w", pady=(0, px(2)))
        label(parent, sub, 9, MUTED, wraplength=px(540), justify="left").pack(anchor="w", pady=(0, px(14)))

    def section(self, parent, title, sub=None):
        f = card(parent)
        f.pack(fill="x", pady=(0, px(12)))
        label(f, title, 11, TEXT, True).pack(anchor="w", padx=px(18), pady=(px(14), 0))
        if sub:
            label(f, sub, 9, MUTED, wraplength=px(500), justify="left").pack(anchor="w", padx=px(18), pady=(px(2), 0))
        inner = tk.Frame(f, bg=CARD)
        inner.pack(fill="x", padx=px(18), pady=(px(10), px(16)))
        return inner

    def row(self, parent, title, hint=""):
        r = tk.Frame(parent, bg=CARD)
        r.pack(fill="x", pady=px(5))
        left = tk.Frame(r, bg=CARD)
        left.pack(side="left", fill="x", expand=True)
        label(left, title, 10).pack(anchor="w")
        if hint:
            label(left, hint, 8, DIM, wraplength=px(340), justify="left").pack(anchor="w")
        right = tk.Frame(r, bg=CARD)
        right.pack(side="right", anchor="n", padx=(px(12), 0))
        return right

    def switch(self, parent, title, var, hint="", command=None):
        Toggle(self.row(parent, title, hint), var, command).pack(side="right")

    def spot_row(self, parent, title, hint, value, on_change):
        """A row with a screen spot: shows it, Pick (click on the screen) and Clear."""
        right = self.row(parent, title, hint)
        state = {"value": value}
        lbl = label(right, "", 9, MUTED)

        def show():
            v = state["value"]
            lbl.configure(text=("%d, %d" % (v[0], v[1])) if v else "not set", fg=TEXT if v else BAD)

        def pick():
            def done(pt):
                if pt:
                    state["value"] = [int(pt[0]), int(pt[1])]
                    show()
                    on_change(state["value"])
                    self.note("%s picked - press Save to keep it" % title)
            self.app.screen_task("point", "Click: %s" % title, done)

        def clear():
            state["value"] = None
            show()
            on_change(None)
        Btn(right, "Clear", clear, "ghost", padx=px(10), pady=px(5), font=(FONT_SEMI, 9)).pack(side="right")
        Btn(right, "Pick", pick, padx=px(12), pady=px(5), font=(FONT_SEMI, 9)).pack(side="right", padx=px(4))
        lbl.pack(side="right", padx=px(8))
        show()
        return state

    # ---- Keybinds ----------------------------------------------------------------------------
    def build_keys(self):
        page = ScrollFrame(self.content)
        self.pages["Keybinds"] = page
        inner = page.inner
        self.page_title(inner, "Keybinds", "Click a key, then press the new one. Game keys must match your AOTR binds.")
        hot = self.section(inner, "Hotkeys", "Work while Roblox is focused.")
        game = self.section(inner, "Game keys", "What the macro presses in the game.")
        self.key_btns = {}
        for name, text, hint in KEY_ROWS:
            right = self.row(hot if name in HOTKEYS else game, text, hint)
            b = Btn(right, key_display(self.keys[name]), lambda n=name: self.begin_bind(n), width=9, pady=px(6))
            b.pack(side="right")
            self.key_btns[name] = b
        Btn(inner, "Reset keys to default", self.reset_keys, "ghost").pack(anchor="w", pady=(0, px(10)))

    def key_label(self, name):
        return dict((r[0], r[1]) for r in KEY_ROWS)[name]

    def begin_bind(self, name):
        if self.binding:
            self.key_btns[self.binding].set_text(key_display(self.keys[self.binding]))
        self.binding = name
        self.app.binding = True
        self.key_btns[name].set_text("Press a key")
        self.note("Press the new key for '%s' (Esc = cancel)" % self.key_label(name))
        self.top.focus_force()

    def _key(self, e):
        if not self.binding:
            return
        name = self.binding
        if e.keysym == "Escape":
            self.key_btns[name].set_text(key_display(self.keys[name]))
            self.note("")
        else:
            key = keysym_to_name(e.keysym)
            if key is None:
                self.note("That key can't be used - pick another one", BAD)
                return "break"
            self.keys[name] = key
            self.key_btns[name].set_text(key_display(key))
            self.note("%s set to %s - press Save to keep it" % (self.key_label(name), key_display(key)))
        self.binding = None
        self.top.after(300, lambda: self.binding is None and setattr(self.app, "binding", False))
        return "break"

    def reset_keys(self):
        self.keys = dict(DEFAULT_KEYS)
        for name, b in self.key_btns.items():
            b.set_text(key_display(self.keys[name]))
        self.note("Keys reset - press Save to keep them")

    # ---- Timings -----------------------------------------------------------------------------
    def build_timings(self):
        page = tk.Frame(self.content, bg=BG)
        self.pages["Timings"] = page
        self.page_title(page, "Timings", "Every value has a short explanation. Shared is used by every routine.")
        self.tsec_var = tk.StringVar(value=self.cfg["routine"])
        Segmented(page, self.tsec_var, TIMING_SECTIONS, command=self.show_tsec).pack(anchor="w", pady=(0, px(12)))
        holder = tk.Frame(page, bg=BG)
        holder.pack(fill="both", expand=True)
        self.tsec_frames = {}
        self.timing_widgets = {}
        self.spot_states = {}
        for sec in TIMING_SECTIONS:
            sf = ScrollFrame(holder)
            self.tsec_frames[sec] = sf
            if sec in ("Blood Awakening", "Shiki", "Universal"):
                box = self.section(sf.inner, "Presets",
                                   "Speed: smart shift wait, ability 4 spam that stops once used, fast retry and shorter "
                                   "dead waits (after ability 2, before the last ability 5, after retry). Dash and strafe "
                                   "stay yours - the Speed finder (Blood Awakening) can shorten them by testing. The Runs "
                                   "tab shows how long each step took.")
                pr = tk.Frame(box, bg=CARD)
                pr.pack(anchor="w")
                Btn(pr, "Load speed preset", lambda s_=sec: self.load_preset(s_, True), "primary").pack(side="left")
                Btn(pr, "Load defaults", lambda s_=sec: self.load_preset(s_, False)).pack(side="left", padx=px(8))
                if sec == "Universal":
                    box2 = self.section(sf.inner, "Universal style",
                                        "Normal: Order: Advance on key 2, meteor then triple thunder spear. Rage: Order: "
                                        "Rage on key 2 instead (more damage - Avatar of Ymir not needed), same sequence.")
                    pr2 = tk.Frame(box2, bg=CARD)
                    pr2.pack(anchor="w")
                    Btn(pr2, "Normal preset", lambda: self.load_preset("Universal", "normal")).pack(side="left")
                    Btn(pr2, "Rage preset", lambda: self.load_preset("Universal", "rage"), "primary").pack(
                        side="left", padx=px(8))
            groups = []
            for f in FIELDS[sec]:
                if f.group not in groups:
                    groups.append(f.group)
            for g in groups:
                box = self.section(sf.inner, g)
                for f in [f for f in FIELDS[sec] if f.group == g]:
                    value = self.cfg["timings"][sec][f.key]
                    if f.kind == "spot":
                        self.spot_states[(sec, f.key)] = self.spot_row(box, f.label, f.help, value, lambda v: None)
                        continue
                    right = self.row(box, f.label, f.help)
                    self.timing_widgets[(sec, f.key)] = self._timing_input(right, f, value)
            Btn(sf.inner, "Reset %s to default" % sec, lambda s=sec: self.reset_timings(s), "ghost").pack(
                anchor="w", pady=(0, px(10)))
        self.show_tsec(self.cfg["routine"])

    def show_tsec(self, sec):
        if self.tsec_var.get() != sec:
            self.tsec_var.set(sec)
        for sf in self.tsec_frames.values():
            sf.pack_forget()
        self.tsec_frames[sec].pack(fill="both", expand=True)
        redraw_cards(self.tsec_frames[sec])

    def _timing_input(self, parent, f, value):
        if f.kind == "bool":
            var = tk.BooleanVar(value=bool(value))
            Toggle(parent, var).pack(side="right")
            return ("bool", var)
        if f.kind == "choice":
            var = tk.StringVar(value=value)
            Segmented(parent, var, f.lo, accent=False, track=FIELD_BG).pack(side="right")
            return ("choice", var)
        unit = {"sec": "s", "pix": "px", "range": "s", "num": "", "int": ""}[f.kind]
        if f.kind == "range":
            e1, e2 = entry(parent, 6), entry(parent, 6)
            e1.insert(0, "%g" % value[0])
            e2.insert(0, "%g" % value[1])
            label(parent, unit, 9, DIM).pack(side="right", padx=(px(6), 0))
            e2.pack(side="right", ipady=px(3))
            label(parent, "to", 9, DIM).pack(side="right", padx=px(6))
            e1.pack(side="right", ipady=px(3))
            return ("range", (e1, e2))
        e = entry(parent, 7)
        e.insert(0, "%g" % value)
        if unit:
            label(parent, unit, 9, DIM).pack(side="right", padx=(px(6), 0))
        e.pack(side="right", ipady=px(3))
        return ("num", e)

    def set_timing(self, sec, key, value):
        kind, w = self.timing_widgets[(sec, key)]
        if kind in ("bool", "choice"):
            w.set(value)
        elif kind == "range":
            for e, v in zip(w, value):
                e.delete(0, "end")
                e.insert(0, "%g" % v)
        else:
            w.delete(0, "end")
            w.insert(0, "%g" % value)

    def reset_timings(self, sec):
        for f in FIELDS[sec]:
            if f.kind != "spot":  # picked spots are kept
                self.set_timing(sec, f.key, f.default)
        self.note("%s timings reset - press Save to keep them" % sec)

    def load_preset(self, sec, speed):
        if speed in ("rage", "normal"):
            rage = speed == "rage"
            self.set_timing("Universal", "rage", rage)
            msg = ("Rage preset loaded: Order: Rage on key 2 - press Save" if rage
                   else "Normal preset loaded: Order: Advance on key 2 - press Save")
            self.note(msg, GOOD)
            return
        if speed:
            for key, v in SPEED_PRESET["Shared"].items():
                self.set_timing("Shared", key, v)
            for key, v in SPEED_PRESET["routine"].items():
                self.set_timing(sec, key, v)
            self.note("Speed preset loaded for %s (+ Shared) - press Save" % sec, GOOD)
        else:
            self.reset_timings("Shared")
            self.reset_timings(sec)
            self.note("Default timings loaded for %s and Shared - press Save" % sec)

    def read_timings(self):
        out, bad = {sec: {} for sec in TIMING_SECTIONS}, []
        for sec in TIMING_SECTIONS:
            for f in FIELDS[sec]:
                if f.kind == "spot":
                    out[sec][f.key] = self.spot_states[(sec, f.key)]["value"]
                    continue
                kind, w = self.timing_widgets[(sec, f.key)]
                if kind in ("bool", "choice"):
                    raw = w.get()
                elif kind == "range":
                    raw = (w[0].get().strip(), w[1].get().strip())
                else:
                    raw = w.get().strip()
                v = clean_value(f, raw)
                widgets = w if kind == "range" else (w,) if kind == "num" else ()
                for e in widgets:
                    e.configure(highlightbackground=EDGE_HI if v is not None else BAD)
                if v is None:
                    bad.append((sec, f))
                else:
                    out[sec][f.key] = v
        return out, bad

    # ---- Pictures ----------------------------------------------------------------------------
    def build_pictures(self):
        page = ScrollFrame(self.content)
        self.pages["Pictures"] = page
        inner = page.inner
        self.page_title(inner, "Pictures", "What the macro looks for on your screen. The built-in ones are from a 1080p "
                                           "screen and get scaled. If one isn't found, capture your own: get it on "
                                           "screen in Roblox, press Capture, switch to Roblox within 3 seconds and "
                                           "drag a box around it.")
        top = self.section(inner, "Test", "Switch to Roblox within 3 seconds - the macro lists what it can see.")
        r = tk.Frame(top, bg=CARD)
        r.pack(fill="x")
        Btn(r, "Test detection now", self.test_detection, "primary").pack(side="left")
        Btn(r, "Open pictures folder", self.open_pictures_folder).pack(side="left", padx=px(8))
        self.test_out = label(top, "Nothing tested yet.", 9, DIM, wraplength=px(500), justify="left")
        self.test_out.pack(anchor="w", pady=(px(8), 0))
        subs = {"Detection": "Used by every routine.",
                "Results": "Read on the end screen to count completed / failed runs. Not counted on your screen? "
                           "Press 'End screen' and drag a box around the title on your last end screen.",
                "Loot": "Each icon seen on the end screen counts once.",
                "Shiki": "Only used by the Shiki routine.",
                "Female Raid": "Only used by the Female Raid routine.",
                "Smart waits": "Built in. With Smart shift wait on, your own 'Shifted' picture is saved by itself "
                               "during the first run (Auto-learn) - capture one here only if that doesn't work.",
                "Reconnect": "Only used by auto-reconnect. There are no built-in ones - capture your own."}
        for group in PICTURE_GROUPS:
            sec = self.section(inner, group, subs[group])
            for key in [k for k, p in PICTURES.items() if p["group"] == group]:
                self.picture_row(sec, key)

    def picture_row(self, parent, key):
        r = tk.Frame(parent, bg=CARD)
        r.pack(fill="x", pady=px(5))
        holder = RoundCard(r, fill=FIELD_BG, edge=(EDGE, EDGE), radius=px(10), width=px(150), height=px(48))
        holder.pack_propagate(False)
        holder.pack(side="left")
        prev = tk.Label(holder, bg=FIELD_BG)
        prev.pack(expand=True)
        info = tk.Frame(r, bg=CARD)
        info.pack(side="left", fill="x", expand=True, padx=px(12))
        label(info, PICTURES[key]["label"], 10).pack(anchor="w")
        src = label(info, "", 8, MUTED)
        src.pack(anchor="w")
        btns = tk.Frame(r, bg=CARD)
        btns.pack(side="right")
        Btn(btns, "Capture", lambda k=key: self.capture(k), padx=px(12), pady=px(5), font=(FONT_SEMI, 9)).pack(side="left")
        if PICTURES[key]["group"] in ("Results", "Loot"):
            Btn(btns, "End screen", lambda k=key: self.capture_end_screen(k), padx=px(10), pady=px(5),
                font=(FONT_SEMI, 9)).pack(side="left", padx=(px(4), 0))
        reset = Btn(btns, "Use built-in" if PICTURES[key]["files"] else "Remove", lambda k=key: self.reset_picture(k),
                    "ghost", padx=px(10), pady=px(5), font=(FONT_SEMI, 9))
        reset.pack(side="left", padx=(px(4), 0))
        self.pic_rows.setdefault(key, []).append((prev, src, reset))
        self.refresh_picture(key)

    def refresh_picture(self, key):
        own = own_picture_path(key)
        has_own = os.path.isfile(own)
        files = PICTURES[key]["files"]
        path = own if has_own else (resource_path("assets", *files["normal"].split("/")) if files else None)
        for prev, src, reset in self.pic_rows.get(key, []):
            try:
                if not path:
                    raise FileNotFoundError
                img = Image.open(path).convert("RGB")
                img.thumbnail((px(138), px(38)))
                photo = ImageTk.PhotoImage(img)
                prev.configure(image=photo, text="")
                prev.image = photo
            except Exception:
                prev.configure(image="", text="none", fg=DIM, font=(FONT, 9))
                prev.image = None
            if has_own and key == "shifted" and self.cfg.get("learned", {}).get("shifted"):
                src.configure(text="Learned by itself (yours)", fg=ACCENT_SOFT)
            elif has_own:
                src.configure(text="Using your picture", fg=ACCENT_SOFT)
            elif files:
                src.configure(text="Built-in picture", fg=MUTED)
            else:
                src.configure(text="Not set - capture one", fg=BAD if PICTURES[key]["group"] == "Reconnect" else DIM)
            reset.set_enabled(has_own)

    def open_pictures_folder(self):
        os.makedirs(PICTURES_DIR, exist_ok=True)
        os.startfile(PICTURES_DIR)

    def capture(self, key):
        self.app.screen_task("box", "Drag a box around: %s" % PICTURES[key]["label"],
                             lambda img: self._capture_done(key, img))

    def _capture_done(self, key, img):
        if img is None:
            self.note("Capture cancelled")
            return
        os.makedirs(PICTURES_DIR, exist_ok=True)
        img.convert("RGB").save(own_picture_path(key))
        if key in SCALE_OF:
            self.cfg[SCALE_OF[key]] = None
            save_config(self.cfg)
        if key == "shifted" and self.cfg["learned"].pop("shifted", None) is not None:
            save_config(self.cfg)  # captured by hand now, not learned
        self.refresh_picture(key)
        self.refresh_reconnect_status()
        self.note("Saved your %s picture - used from the next Start" % PICTURES[key]["label"], GOOD)

    def capture_end_screen(self, key):
        """Capture a result / loot picture from the last end screen the macro couldn't read (no rush to switch)."""
        path = end_screen_path()
        if not os.path.isfile(path):
            self.note("No saved end screen yet - the macro saves one when it can't read a result during a run", WARN)
            return
        try:
            img = Image.open(path).convert("RGB")
        except Exception as e:
            self.note("Could not open the saved end screen (%s)" % e, BAD)
            return
        mons = list_monitors()
        cur = self.app._current_monitor()
        fits = [m for m in [cur] + mons if m["width"] == img.width and m["height"] == img.height]
        try:  # windowed game: shown where the game window was
            with open(path + ".json", "r", encoding="utf-8") as fh:
                spot = json.load(fh)
            if (spot["width"], spot["height"]) == img.size:
                fits.insert(0, {"left": int(spot["left"]), "top": int(spot["top"]), "width": img.width,
                                "height": img.height})
        except Exception:
            pass
        if not fits:
            self.note("The saved end screen is %dx%d - none of your screens has that size now" % img.size, BAD)
            return
        self.app.image_task(fits[0], img, "Drag a box around: %s  (your last end screen)" % PICTURES[key]["label"],
                            lambda crop: self._capture_done(key, crop))


    def reset_picture(self, key):
        path = own_picture_path(key)
        if os.path.isfile(path):
            os.remove(path)
            if key in SCALE_OF:
                self.cfg[SCALE_OF[key]] = None
                save_config(self.cfg)
            if key == "shifted" and self.cfg["learned"].pop("shifted", None) is not None:
                save_config(self.cfg)  # gone: Auto-learn may save a new one
        self.refresh_picture(key)
        self.refresh_reconnect_status()
        self.note(("Back to the built-in %s picture" if PICTURES[key]["files"] else "Removed your %s picture")
                  % PICTURES[key]["label"])

    def test_detection(self):
        self.test_out.configure(text="Switch to Roblox now...", fg=WARN)

        def done(lines):
            self.test_out.configure(text="\n".join(lines), fg=TEXT)
            for line in lines:
                self.app.add_log("Test: " + line)
        self.app.detection_test(done)

    # ---- Failsafe ----------------------------------------------------------------------------
    def build_failsafe(self):
        page = ScrollFrame(self.content)
        self.pages["Failsafe"] = page
        inner = page.inner
        fs = self.cfg["failsafe"]
        self.page_title(inner, "Failsafe", "If a mission runs too long, the macro ejects (ability 2), waits 15s, then "
                                           "clicks until the retry button shows up. The Female Raid has its own "
                                           "3 minute limit.")
        sec = self.section(inner, "Stuck mission")
        self.fs_enabled = tk.BooleanVar(value=fs["enabled"])
        self.switch(sec, "Failsafe on", self.fs_enabled)
        right = self.row(sec, "Mission is stuck after", "Seconds, at least 10.")
        self.fs_seconds = entry(right, 7)
        self.fs_seconds.insert(0, "%g" % fs["seconds"])
        label(right, "s", 9, DIM).pack(side="right", padx=(px(6), 0))
        self.fs_seconds.pack(side="right", ipady=px(3))

        sec2 = self.section(inner, "Look at the ground first", "Shift lock, the mouse is dragged down, shift lock.")
        self.fs_look = tk.BooleanVar(value=fs["look_down"])
        self.switch(sec2, "Look down before clicking", self.fs_look)
        right = self.row(sec2, "Look down time")
        self.fs_look_time = entry(right, 6)
        self.fs_look_time.insert(0, "%g" % fs["look_time"])
        label(right, "s", 9, DIM).pack(side="right", padx=(px(6), 0))
        self.fs_look_time.pack(side="right", ipady=px(3))
        right = self.row(sec2, "Pixels every 0.01s")
        self.fs_look_px = entry(right, 6)
        self.fs_look_px.insert(0, "%g" % fs["look_pixels"])
        label(right, "px", 9, DIM).pack(side="right", padx=(px(6), 0))
        self.fs_look_px.pack(side="right", ipady=px(3))

        sec3 = self.section(inner, "Click spot", "Not set = bottom-middle of the screen (50% X, 80% Y).")
        start = [fs["click_x"], fs["click_y"]] if fs["click_x"] is not None else None
        self.fs_point = self.spot_row(sec3, "Failsafe click spot", "", start, lambda v: None)

    # ---- Discord -----------------------------------------------------------------------------
    def build_discord(self):
        page = ScrollFrame(self.content)
        self.pages["Discord"] = page
        inner = page.inner
        d = self.cfg["discord"]
        self.page_title(inner, "Discord", "A message after every run (result, loot, time) and alerts for the failsafe, "
                                          "rejoins and errors. A bot also takes commands: " + BOT_COMMANDS_TEXT)
        sec = self.section(inner, "Mode")
        self.dc_mode = tk.StringVar(value=d["mode"])
        Segmented(sec, self.dc_mode, [("off", "Off"), ("webhook", "Webhook"), ("bot", "Bot + commands")]).pack(anchor="w")

        sec2 = self.section(inner, "Webhook", "Server Settings > Integrations > Webhooks > New Webhook > Copy Webhook URL.")
        self.dc_url = entry(sec2, 60)
        self.dc_url.insert(0, d["url"])
        self.dc_url.pack(fill="x", ipady=px(4))

        sec3 = self.section(inner, "Bot",
                            "discord.com/developers > New Application > Bot: Reset Token (copy it) and turn on MESSAGE "
                            "CONTENT INTENT. OAuth2 > URL Generator: scope 'bot' with View Channel, Send Messages, Read "
                            "Message History and Attach Files; open the link to add it to your server. Channel ID: "
                            "Developer Mode on, right-click the channel > Copy Channel ID. The token is saved in "
                            "config.json on this PC - don't share that file.")
        right = self.row(sec3, "Bot token")
        self.dc_token = entry(right, 36, show="•")
        self.dc_token.insert(0, d["bot_token"])
        self.dc_token.pack(side="right", ipady=px(3))
        right = self.row(sec3, "Channel ID")
        self.dc_channel = entry(right, 24)
        self.dc_channel.insert(0, d["channel_id"])
        self.dc_channel.pack(side="right", ipady=px(3))

        sec4 = self.section(inner, "You",
                            "Your Discord user ID (Developer Mode on, right-click yourself > Copy User ID). Needed to ping "
                            "you and for bot commands - only these IDs can control the macro. Several: separate with commas.")
        right = self.row(sec4, "Your user ID(s)")
        self.dc_user = entry(right, 28)
        self.dc_user.insert(0, d["user_id"])
        self.dc_user.pack(side="right", ipady=px(3))
        self.dc_vars = {}
        for name, text in (("mention", "Ping me in the alerts"),
                           ("notify_mission", "Message after every mission / raid"),
                           ("screenshot", "Add a screenshot of the end screen"),
                           ("notify_failsafe", "Message when the failsafe kicks in"),
                           ("notify_reconnect", "Message when the game is rejoined"),
                           ("notify_error", "Message when the macro stops on an error"),
                           ("notify_graph", "Stats graph every hour while it runs (also: !graph)")):
            v = tk.BooleanVar(value=d[name])
            self.switch(sec4, text, v)
            self.dc_vars[name] = v
        r = tk.Frame(sec4, bg=CARD)
        r.pack(fill="x", pady=(px(10), 0))
        Btn(r, "Send test message", self.discord_test).pack(side="left")
        Btn(r, "Send stats graph", lambda: self.app.send_graph(note=self.note)).pack(side="left", padx=(px(8), 0))
        self.dc_test = label(r, "", 9, MUTED)
        self.dc_test.pack(side="left", padx=px(10))

    def read_discord(self):
        out = {"mode": self.dc_mode.get(), "url": self.dc_url.get().strip(), "bot_token": self.dc_token.get().strip(),
               "channel_id": self.dc_channel.get().strip(), "user_id": self.dc_user.get().strip()}
        for name, v in self.dc_vars.items():
            out[name] = v.get()
        return out

    def discord_test(self):
        self.dc_test.configure(text="Sending...", fg=WARN)
        self.app.discord.test(self.read_discord(), lambda ok, msg: self.app.q.put(("discord_test", ok, msg)))

    def discord_test_result(self, ok, msg):
        if self.top.winfo_exists():
            self.dc_test.configure(text=msg, fg=GOOD if ok else BAD)

    # ---- Reconnect ---------------------------------------------------------------------------
    def build_reconnect(self):
        page = ScrollFrame(self.content)
        self.pages["Reconnect"] = page
        inner = page.inner
        rc = self.cfg["reconnect"]
        self.page_title(inner, "Reconnect", "On Roblox's Disconnected message, a 2 minute failsafe, or the bot's "
                                            "!reconnect: Roblox is closed, AOTR is launched again and the spots below "
                                            "are clicked in order. Then the macro waits for the next mission as usual.")
        sec = self.section(inner, "Auto-reconnect")
        self.rc_enabled = tk.BooleanVar(value=rc["enabled"])
        self.switch(sec, "Auto-reconnect on", self.rc_enabled, command=self.refresh_reconnect_status)
        self.rc_status = label(sec, "", 9, MUTED, wraplength=px(500), justify="left")
        self.rc_status.pack(anchor="w", pady=(px(4), 0))
        Btn(sec, "Rejoin now (test)", self.reconnect_test).pack(anchor="w", pady=(px(10), 0))

        pics = self.section(inner, "Pictures", "Capture each one while it is on screen.")
        for key in RECONNECT_PICTURES:
            self.picture_row(pics, key)

        self.rc_spots = dict(rc["spots"])

        def setter(key):
            def change(v):
                if v:
                    self.rc_spots[key] = v
                else:
                    self.rc_spots.pop(key, None)
                self.refresh_reconnect_status()
            return change
        for title, spots in (("Spots - every reconnect", RECONNECT_SHARED_SPOTS),
                             ("Spots - Missions", RECONNECT_TAB_SPOTS["Missions"]),
                             ("Spots - Raids (Female Raid)", RECONNECT_TAB_SPOTS["Raids"])):
            box = self.section(inner, title, "Pick = switch to Roblox within 3 seconds, then click the button.")
            for key, name in spots:
                gate = RECONNECT_GATES.get(key)
                hint = ("Clicked after the '%s' picture shows." % PICTURES[gate]["label"]) if gate else ""
                self.spot_row(box, name, hint, rc["spots"].get(key), setter(key))

        d = self.section(inner, "Delays")
        right = self.row(d, "Seconds between clicks")
        self.rc_click_delay = entry(right, 6)
        self.rc_click_delay.insert(0, "%g" % rc["click_delay"])
        self.rc_click_delay.pack(side="right", ipady=px(3))
        right = self.row(d, "Seconds between Create and Play")
        self.rc_play_delay = entry(right, 6)
        self.rc_play_delay.insert(0, "%g" % rc["play_delay"])
        self.rc_play_delay.pack(side="right", ipady=px(3))

    def refresh_reconnect_status(self):
        if not hasattr(self, "rc_status"):
            return
        tmp = {"reconnect": {"spots": getattr(self, "rc_spots", self.cfg["reconnect"]["spots"])}}
        lines = []
        for raid, name in ((False, "Missions"), (True, "Female Raid")):
            missing = reconnect_missing(tmp, raid)
            pics = sum(1 for m in missing if m.endswith(" picture"))
            spots = len(missing) - pics
            need = []
            if pics:
                need.append("%d picture%s" % (pics, "" if pics == 1 else "s"))
            if spots:
                need.append("%d click spot%s" % (spots, "" if spots == 1 else "s"))
            lines.append("%s   \u00b7   %s" % (name, "ready" if not need else "needs " + " and ".join(need)))
        on = self.rc_enabled.get()
        self.rc_status.configure(text="\n".join(lines), fg=TEXT if on else MUTED)

    def reconnect_test(self):
        eng = self.app.engine
        if not eng.running():
            self.note("Start the macro first - the test rejoin runs inside it", WARN)
            return
        if not eng.reconnect_on:
            self.note("Reconnect isn't active: turn it on, set everything up, Save, then Stop and Start the macro", WARN)
            return
        if messagebox.askyesno(APP_NAME, "This closes Roblox and rejoins AOTR right now. Continue?", parent=self.top):
            eng.rc_request = True
            self.note("Rejoining...", GOOD)

    # ---- App ---------------------------------------------------------------------------------
    def build_app(self):
        page = ScrollFrame(self.content)
        self.pages["App"] = page
        inner = page.inner
        a = self.cfg["app"]
        self.page_title(inner, "App", "How the app behaves while the macro runs.")
        sec = self.section(inner, "While running")
        self.app_vars = {}
        for name, text in (("mini_bar", "Small status bar at the top of the screen"),
                           ("minimize_on_start", "Minimize this window when the macro starts"),
                           ("focus_roblox", "Bring Roblox to the front when a mission starts"),
                           ("grab_check", "Press ability 1 on 'YOUR STREAK IS IN DANGER'"),
                           ("track_loot", "Read the result and loot on every end screen")):
            v = tk.BooleanVar(value=a[name])
            self.switch(sec, text, v)
            self.app_vars[name] = v
        secl = self.section(inner, "Session limits", "Stop by itself at the end of a run - handy overnight. "
                                                         "0 = no limit. It stops on the end screen without clicking retry.")
        right = self.row(secl, "Stop after this many runs")
        self.lim_runs = entry(right, 8)
        self.lim_runs.insert(0, str(a["stop_runs"]))
        self.lim_runs.pack(side="right", ipady=px(3))
        right = self.row(secl, "Stop after this many hours")
        self.lim_hours = entry(right, 8)
        self.lim_hours.insert(0, "%g" % a["stop_hours"])
        self.lim_hours.pack(side="right", ipady=px(3))
        self.lim_close = tk.BooleanVar(value=a["close_roblox_at_end"])
        self.switch(secl, "Close Roblox when a limit stops the macro", self.lim_close)
        sec2 = self.section(inner, "Screen", "The screen Roblox is on. Used for detection and clicks.")
        self.monitors = list_monitors()
        names = [monitor_label(i, m) for i, m in enumerate(self.monitors)]
        idx = a["monitor"] if a["monitor"] < len(names) else 0
        self.mon_var = tk.StringVar(value=names[idx])
        Dropdown(sec2, self.mon_var, names).pack(anchor="w")
        self.mon_names = names
        sec3 = self.section(inner, "Stats", "All-time counters (runs, results, loot) for missions and raids.")
        Btn(sec3, "Reset all-time stats", self.reset_stats, "danger").pack(anchor="w")
        sec4 = self.section(inner, "Files", "Settings, your pictures and the last session log are in:\n" + DATA_DIR)
        Btn(sec4, "Open folder", lambda: (os.makedirs(DATA_DIR, exist_ok=True), os.startfile(DATA_DIR))).pack(anchor="w")

    def reset_stats(self):
        if messagebox.askyesno(APP_NAME, "Reset all-time stats for missions and raids? This can't be undone.", parent=self.top):
            self.cfg["stats"] = {"missions": new_family_stats(), "raids": new_family_stats(), "best": {}}
            save_config(self.cfg)
            self.app.refresh_stats()
            self.note("All-time stats reset", GOOD)

    # ---- save --------------------------------------------------------------------------------
    def save(self):
        timings, bad = self.read_timings()
        if bad:
            sec, f = bad[0]
            self.show_page("Timings")
            self.show_tsec(sec)
            self.note("Fix the red boxes (%s): %s" % (sec, ", ".join(b[1].label for b in bad[:3])), BAD)
            return
        hot = [self.keys[h] for h in HOTKEYS]
        game = [self.keys[n] for n, _, _ in KEY_ROWS if n not in HOTKEYS]
        if len(set(hot)) < len(hot):
            self.show_page("Keybinds")
            self.note("The hotkeys (Start, Pause, Stop, Stop build scan) need different keys", BAD)
            return
        clash = [key_display(h) for h in hot if h in game]
        if clash:
            self.show_page("Keybinds")
            self.note("%s is a hotkey and a game key - change one of them" % clash[0], BAD)
            return
        try:
            secs = float(self.fs_seconds.get())
            look_time = float(self.fs_look_time.get())
            look_px = float(self.fs_look_px.get())
            if not (10 <= secs <= 3600 and 0.1 <= look_time <= 10 and 1 <= look_px <= 200):
                raise ValueError
        except ValueError:
            self.show_page("Failsafe")
            self.note("Failsafe: seconds 10-3600, look time 0.1-10, pixels 1-200", BAD)
            return
        try:
            click_delay = float(self.rc_click_delay.get())
            play_delay = float(self.rc_play_delay.get())
            if not (0 <= click_delay <= 60 and 0 <= play_delay <= 60):
                raise ValueError
        except ValueError:
            self.show_page("Reconnect")
            self.note("Reconnect delays must be 0-60 seconds", BAD)
            return
        try:
            stop_runs = int(self.lim_runs.get().strip() or "0")
            stop_hours = float(self.lim_hours.get().strip() or "0")
            if not (0 <= stop_runs <= 100000 and 0 <= stop_hours <= 72):
                raise ValueError
        except ValueError:
            self.show_page("App")
            self.note("Session limits: runs 0-100000, hours 0-72 (0 = no limit)", BAD)
            return
        dc = self.read_discord()
        if dc["mode"] == "webhook" and not webhook_valid(dc["url"]):
            self.show_page("Discord")
            self.note("That webhook URL doesn't look right (it starts with https://discord.com/api/webhooks/)", BAD)
            return
        if dc["mode"] == "bot" and not discord_ready(dc):
            self.show_page("Discord")
            self.note("Bot mode needs the bot token and a channel ID (numbers only)", BAD)
            return

        self.cfg["keys"].update(self.keys)
        for sec in TIMING_SECTIONS:
            self.cfg["timings"][sec].update(timings[sec])
        pt = self.fs_point["value"]
        self.cfg["failsafe"].update({"enabled": self.fs_enabled.get(), "seconds": secs, "look_down": self.fs_look.get(),
                                     "look_time": look_time, "look_pixels": look_px,
                                     "click_x": pt[0] if pt else None, "click_y": pt[1] if pt else None})
        self.cfg["discord"].update(dc)
        self.cfg["reconnect"].update({"enabled": self.rc_enabled.get(), "spots": dict(self.rc_spots),
                                      "click_delay": click_delay, "play_delay": play_delay})
        for name, v in self.app_vars.items():
            self.cfg["app"][name] = v.get()
        self.cfg["app"].update({"stop_runs": stop_runs, "stop_hours": stop_hours,
                                "close_roblox_at_end": self.lim_close.get()})
        new_mon = self.mon_names.index(self.mon_var.get()) if self.mon_var.get() in self.mon_names else 0
        if new_mon != self.cfg["app"]["monitor"]:
            self.cfg["retry_scale"] = None
            self.cfg["start_scale"] = None
            self.cfg["rage_scale"] = None
        self.cfg["app"]["monitor"] = new_mon
        ok = save_config(self.cfg)
        self.app.discord.restart_bot()
        self.app.refresh_hotkey_labels()
        self.app.refresh_build_page()
        running = self.app.engine.running()
        self.note(("Saved" if ok else "Saved for now (could not write the settings file)")
                  + (" - keys and timings apply right away; screen, pictures and reconnect on the next Start" if running else ""),
                  GOOD if ok else WARN)


class OptimiserEditWindow:
    """Fix what the scan read: perk levels, perks it missed, memories."""

    def __init__(self, app):
        self.app = app
        o = app.cfg["optimiser"]
        self.perks = dict(o["perks"])
        self.mems = list(o["memories"])
        self.top = tk.Toplevel(app.root)
        self.top.withdraw()
        self.top.title("%s - Your perks and memories" % APP_NAME)
        self.top.configure(bg=BG)
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        shell = tk.Frame(self.top, bg=BG)
        shell.pack(fill="both", expand=True, padx=px(16), pady=px(16))
        label(shell, "Your perks and memories", 14, TEXT, True).pack(anchor="w")
        label(shell, "What the scan read. Fix a level, add something it missed or remove something you no longer have.",
              9, MUTED).pack(anchor="w", pady=(px(2), px(12)))
        cols = tk.Frame(shell, bg=BG)
        cols.pack(fill="both", expand=True)
        cols.grid_columnconfigure(0, weight=3, uniform="c")
        cols.grid_columnconfigure(1, weight=2, uniform="c")
        cols.grid_rowconfigure(0, weight=1)
        pc = card(cols)
        pc.grid(row=0, column=0, sticky="nsew")
        mc = card(cols)
        mc.grid(row=0, column=1, sticky="nsew", padx=(px(12), 0))
        # perks
        pin = tk.Frame(pc, bg=CARD)
        pin.pack(fill="both", expand=True, padx=px(16), pady=px(14))
        label(pin, "PERKS", 7, ACCENT, True).pack(anchor="w")
        add = tk.Frame(pin, bg=CARD)
        add.pack(fill="x", pady=(px(8), px(8)))
        self.add_name = tk.StringVar(value="Pick a perk")
        Dropdown(add, self.add_name, sorted(bo.PERKS)).pack(side="left")
        self.add_lv = tk.StringVar(value="10")
        tk.Spinbox(add, from_=0, to=10, width=3, textvariable=self.add_lv, bg=FIELD_BG, fg=TEXT, bd=0,
                   buttonbackground=CARD2, insertbackground=TEXT, font=(FONT, 10)).pack(side="left", padx=px(8))
        Btn(add, "Add", self.add_perk, "normal", padx=px(12), pady=px(5), font=(FONT_SEMI, 9), radius=px(8)).pack(
            side="left")
        self.plist = ScrollFrame(pin, bg=CARD)
        self.plist.pack(fill="both", expand=True)
        # memories
        mmin = tk.Frame(mc, bg=CARD)
        mmin.pack(fill="both", expand=True, padx=px(16), pady=px(14))
        label(mmin, "MEMORIES", 7, ACCENT, True).pack(anchor="w")
        madd = tk.Frame(mmin, bg=CARD)
        madd.pack(fill="x", pady=(px(8), px(8)))
        self.add_mem = tk.StringVar(value="Pick a memory")
        Dropdown(madd, self.add_mem, sorted(bo.MEMORIES)).pack(side="left")
        Btn(madd, "Add", self.add_memory, "normal", padx=px(12), pady=px(5), font=(FONT_SEMI, 9), radius=px(8)).pack(
            side="left", padx=(px(8), 0))
        self.mlist = tk.Frame(mmin, bg=CARD)
        self.mlist.pack(fill="both", expand=True)
        foot = tk.Frame(shell, bg=BG)
        foot.pack(fill="x", pady=(px(12), 0))
        Btn(foot, "Save", self.save, "primary", padx=px(22), pady=px(8), font=(FONT_SEMI, 10), radius=px(10)).pack(
            side="right")
        Btn(foot, "Clear everything", self.clear, "danger", padx=px(16), pady=px(8), font=(FONT_SEMI, 9),
            radius=px(10)).pack(side="left")
        self.note = label(foot, "", 9, MUTED)
        self.note.pack(side="left", padx=px(12))
        self.fill()
        fit_geometry(self.top, px(820), px(600))
        dark_titlebar(self.top)
        present(self.top)

    def fill(self):
        for w in self.plist.inner.winfo_children():
            w.destroy()
        for w in self.mlist.winfo_children():
            w.destroy()
        order = sorted(self.perks, key=lambda n: (-bo.RARITIES.index(bo.PERKS[n]["rarity"]), n))
        if not order:
            label(self.plist.inner, "No perks yet - scan them on the Build optimiser page, or add them above.", 9,
                  DIM, bg=CARD).pack(anchor="w")
        for n in order:
            r = tk.Frame(self.plist.inner, bg=CARD)
            r.pack(fill="x", pady=px(2))
            label(r, n, 10, bo.RARITY_COLOR.get(bo.PERKS[n]["rarity"], TEXT), True, bg=CARD).pack(side="left")
            label(r, bo.PERKS[n]["rarity"], 8, DIM, bg=CARD).pack(side="left", padx=px(8))
            Btn(r, "Remove", lambda n_=n: self.remove_perk(n_), "ghost", padx=px(10), pady=px(3), font=(FONT_SEMI, 8),
                radius=px(7)).pack(side="right")
            v = tk.StringVar(value=str(self.perks[n]))
            sb = tk.Spinbox(r, from_=0, to=10, width=3, textvariable=v, bg=FIELD_BG, fg=TEXT, bd=0,
                            buttonbackground=CARD2, insertbackground=TEXT, font=(FONT, 10))
            sb.pack(side="right", padx=px(8))
            v.trace_add("write", lambda *a, n_=n, v_=v: self.set_level(n_, v_.get()))
            label(r, "+", 9, MUTED, bg=CARD).pack(side="right")
        if not self.mems:
            label(self.mlist, "No memories yet.", 9, DIM).pack(anchor="w")
        for m in self.mems:
            r = tk.Frame(self.mlist, bg=CARD)
            r.pack(fill="x", pady=px(2))
            label(r, m, 10, TEXT, True).pack(side="left")
            label(r, "%d-star" % bo.MEMORIES[m]["stars"], 8, DIM).pack(side="left", padx=px(8))
            Btn(r, "Remove", lambda m_=m: self.remove_memory(m_), "ghost", padx=px(10), pady=px(3),
                font=(FONT_SEMI, 8), radius=px(7)).pack(side="right")
        redraw_cards(self.top)

    def set_level(self, n, text):
        try:
            lv = int(text)
        except ValueError:
            return
        if 0 <= lv <= bo.MAX_LEVEL and n in self.perks:
            self.perks[n] = lv

    def add_perk(self):
        n = self.add_name.get()
        if n not in bo.PERKS:
            self.note.configure(text="Pick a perk first", fg=WARN)
            return
        try:
            lv = max(0, min(bo.MAX_LEVEL, int(self.add_lv.get())))
        except ValueError:
            lv = 0
        self.perks[n] = max(self.perks.get(n, -1), lv)
        self.note.configure(text="Added %s +%d" % (n, lv), fg=GOOD)
        self.fill()

    def remove_perk(self, n):
        self.perks.pop(n, None)
        self.fill()

    def add_memory(self):
        m = self.add_mem.get()
        if m not in bo.MEMORIES:
            self.note.configure(text="Pick a memory first", fg=WARN)
            return
        if m not in self.mems:
            self.mems.append(m)
        self.fill()

    def remove_memory(self, m):
        if m in self.mems:
            self.mems.remove(m)
        self.fill()

    def clear(self):
        if not messagebox.askyesno(APP_NAME, "Remove every perk and memory from the list?", parent=self.top):
            return
        self.perks, self.mems = {}, []
        self.fill()

    def save(self):
        o = self.app.cfg["optimiser"]
        o["perks"] = dict(self.perks)
        o["memories"] = [m for m in bo.MEMORIES if m in self.mems]
        if not self.perks:
            o["scanned_at"] = None
        elif not o["scanned_at"]:
            o["scanned_at"] = time.time()
        save_config(self.app.cfg)
        self.app.refresh_optimiser()
        self.top.destroy()

    def close(self):
        self.top.destroy()


class GuideWindow:
    def __init__(self, app, lines=None, title="How to use"):
        self.top = tk.Toplevel(app.root)
        self.top.withdraw()
        self.top.title("%s - %s" % (APP_NAME, title))
        self.top.configure(bg=BG)
        shell = card(self.top)
        shell.pack(fill="both", expand=True, padx=px(16), pady=px(16))
        text = tk.Text(shell, bg=CARD, fg=TEXT, wrap="word", relief="flat", padx=px(22), pady=px(18), bd=0,
                       font=(FONT, 10), highlightthickness=0, spacing1=px(3), spacing3=px(3),
                       selectbackground=ACCENT_BG, insertwidth=0, cursor="arrow")
        bar = ThinScrollbar(shell, text.yview)
        text.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y", padx=(0, px(8)), pady=px(14))
        text.pack(side="left", fill="both", expand=True, padx=(px(2), 0), pady=px(2))
        text.tag_configure("h1", font=(FONT_SEMI, 18), foreground=TEXT, spacing1=px(4), spacing3=px(2))
        text.tag_configure("sub", foreground=MUTED, spacing3=px(8))
        text.tag_configure("h2", font=(FONT_SEMI, 12), foreground=ACCENT_SOFT, spacing1=px(16), spacing3=px(4))
        text.tag_configure("h3", font=(FONT_SEMI, 11), foreground=TEXT, spacing1=px(12), spacing3=px(4))
        text.tag_configure("bullet", lmargin1=px(8), lmargin2=px(24), foreground=mix(TEXT, MUTED, 0.2))
        text.tag_configure("pic", lmargin1=px(4), spacing1=px(4), spacing3=px(6))
        self.images = []
        if lines is None:
            try:
                with open(resource_path(GUIDE_FILE), "r", encoding="utf-8") as fh:
                    lines = fh.read().splitlines()
            except Exception:
                lines = ["The guide file is missing. See HOW TO USE.txt next to the app."]
        after_h1 = False
        for line in lines:
            s = line.rstrip()
            if s.startswith("==="):
                continue
            pic = re.match(r"^\[Skill layout picture: (\w+)", s)
            if pic:  # the routine's skill layout picture (the .txt file only has this line)
                try:
                    im = Image.open(resource_path("assets", "layouts", pic.group(1) + ".png")).convert("RGB")
                    w = min(px(600), im.width)
                    im = im.resize((w, int(im.height * w / im.width)), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(im)
                    self.images.append(photo)
                    text.image_create("end", image=photo)
                    text.insert("end", "\n", "pic")
                except Exception:
                    pass
                continue
            if s.startswith("### "):
                text.insert("end", s[4:] + "\n", "h3")
            elif s.startswith("## "):
                text.insert("end", s[3:] + "\n", "h2")
            elif s.startswith("# "):
                text.insert("end", s[2:] + "\n", "h1")
                after_h1 = True
                continue
            elif re.match(r"^\s*(-|\*|\d+\.)\s", s):
                body = s.strip()
                if body.startswith(("- ", "* ")):
                    body = "•  " + body[2:]
                text.insert("end", body + "\n", "bullet")
            else:
                text.insert("end", s + "\n", "sub" if after_h1 else ())
            after_h1 = False
        text.configure(state="disabled")
        fit_geometry(self.top, px(720), px(760))
        if not app.headless:
            present(self.top)


_PUBLIC_SCRUB = (
    (re.compile(r"https?://\S+"), "[link]"),
    (re.compile(r"[\w-]{20,}\.[\w-]{5,}\.[\w-]{20,}"), "[token]"),  # Discord bot tokens
    (re.compile(r"\b\d{15,21}\b"), "[id]"),  # Discord channel / user ids
)


def scrub_for_public(text):
    """Feedback becomes a public GitHub issue: take out the home folder / Windows user name, links, tokens and ids."""
    home = os.path.expanduser("~")
    if len(home) > 3:
        text = re.sub(re.escape(home), "~", text, flags=re.IGNORECASE)
    user = os.environ.get("USERNAME", "")
    if len(user) >= 3:
        text = re.sub(r"(?i)(?<![\w])%s(?![\w])" % re.escape(user), "[user]", text)
    for pat, repl in _PUBLIC_SCRUB:
        text = pat.sub(repl, text)
    return text


def feedback_issue_url(message, contact, info, log_lines=(), log_title="Activity log", limit=FEEDBACK_URL_MAX):
    """Link to a new, filled-in issue on the macro's GitHub repo. log_lines are plain text lines (scrubbed here); when
    they don't all fit, the newest are kept. Returns (url, how many log lines went in). The size that counts is the
    link encoded again (as the sign-in page carries it), so testers who aren't signed in keep what they wrote."""
    message = message.strip()
    contact = contact.strip()
    base = "https://github.com/%s/issues/new?" % FEEDBACK_REPO
    lines = [scrub_for_public(l) for l in log_lines]

    def make(msg, n):
        first = msg.splitlines()[0].strip() if msg else ""
        title = "Feedback: " + (first[:60] + "..." if len(first) > 60 else first)
        body = msg + "\n\n" + ("**Contact:** %s\n" % contact if contact else "") + "**App:** " + info
        if n:
            body += ("\n\n<details><summary>%s (last %d lines)</summary>\n\n```\n%s\n```\n</details>"
                     % (log_title, n, "\n".join(lines[-n:])))
        return base + urllib.parse.urlencode({"title": title, "body": body}, quote_via=urllib.parse.quote)

    def fits(url):
        return len(urllib.parse.quote(url, safe="")) <= limit

    while not fits(make(message, 0)) and len(message) > 40:  # a very long message: keep its start
        message = message[:int(len(message) * 0.85)].rstrip() + " ..."
    lo, hi = 0, len(lines)  # the most log lines that still fit (the link only grows with more lines)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if fits(make(message, mid)):
            lo = mid
        else:
            hi = mid - 1
    return make(message, lo), lo


class FeedbackWindow:
    """A bug or an idea: opens a filled-in GitHub issue in the browser (GitHub emails the repo owner). The app itself
    sends nothing - the tester sees everything on GitHub and presses Submit there."""

    def __init__(self, app):
        self.app = app
        self.top = tk.Toplevel(app.root)
        self.top.withdraw()
        self.top.title("%s - Send feedback" % APP_NAME)
        self.top.configure(bg=BG)
        shell = tk.Frame(self.top, bg=BG)
        shell.pack(fill="both", expand=True, padx=px(16), pady=px(16))
        label(shell, "Send feedback", 14, TEXT, True).pack(anchor="w")
        label(shell, "A bug, an idea, anything. It opens on GitHub with this filled in - press Submit new issue there "
                     "(needs a free GitHub account). Feedback on GitHub is public, so don't write passwords or "
                     "personal info.", 9, MUTED, wraplength=px(540), justify="left").pack(anchor="w", pady=(px(2), px(12)))
        c = card(shell)
        c.pack(fill="both", expand=True)
        inner = tk.Frame(c, bg=CARD)
        inner.pack(fill="both", expand=True, padx=px(16), pady=px(14))
        label(inner, "WHAT HAPPENED, OR YOUR IDEA", 7, ACCENT, True).pack(anchor="w")
        self.text = tk.Text(inner, height=7, wrap="word", bg=FIELD_BG, fg=TEXT, insertbackground=TEXT, relief="flat",
                            font=(FONT, 10), highlightthickness=1, highlightbackground=EDGE_HI, highlightcolor=ACCENT,
                            padx=px(10), pady=px(8), bd=0, selectbackground=ACCENT_BG, selectforeground=TEXT,
                            insertwidth=1, undo=True)
        self.text.pack(fill="both", expand=True, pady=(px(6), px(12)))
        label(inner, "YOUR DISCORD OR ROBLOX NAME (OPTIONAL, SO YOU CAN GET A REPLY)", 7, DIM, True).pack(anchor="w")
        self.contact = entry(inner, 36)
        self.contact.pack(fill="x", pady=(px(6), px(12)), ipady=px(4))
        row = tk.Frame(inner, bg=CARD)
        row.pack(fill="x")
        self.attach = tk.BooleanVar(value=False)
        Toggle(row, self.attach).pack(side="left")
        label(row, "Attach my activity log", 10, TEXT).pack(side="left", padx=(px(10), 0))
        label(inner, "Helps find bugs. Your Windows name, links and Discord ids are taken out first.", 8, DIM,
              wraplength=px(520), justify="left").pack(anchor="w", pady=(px(4), 0))
        label(inner, "Also added: " + self.info(), 8, DIM).pack(anchor="w", pady=(px(8), 0))
        foot = tk.Frame(shell, bg=BG)
        foot.pack(fill="x", pady=(px(12), 0))
        small = dict(padx=px(16), pady=px(8), font=(FONT_SEMI, 9), radius=px(9))
        Btn(foot, "Open on GitHub", self.send, "primary", **small).pack(side="right")
        Btn(foot, "Cancel", self.top.destroy, "ghost", **small).pack(side="right", padx=(0, px(8)))
        self.note = label(foot, "", 9, MUTED)
        self.note.pack(side="left")
        fit_geometry(self.top, px(620), px(580))
        if not app.headless:
            present(self.top)
            self.text.focus_set()

    def info(self):
        cfg = self.app.cfg
        routine = cfg["routine"]
        if routine == "Universal" and cfg["timings"]["Universal"].get("rage"):
            routine += " (Rage preset)"
        return "%s %s, routine %s" % (APP_NAME, VERSION, routine)

    def log_lines(self):
        """This session's log; when it has barely started, the previous session (the one that went wrong) first."""
        lines = ["%s  %s" % (ts, text) for ts, text in self.app.log_lines]
        if len(lines) <= 4:
            try:
                with open(os.path.join(DATA_DIR, "previous_session_log.txt"), encoding="utf-8", errors="replace") as fh:
                    prev = [l.rstrip("\n") for l in fh if l.strip()]
            except OSError:
                prev = []
            if prev:
                lines = ["--- previous session ---"] + prev[-400:] + ["--- this session ---"] + lines
        return lines

    def send(self):
        msg = self.text.get("1.0", "end").strip()
        if not msg:
            self.note.configure(text="Write what happened or your idea first", fg=WARN)
            return
        lines = self.log_lines() if self.attach.get() else []
        url, n = feedback_issue_url(msg, self.contact.get(), self.info(), lines)
        try:
            opened = webbrowser.open(url)
        except Exception:
            opened = False
        if not opened:
            self.top.clipboard_clear()
            self.top.clipboard_append(url)
            self.note.configure(text="Couldn't open your browser - the link is copied, paste it into one", fg=WARN)
            return
        self.app.add_log("Feedback opened on GitHub - press Submit new issue there%s"
                         % (" (log: last %d lines)" % n if lines and n < len(lines) else ""))
        self.top.destroy()


class MiniBar:
    """Small always-on-top rounded status strip while the macro runs."""

    def __init__(self, app):
        self.app = app
        self.pill = None

    def show(self):
        if self.pill is not None:
            return
        mon = pick_monitor(self.app.cfg)
        w, h = px(480), px(32)
        self.pill = FloatingPill(self.app.root, w, h, alpha=0.94)
        c = self.pill.canvas
        self.dot = c.create_text(px(18), h // 2, text="●", fill=ACCENT, font=(FONT, 9))
        self.text = c.create_text(px(32), h // 2, text="", fill=TEXT, font=(FONT_SEMI, 9), anchor="w")
        self.keys = c.create_text(w - px(16), h // 2, text="", fill=DIM, font=(FONT, 8), anchor="e")
        self.pill.place(mon["left"] + (mon["width"] - w) // 2, mon["top"] + px(6))
        c.bind("<Button-1>", lambda e: self.app.restore_window())
        self.update()

    def hide(self):
        if self.pill is not None:
            self.pill.destroy()
            self.pill = None

    def update(self):
        if self.pill is None:
            return
        a = self.app
        if a.scanner.running() and not a.engine.running():
            c = self.pill.canvas
            c.itemconfigure(self.dot, fill=WARN)
            c.itemconfigure(self.text, text=getattr(a, "scan_progress", "") or "Scanning your build...")
            k = a.cfg["keys"]
            c.itemconfigure(self.keys, text="%s or move the mouse = stop" % key_display(k.get("scan_stop", "esc")))
            return
        status = a.engine.state
        look = STATUS_LOOK.get(status, STATUS_LOOK["idle"])
        c = self.pill.canvas
        c.itemconfigure(self.dot, fill=ACCENT if status == "running" else look[2])
        c.itemconfigure(self.text, text="%s   ·   %s   ·   %d done" % (look[0], a.now_title, a.engine.session["retries"]))
        k = a.cfg["keys"]
        c.itemconfigure(self.keys, text="%s pause   %s stop" % (key_display(k["pause"]), key_display(k["stop"])))


ICON_FONT = "Segoe MDL2 Assets"
NAV_ICONS = {"Dashboard": "\ue80f", "Runs": "\ue81c", "Graph": "\ue9d2", "Loot": "\ue7b8", "Stats": "\ueb05",
             "Appearance": "\ue790", "Settings": "\ue713", "Guide": "\ue897", "Feedback": "\ue939",
             "Discord": "\ue8f2"}
NAV_TEXT = {"Graph": "Analytics", "Stats": "All-time stats", "Build": "Your build"}
NAV_ICONS["Build"] = "\ue8fd"
NAV_ICONS["Optimiser"] = "\ue735"
NAV_TEXT["Optimiser"] = "Build optimiser"
CREDIT = "Made by Aarav Narula"
# What each routine needs (shown on the 'Your build' page). (title, text, important)
_AVOID = "Adaptation, Tatsujin and Wings of Freedom (perks), Flashsteps (memory)"
_OPTIONAL = "Any legendary memory, or memories that add damage"
_BICORN = ("Turn on Settings > Timings > Shared > No Feathered Bicorn - the macro looks up before the dash so "
           "it still reaches the titans")
BUILDS = {
    "Blood Awakening": {"layout": "blood", "rows": [
        ("Family", "Any - Shiki for luck, Fritz for extra gems", False),
        ("Perks", "Warchief or Stormwrath, Immortal, Founder's Blessing or Avatar of Ymir, Munition Masters", False),
        ("Artifacts", "Colossal Scars and Cloak, both with Shifter Dmg%", False),
        ("Memories", "Blood Awakening (required)", True),
        ("Optional", _OPTIONAL, False),
        ("No Feathered Bicorn?", _BICORN, False),
        ("Avoid", _AVOID, False)]},
    "Shiki": {"layout": "shiki", "rows": [
        ("Family", "Shiki", False),
        ("Skill tree", "Right - right - left", False),
        ("Perks", "Kengo or Godforged, Immortal, Founder's Blessing or Avatar of Ymir, Munition Masters", False),
        ("You need", "Godforged or Avatar of Ymir", True),
        ("Artifacts", "Colossal Scars and Cloak, both with TS Dmg%", False),
        ("Memories", "Apotheosis and Afterimages (both required)", True),
        ("Optional", _OPTIONAL, False),
        ("No Feathered Bicorn?", _BICORN, False),
        ("Avoid", _AVOID, False)]},
    "Universal": {"layout": "universal", "rows": [
        ("Family", "Fritz, or Reiss, or any other", False),
        ("Skill tree", "Right - right - left. Don't unlock the skill tree for the Fritz family.", False),
        ("Perks", "Kengo or Godforged, Immortal, Founder's Blessing or Avatar of Ymir, Munition Masters", False),
        ("You need", "Godforged or Avatar of Ymir", True),
        ("Artifacts", "Colossal Scars and Cloak, both with TS Dmg%", False),
        ("Memories", "Apotheosis and Afterimages (both required)", True),
        ("Optional", _OPTIONAL, False),
        ("No Feathered Bicorn?", _BICORN, False),
        ("Avoid", _AVOID, False)]},
    "Universal (Rage)": {"layout": "universal_rage", "rows": [
        ("Preset", "Settings > Timings > Universal > Rage preset (Normal preset switches back)", True),
        ("Key 2", "Order: Rage instead of Order: Advance", True),
        ("Family", "Fritz, or Reiss, or any other", False),
        ("Skill tree", "Right - right - left. Don't unlock the skill tree for the Fritz family.", False),
        ("Perks", "Kengo or Godforged, Immortal, Founder's Blessing, Munition Masters - Avatar of Ymir not needed", False),
        ("Artifacts", "Colossal Scars and Cloak, both with TS Dmg%", False),
        ("Memories", "Apotheosis (required)", True),
        ("Optional", "Afterimages, any legendary memory, or memories that add damage", False),
        ("No Feathered Bicorn?", _BICORN, False),
        ("Avoid", _AVOID, False)]},
    "Female Raid": {"layout": "female", "rows": [
        ("Family", "Fritz", False),
        ("Skill tree", "Right - right - left; capstone - capstone - no capstone", False),
        ("Perks (all required)", "Stormwrath, Avatar of Ymir, 15th Commander, Immortal, Font of Inspiration", True),
        ("Artifacts", "Colossal Scars and Scorched Cloak, both with Shifter Dmg%", False),
        ("Memories (all required)", "Blood Awakening, Divine Decree, Sparks of Black, Shatterpoint, Elementalist or Tactician", True),
        ("Avoid", "Adaptation (the failsafe needs it off), Tatsujin, Wings of Freedom (perks), Flashsteps (memory)", False),
        ("Before the first raid", "Pick the chest spots in Settings > Timings > Female Raid", True)]},
}
APP_TOUR = """# How to use the app
A quick tour: where everything is, how to read the Guide, and what we recommend.

## The window
- Sidebar (left): Build optimiser, Dashboard, Your build, Runs, Analytics, Loot and All-time stats. At the bottom: Appearance (theme and colours), Settings, Guide and Feedback (a bug or an idea - opens a filled-in GitHub issue).
- Top bar: the page you're on, this tour, the routine picker (Blood Awakening, Shiki, Universal, Female Raid) and the status badge (Idle, Waiting, Running, Paused).

## Build optimiser
- Pick Shifter, Thunder Spear or ODM at the top. It shows the best build you can equip, slot by slot (Body, Offense, Defense, Support and your family's extra slots), your memories, why each perk was picked, and Get next: the 3 upgrades that would make the build strongest, with how much (%) and where they come from.
- Before you scan it shows the best possible build - every perk at +10.
- Scan my perks: in Roblox open Equipment > Perks and click your Body slot, then press it. The macro clicks each perk in every tab and reads its name and level (it never clicks Equip or Enhance). Esc or moving your mouse stops it (F7 too). The SCAN row filters rarities - Common, Rare and Epic are skipped unless you turn them on. How to use on that page is a step-by-step tutorial.
- Scan memories: open Equipment > Prestige and press it (and again on the memory Storage).
- Family and Capstones: set them so the build only uses slots you really have. Edit list fixes anything the scan got wrong.

## Dashboard
- The big card shows the step the macro is on, a timer for the current run and the step that comes next.
- Start (F8) starts the macro, Pause (F6) pauses and resumes, Stop (F7) stops it. Moving the mouse into the top-left corner of the screen also stops it.
- Under it: runs done, success rate, best and average time, runs per hour. The Activity log at the bottom says everything the macro does.

## Your build
- Shows only what the routine you picked needs: the skill layout picture (which skill goes on which key, before and after you shift), family, skill tree, perks, artifacts and memories. Pick another routine at the top and it changes.

## Runs, Analytics, Loot, All-time stats
- Runs: every run this session with its time, result and loot, and how long each step of the last run took.
- Analytics: the last 24 hours - runs per hour, average time, loot, your recent run times and the average time of each step. Save picture and Send to Discord share it.
- Loot: what this session dropped. All-time stats: everything since you last reset the stats.

## Settings
- Keybinds: the keys the macro presses - make them match your game. The Start / Pause / Stop hotkeys are here too.
- Timings: every wait and spam time, one page per routine. "Load speed preset" makes it faster, "Load defaults" puts it back. The Speed finder (Blood Awakening) finds shorter dash and strafe times by itself.
- Pictures: what the macro looks for on the screen. "Test detection now" shows what it can see. If something isn't seen, press Capture (or End screen, for results and loot) and drag a box around it.
- Failsafe: what happens when a mission gets stuck. Discord: messages, the stats graph and bot commands. Reconnect: rejoins the game after a disconnect. App: your screen, session limits (stop after X runs or hours) and loot tracking.
- Press Save at the bottom after changing anything.

## The Guide
- Guide (bottom of the sidebar) is the full manual, in sections: Quick start, The routines, Before you start, Builds and skill layouts, Going fast, Running it for hours, Stats graph, Loot, Discord, Auto-reconnect, If something doesn't work.
- Stuck? Read "If something doesn't work" first - most problems are a picture the macro can't see, fixed in Settings > Pictures.

## Recommendations
- Set up your build first (Your build page) and check your keys in Settings > Keybinds.
- Load the speed preset (Settings > Timings > your routine) and, for Blood Awakening, turn on the Speed finder.
- Leave the mouse and keyboard alone while it runs. Windowed and fullscreen both work - don't resize the window during a session.
- For long sessions lower the Roblox graphics and set a session limit (Settings > App).
- Watch the first 2-3 runs: the log shows the start icon and retry button being found and your shift being learned.
"""
OPT_TUTORIAL = """# Build optimiser - how to use it
It finds the best build you can equip from the perks and memories you own, and the upgrades that would make it stronger.

## 1. Pick what you play
- Shifter, Thunder Spear or ODM at the top of the page.
- Before you scan, the page shows the best possible build (every perk at +10) - something to aim for.

## 2. Your family and capstones
- Family: pick yours if it's in the list - some families give extra perk slots (Ackerman, Yeager, Reiss, Fritz, Helos, Shiki).
- Capstones: turn on the ones you've unlocked in your skill tree. Divine perks only go in an Offense, Defense or Support slot with that capstone (the Body slot takes any perk).

## 3. Scan your perks
1. In Roblox open Equipment > Perks.
2. Click your Body slot - your perk list opens with a round tab for each category (Body, Offense, Defense, Support).
3. In Colossal Macro press Scan my perks. It switches to Roblox by itself.
4. Let go of the mouse. The macro clicks each perk tile, reads its name and level from the panel on the right, scrolls down and goes through every tab. It only clicks perk tiles and the tabs - never Equip or Enhance.
5. To stop it: press Esc or just move your mouse (F7 and Stop scan work too). The bar at the top of the screen shows how far it is.
[Skill layout picture: optimiser_perks]
- Filter (the SCAN row): Common, Rare and Epic perks are skipped unless you turn them on - it's quicker, and they're rarely in a best build. Once it has read a few tiles of a rarity it knows their border colour and skips the rest without clicking; anything it isn't sure about is read anyway.
- Only one category read? You opened a slot that takes one category. Open the Body slot (it has every tab), or scan each tab in turn - the scans add up.

## 4. Scan your memories
1. Open Equipment > Prestige - your 5 memories show there.
2. Press Scan memories. Open the memory Storage and press it again to add the stored ones.

## 5. Read the result
- Each tile is a slot: the perk to put there, its rarity and level, and what it gives you.
- Memories: the 5 to equip (required ones are marked).
- Why this build: why each perk beat the next best one you own.
- Get next: the 3 upgrades that make the build strongest - the % is how much stronger, and it says where each comes from (drops, divine fragments, prestige scrolls, a capstone, or levelling a perk you already have).

## If something looks wrong
- Edit list: fix a level, add a perk the scan missed, remove one you no longer have.
- "The tiles here aren't perks": the Perks screen wasn't open - open Equipment > Perks and your Body slot, then scan again.
- The Activity log on the Dashboard says what was read.
"""
PAGE_SUBTITLES = {"Build": "What you need for the routine you picked",
                  "Optimiser": "The best build from your perks and memories - and what to get next",
                  "Runs": "Every run this session and where the time went",
                  "Graph": "The last 24 hours of the routine you picked",
                  "Loot": "What this session dropped", "Stats": "Everything since the stats were last reset",
                  "Appearance": "Theme and accent colour"}


class NavItem(tk.Canvas):
    """A sidebar entry: icon + label on a rounded highlight, accent bar when selected."""

    def __init__(self, parent, key, command, width):
        self.w, self.h = width, px(38)
        super().__init__(parent, width=self.w, height=self.h, bg=parent.cget("bg"), highlightthickness=0, bd=0,
                         cursor="hand2")
        self.key, self.command = key, command
        self.selected = self.hover = False
        self.bind("<Button-1>", lambda e: self.command())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.draw()

    def _set_hover(self, on):
        self.hover = on
        self.draw()

    def set_selected(self, on):
        self.selected = on
        self.draw()

    def draw(self):
        self.delete("all")
        imgs = []
        fill = ACCENT_BG if self.selected else CARD2 if self.hover else None
        if fill:
            imgs.append(rounded_image(self.w, self.h, px(9), fill))
            self.create_image(0, 0, image=imgs[-1], anchor="nw")
        if self.selected:
            imgs.append(rounded_image(px(3), px(16), px(2), ACCENT))
            self.create_image(px(5), (self.h - px(16)) // 2, image=imgs[-1], anchor="nw")
        icol = ACCENT if self.selected else TEXT if self.hover else MUTED
        self.create_text(px(26), self.h // 2, text=NAV_ICONS.get(self.key, ""), font=(ICON_FONT, 12), fill=icol)
        self.create_text(px(48), self.h // 2, text=NAV_TEXT.get(self.key, self.key), anchor="w",
                         font=(FONT_SEMI if self.selected else FONT, 10), fill=TEXT if self.selected or self.hover else MUTED)
        self.images = imgs


_APP_ICONS = {}


def app_icon(accent, size):
    """The app icon (rounded tile, white C ring with steam) in the accent colour, as a PIL image."""
    key = (accent, size)
    img = _APP_ICONS.get(key)
    if img is None:
        S = 512
        top, bottom = np.array(_rgb(mix(accent, "#ffffff", 0.18))), np.array(_rgb(mix(accent, "#000000", 0.38)))
        t = np.linspace(0.0, 1.0, S)[:, None, None]
        grad = np.repeat((top * (1 - t) + bottom * t).astype(np.uint8), S, axis=1)
        mask = Image.new("L", (S, S), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=115, fill=255)
        icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        icon.paste(Image.fromarray(grad, "RGB"), (0, 0), mask)
        glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse((125, 125, 387, 387), fill=(255, 255, 255, 70))
        icon = Image.alpha_composite(icon, glow.filter(ImageFilter.GaussianBlur(30)))
        ring = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        dr = ImageDraw.Draw(ring)
        dr.arc((100, 100, 412, 412), start=40, end=320, fill=(255, 255, 255, 255), width=75)
        for cx, cy, r in ((380, 210, 23), (420, 175, 17), (450, 150, 12)):
            dr.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 235))
        img = Image.alpha_composite(icon, ring).resize((size, size), Image.LANCZOS)
        _APP_ICONS[key] = img
    return img


def apply_theme(name, accent=""):
    """Set every colour of the app from a theme + accent. Windows built after this use the new colours."""
    t = THEMES.get(name) or THEMES["Midnight"]
    acc = accent if isinstance(accent, str) and HEX_COLOR.match(accent or "") else t["accent"]
    light = name == "Light"
    UI["light"] = light
    g = globals()
    g.update(BG=t["bg"], SIDE=t["side"], CARD=t["card"], CARD2=t["card2"], HOVER=t["hover"], EDGE=t["edge"],
             EDGE_HI=t["edge_hi"], TEXT=t["text"], MUTED=t["muted"], DIM=t["dim"], FIELD_BG=t["field"])
    r, gg, b = _rgb(acc)
    lum = (0.2126 * r + 0.7152 * gg + 0.0722 * b) / 255.0
    g.update(ACCENT=acc, ACCENT_HOVER=mix(acc, "#ffffff", 0.12), ACCENT_DARK="#0b0d12" if lum > 0.5 else "#ffffff",
             ACCENT_BG=mix(t["card"], acc, 0.14 if light else 0.18), ACCENT_SOFT=mix(acc, t["text"], 0.3),
             SEG_DONE=mix(t["card2"], acc, 0.45))
    good, warn, bad, wait = (("#15803d", "#b45309", "#dc2626", "#2563eb") if light
                             else ("#3ccf80", "#f2b544", "#f06262", "#8fb3ff"))
    g.update(GOOD=good, WARN=warn, BAD=bad)
    g["STATUS_LOOK"] = {
        "idle": ("Idle", t["card2"], t["muted"]),
        "waiting": ("Waiting", mix(t["card"], wait, 0.16), wait),
        "running": ("Running", g["ACCENT_BG"], acc if light else g["ACCENT_SOFT"]),
        "retrying": ("Retrying", mix(t["card"], good, 0.16), good),
        "paused": ("Paused", mix(t["card"], warn, 0.16), warn),
        "rescue": ("Failsafe", mix(t["card"], bad, 0.16), bad),
    }
    Btn.STYLES = {
        "primary": ((mix(acc, "#ffffff", 0.06), mix(acc, "#000000", 0.06)), (g["ACCENT_HOVER"], acc),
                    mix(acc, "#000000", 0.14), g["ACCENT_DARK"]),
        "normal": (t["card2"], t["hover"], mix(t["card2"], t["bg"], 0.5), t["text"]),
        "ghost": (None, t["card2"], t["hover"], t["muted"]),
        "danger": (mix(t["card"], bad, 0.12), mix(t["card"], bad, 0.2), mix(t["card"], bad, 0.08), bad),
    }
    RoundCard.__init__.__defaults__ = (t["card"], (t["edge_hi"], t["edge"]), None)
    label.__defaults__ = (10, t["text"], False, None)
    Segmented.__init__.__defaults__ = (None, None, False, True, t["field"])
    ScrollFrame.__init__.__defaults__ = (t["bg"],)
    SettingsWindow.note.__defaults__ = (t["muted"],)
    # charts follow the theme
    g.update(CH_BG=_rgb(t["bg"]), CH_CARD=_rgb(t["card"]), CH_GRID=_rgb(mix(t["card"], t["text"], 0.1)),
             CH_TEXT=_rgb(t["text"]), CH_MUTED=_rgb(t["muted"]), CH_DIM=_rgb(t["dim"]))
    series = ({"completed": "#0ca30c", "unknown": "#8a93a4", "failed": "#d03b3b", "main": "#2a78d6",
               "fragments": "#eb6834", "serums": "#1baf7a", "time": "#6250d6"} if light else
              {"completed": "#0ca30c", "unknown": "#6b7180", "failed": "#d03b3b", "main": "#3987e5",
               "fragments": "#d95926", "serums": "#199e70", "time": "#9085e9"})
    for k, col in series.items():
        CH_SERIES[k] = (CH_SERIES[k][0], _rgb(col))
    bar_chart.__defaults__ = (g["CH_CARD"], True)


class ScanProblem(Exception):
    pass


class BuildScanner:
    """Reads your perks and memories off the game's menus - nothing else is touched. Perks: it clicks every tile in
    the Perks menu (each category tab in turn, scrolling down) and reads the name and level in the detail panel with
    Windows' text recognition. Memories: their names are read straight off the Prestige page / memory storage.
    Stop it any time with the Stop key or by moving the mouse into the top-left corner."""
    PANEL = (0.55, 0.10, 1.0, 0.86)  # the perk detail panel: name, level and stat lines (not the buttons below)
    MAX_PAGES = 200                  # per tab

    def __init__(self, cfg, out):
        self.cfg, self.out = cfg, out
        self.thread = None
        self.quit = False
        self.region = None
        self.expect_pos = None  # where the scan last put the mouse (a different spot = you moved it: stop)
        self.include = set(bo.RARITIES)
        self.samples = []       # (border colour, rarity) of tiles read so far - to skip filtered rarities
        self.reads = self.named = 0

    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, what):
        if self.running():
            return False
        self.quit = False
        self.thread = threading.Thread(target=self._run, args=(what,), name="scan", daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.quit = True

    # ---- helpers ----
    def _check(self):
        k = self.cfg["keys"]
        if self.quit or key_is_down(k["stop"]) or key_is_down(k.get("scan_stop", "esc")):
            raise StopMacro()
        pos = cursor_pos()
        if pos == (0, 0):
            raise StopMacro()
        if self.expect_pos is not None and (abs(pos[0] - self.expect_pos[0]) > 25 or
                                            abs(pos[1] - self.expect_pos[1]) > 25):
            self.moved_by_user = True
            raise StopMacro()  # you moved the mouse: stop straight away

    def _say(self, text):
        self.out.put(("opt_progress", text))

    def _sleep(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self._check()
            time.sleep(min(0.05, max(0.0, end - time.time())))

    def _shot(self, g):
        return cv2.cvtColor(g.grab(), cv2.COLOR_BGRA2BGR)

    def _to_screen(self, x, y):
        return self.region["left"] + int(x), self.region["top"] + int(y)

    def _put_mouse(self, x, y):
        sx, sy = self._to_screen(x, y)
        user32.SetCursorPos(sx, sy)
        time.sleep(0.03)
        mouse_move_rel(0, 1)  # Roblox only notices the cursor after a real move
        time.sleep(0.03)
        self.expect_pos = cursor_pos()

    def _click(self, x, y):
        self._check()
        self._put_mouse(x, y)
        mouse_click()

    def _wheel_at(self, x, y, notches):
        self._check()
        self._put_mouse(x, y)
        step = 1 if notches > 0 else -1
        for _ in range(abs(int(notches))):
            mouse_wheel(step)
            time.sleep(0.02)

    def _panel(self, shot):
        h, w = shot.shape[:2]
        x0, y0, x1, y1 = self.PANEL
        return shot[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]

    def _read_panel(self, g):
        return bo.read_perk_panel_img(self._panel(self._shot(g)))

    def _settled(self, g, area, wait=0.35):
        """A screenshot once the scrolling has stopped moving (smooth scrolling)."""
        self._sleep(wait)
        x0, y0, x1, y1 = area
        prev = self._shot(g)
        for _ in range(6):
            self._sleep(0.1)
            cur = self._shot(g)
            if float(np.mean(cv2.absdiff(prev[y0:y1, x0:x1], cur[y0:y1, x0:x1]))) < 1.0:
                return cur
            prev = cur
        return prev

    @staticmethod
    def _shift_errors(before, after, lo, hi):
        """How well `after` matches `before` moved up by s px, for s in [lo, hi] (every px; every 2nd column):
        {s: mean difference}. The right s has a clear dip."""
        bg = before[:, ::2].astype(np.int16)  # in colour: rarity colours tell rows apart better than grey
        ag = after[:, ::2].astype(np.int16)
        h = bg.shape[0]
        out = {}
        for s_ in range(max(1, int(lo)), min(int(h * 0.88), int(hi)) + 1):
            out[s_] = float(np.mean(np.abs(bg[s_:] - ag[:h - s_])))
        return out

    @classmethod
    def _measure_scroll(cls, before, after, pitch, expect=None):
        """How far the list moved up (px), or None when it can't be told for sure. The list repeats every row, so a
        picture match can also fit one row off: unknown moves (expect=None) only count when the best fit is clearly
        better than the fits a row away; known ones are only looked for within a third of a row of the expected."""
        if expect is None:
            errs = cls._shift_errors(before, after, 2, before.shape[0])
            if not errs:
                return None
            s = min(errs, key=errs.get)
            rivals = [e for k, e in errs.items() if abs(k - s) > pitch * 0.35]
            if rivals and (errs[s] > 0.5 * min(rivals) or min(rivals) - errs[s] < 0.15):
                return None  # a row away fits (nearly) as well: can't tell
            return s
        errs = cls._shift_errors(before, after, expect - pitch * 0.33, expect + pitch * 0.33)
        if not errs:
            return None
        s = min(errs, key=errs.get)
        if errs[s] > 0.6 * max(errs.values()):
            return None  # no clear fit near the expected move (the end of the list stopped it short)
        return s

    # ---- the scan ----
    def _run(self, what):
        result = {"what": what, "ok": False, "started": time.time()}
        g = None
        self.expect_pos, self.moved_by_user = None, False
        self.samples, self.reads, self.named, self.skipped = [], 0, 0, 0
        inc = self.cfg["optimiser"].get("scan_rarities")
        self.include = set(inc) if inc else set(bo.RARITIES)
        try:
            if not bo.ocr_available():
                raise ScanProblem("Windows text recognition isn't available on this PC (it needs Windows 10 or 11)")
            if roblox_window() == 0:
                raise ScanProblem("Roblox isn't open")
            self.region = game_region(pick_monitor(self.cfg))
            g = ScreenGrabber(self.region)
            focus_roblox()
            self._sleep(0.6)
            if what == "perks":
                result.update(self._scan_perks(g))
            else:
                result.update(self._scan_memories(g))
            result["ok"] = True
        except StopMacro:
            result["error"] = "Scan stopped (you moved the mouse)" if self.moved_by_user else "Scan stopped"
        except ScanProblem as e:
            result["error"] = str(e)
        except Exception as e:
            result["error"] = "%s: %s" % (type(e).__name__, e)
            self.out.put(("trace", traceback.format_exc()))
        finally:
            if g is not None:
                g.close()
        result["seconds"] = time.time() - result["started"]
        self.out.put(("opt_done", result))

    def _scan_memories(self, g):
        names = bo.read_memories(bo.ocr_lines(self._shot(g), 1.5))
        if not names:
            raise ScanProblem("No memories found on the screen. In Roblox open Equipment > Prestige (your memories "
                              "show there), or the memory Storage, then press Scan memories again.")
        return {"memories": names}

    def _scan_perks(self, g):
        grid = bo.find_perk_grid(self._shot(g))
        if grid is None:
            raise ScanProblem("Couldn't find your perk list. In Roblox open Equipment > Perks and click your Body "
                              "slot so the list shows, then press Scan my perks again.")
        found = {}
        tabs = grid["tabs"] or [None]
        geom, per_notch = None, None
        for ti, tab in enumerate(tabs):
            if tab is not None:
                self._click(*tab)
                self._sleep(0.7)
            geom, per_notch = self._scan_tab(g, found, ti, len(tabs), geom, per_notch)
        return {"perks": found, "all_tabs": len(tabs) > 1, "skipped": self.skipped,
                "rarities": sorted(self.include, key=bo.RARITIES.index)}

    def _read_cell(self, g, x, y, last):
        """Click a tile and read the panel: (name, level) - level None when it couldn't be read."""
        self._check()
        self._click(x, y)
        self._sleep(0.2)
        name, lv = self._read_panel(g)
        if name is not None and (name, lv) == last:  # the panel may not have changed yet
            self._sleep(0.25)
            name, lv = self._read_panel(g)
        if name is not None and lv is None:
            self._sleep(0.2)
            name2, lv2 = self._read_panel(g)
            if name2 == name and lv2 is not None:
                lv = lv2
        return name, lv

    @staticmethod
    def _border(shot, x, y, size):
        """A tile's border colour (top and bottom edge, in Lab) - how its rarity shows before it's clicked."""
        h = int(size / 2)
        x0, y0, x1, y1 = int(x - h), int(y - h), int(x + h), int(y + h)
        m = max(2, int(size * 0.06))
        if x0 - m < 0 or y0 - m < 0 or y1 + m > shot.shape[0] or x1 + m > shot.shape[1]:
            return None
        b = max(3, int(size * 0.14))

        def edge(band):
            px_ = band.reshape(-1, 3)
            v = px_.max(axis=1)
            keep = px_[v >= np.percentile(v, 75)]  # the border is the brightest thing along the edge
            return np.median(keep, axis=0)
        top = edge(shot[y0 - m:y0 + b, x0 + b:x1 - b])
        bot = edge(shot[y1 - b:y1 + m, x0 + b:x1 - b])
        lab = cv2.cvtColor(np.uint8([[top, bot]]), cv2.COLOR_BGR2LAB).astype(float)
        return lab.reshape(-1)

    def _skip(self, vec):
        """Skip this tile without clicking it? Only when its border clearly matches a rarity you filtered out (seen
        at least twice) and clearly doesn't match any rarity you want - never on a guess."""
        if vec is None or self.include >= set(bo.RARITIES) or not self.samples:
            return False
        dist = {}
        for v, r in self.samples:
            d = float(np.linalg.norm(v - vec))
            dist[r] = min(dist.get(r, 1e9), d)
        best = min(dist, key=dist.get)
        if best in self.include or sum(1 for _, r in self.samples if r == best) < 2 or dist[best] > 10:
            return False
        wanted = [d for r, d in dist.items() if r in self.include]
        if not wanted:
            return False  # nothing you want has been seen yet: can't be sure their colours differ
        return all(d >= max(25.0, 2.5 * dist[best]) for d in wanted)

    def _tile(self, g, shot, x, y, size, last, found, where):
        """One tile: skip it (filtered rarity) or click it and read it. Returns the last (name, level) read."""
        vec = self._border(shot, x, y, size)
        if self._skip(vec):
            self.skipped += 1
            return last
        name, lv = self._read_cell(g, x, y, last)
        self.reads += 1
        if name is None:
            if self.reads >= 4 and self.named == 0:
                raise ScanProblem("The tiles here aren't perks. In Roblox open Equipment > Perks and click your Body "
                                  "slot so your perk list shows, then press Scan my perks again.")
            return last
        self.named += 1
        rarity = bo.PERKS[name]["rarity"]
        if vec is not None:
            self.samples.append((vec, rarity))
        lv0 = 0 if lv is None else lv
        if rarity in self.include:
            found[name] = max(found.get(name, -1), lv0)
        self._say("Reading your perks - %s - %d kinds found%s (last: %s +%d)"
                  % (where, len(found), (", %d skipped by your filter" % self.skipped) if self.skipped else "",
                     name, lv0))
        return (name, lv)

    def _scan_tab(self, g, found, ti, ntabs, geom_prev=None, per_notch=None):
        """Read every tile of the shown tab, top to bottom. Scrolling: how far one wheel notch moves the list is
        learned once (at the top, where rows differ); after that each move is checked against the notches turned,
        and when a move can't be told for sure every tile on screen is read again - a row is never skipped.
        Returns (the grid's shape, px per notch) for the next tabs."""
        shot = self._shot(g)
        grid = bo.find_perk_grid(shot) or (bo.find_perk_grid(shot, geom_prev) if geom_prev else None)
        if grid is None:
            return geom_prev, per_notch
        gm = grid["geom"]
        size, xs, pitch = gm["size"], gm["xs"], gm["pitch_y"]
        h = shot.shape[0]
        area = (max(0, int(xs[0] - size * 0.6)), max(0, int(gm["top"])), int(xs[-1] + size * 0.6),
                min(h, int(grid["bottom"] + size * 0.3)))
        cx, cy = (area[0] + area[2]) // 2, (area[1] + area[3]) // 2
        self._wheel_at(cx, cy, 40)  # start at the top of the list
        shot = self._settled(g, area)
        top_grid = bo.find_perk_grid(shot)  # at the top: the list's real start
        if top_grid is not None:
            gm = top_grid["geom"]
        rows_visible = max(1.0, (area[3] - area[1]) / pitch)
        careful = False  # can't tell how far a notch scrolls: one notch at a time, every tile read each time
        notches = 1 if per_notch is None else max(1, int(((rows_visible - 1.3) * pitch) // max(1.0, per_notch)))
        new_below = None  # after a scroll: only cells below this y are new
        last = None
        for page in range(self.MAX_PAGES):
            grid = bo.find_perk_grid(shot, gm)
            if grid is None:
                break
            for (x, y) in grid["cells"]:
                if new_below is not None and y <= new_below:
                    continue
                last = self._tile(g, shot, x, y, gm["size"], last, found,
                                  "tab %d of %d, page %d" % (ti + 1, ntabs, page + 1))
            x0, y0, x1, y1 = area
            self._check()
            self._put_mouse(cx, cy)  # the mouse goes where it will scroll first: a hover look is in both pictures
            self._sleep(0.15)
            before = self._shot(g)[y0:y1, x0:x1].copy()
            max_y = max(c[1] for c in grid["cells"])
            self._wheel_at(cx, cy, -notches)
            shot = self._settled(g, area)
            after = shot[y0:y1, x0:x1]
            if float(np.mean(cv2.absdiff(before, after))) < 1.5:
                # nothing moved: the end of the list. The last move may have been cut short by the end, so read
                # every tile on screen once more (a row hidden by a short move would be here)
                if new_below is not None:
                    g2 = bo.find_perk_grid(shot, gm)
                    for (x, y) in (g2["cells"] if g2 else []):
                        last = self._tile(g, shot, x, y, gm["size"], last, found, "tab %d of %d, end" % (ti + 1, ntabs))
                break
            if careful:  # try to learn the notch again; until then read everything on screen each time
                moved = self._measure_scroll(before, after, pitch)
                if moved is None or moved <= 0:
                    new_below = None
                    continue
                careful, per_notch = False, float(moved)
                new_below = max_y - moved + pitch * 0.5
                notches = max(1, int(((rows_visible - 1.3) * pitch) // per_notch))
                continue
            if per_notch is None:  # learn how far one notch scrolls
                moved = self._measure_scroll(before, after, pitch)
                if moved is None or moved <= 0:
                    careful, new_below = True, None
                    continue
                per_notch = float(moved)
                notches = max(1, int(((rows_visible - 1.3) * pitch) // per_notch))
            else:
                moved = self._measure_scroll(before, after, pitch, notches * per_notch)
                if moved is None:
                    new_below = None  # stopped short (the end) or unclear: read everything on screen again
                    continue
            new_below = max_y - moved + pitch * 0.5
        return gm, per_notch


class App:
    def __init__(self, headless=False):
        self.headless = headless
        if not headless:
            os.makedirs(DATA_DIR, exist_ok=True)
        self.cfg = load_config()
        apply_theme(self.cfg["app"]["theme"], self.cfg["app"]["accent"])
        self.log_lines = []
        self.q = queue.Queue()
        self.discord = Discord(self.cfg, lambda t: self.q.put(("log", t)), lambda cmd: self.q.put(("bot", cmd)),
                               lambda: pick_monitor(self.cfg))
        self.engine = Engine(self.cfg, self.q, self.discord)
        self.scanner = BuildScanner(self.cfg, self.q)
        self.binding = False
        self.settings = None
        self.now_title = "Ready"
        self.current_step = None
        self.breath = 0.0
        self.log_file = None
        self.last_graph_sent = None
        if not headless:
            try:
                if os.path.isfile(LOG_PATH):  # keep the previous session's log (e.g. after a crash)
                    os.replace(LOG_PATH, os.path.join(DATA_DIR, "previous_session_log.txt"))
            except Exception:
                pass
            try:
                self.log_file = open(LOG_PATH, "w", encoding="utf-8")
            except Exception:
                self.log_file = None

        self.root = tk.Tk()
        self.root.withdraw()
        UI["scale"] = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        self.root.title(APP_NAME)
        self.root.configure(bg=BG)
        try:
            self.root.iconbitmap(default=resource_path("assets", "icon.ico"))
        except tk.TclError:
            pass
        self.root.minsize(px(1000), px(640))
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.mini = MiniBar(self)
        self.build()
        self.refresh_stats()
        self.add_log("%s %s ready. Pick a routine, press %s (or Start) in a mission."
                     % (APP_NAME, VERSION, key_display(self.cfg["keys"]["start"])))
        self.add_log("Settings folder: %s" % DATA_DIR)
        if headless:
            return
        self.root.update_idletasks()
        fit_geometry(self.root, max(px(1040), self.root.winfo_reqwidth()), max(px(720), self.root.winfo_reqheight()))
        present(self.root)
        self.discord.restart_bot()
        threading.Thread(target=self.hotkey_loop, name="hotkeys", daemon=True).start()
        self.root.after(50, self.poll)
        self.root.after(1000, self.tick_clock)
        self.root.after(90, self.breathe)
        self.root.after(150, self.timer_tick)
        self.root.after(60000, self.graph_timer)

    # ---- layout ------------------------------------------------------------------------------
    def build(self):
        r = self.root
        self.tabs, self.nav = {}, {}
        side = tk.Frame(r, bg=SIDE, width=px(216))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Frame(r, bg=EDGE, width=1).pack(side="left", fill="y")
        brand = tk.Frame(side, bg=SIDE)
        brand.pack(fill="x", padx=px(18), pady=(px(20), px(22)))
        try:
            self.logo = ImageTk.PhotoImage(app_icon(ACCENT, px(30)))
            tk.Label(brand, image=self.logo, bg=SIDE).pack(side="left", padx=(0, px(10)))
            self.win_icons = [ImageTk.PhotoImage(app_icon(ACCENT, s)) for s in (64, 32, 16)]
            self.root.iconphoto(True, *self.win_icons)  # title bar + taskbar in the accent colour too
        except Exception:
            pass
        names = tk.Frame(brand, bg=SIDE)
        names.pack(side="left")
        label(names, APP_NAME, 11, TEXT, True, bg=SIDE).pack(anchor="w")
        label(names, "v" + VERSION, 8, DIM, bg=SIDE).pack(anchor="w")
        nav_w = px(216) - 2 * px(14)

        def section(text):
            label(side, text, 7, DIM, True, bg=SIDE).pack(anchor="w", padx=px(22), pady=(px(6), px(6)))

        section("MACRO")
        for key in ("Optimiser", "Dashboard", "Build", "Runs", "Graph", "Loot", "Stats"):
            item = NavItem(side, key, lambda k=key: self.show_tab(k), nav_w)
            item.pack(padx=px(14), pady=px(1))
            self.nav[key] = item
        bottom = tk.Frame(side, bg=SIDE)
        bottom.pack(side="bottom", fill="x", pady=(0, px(16)))
        label(bottom, "APP", 7, DIM, True, bg=SIDE).pack(anchor="w", padx=px(22), pady=(0, px(6)))
        for key, cmd in (("Appearance", lambda: self.show_tab("Appearance")), ("Settings", self.open_settings),
                         ("Guide", self.open_guide), ("Feedback", self.open_feedback),
                         ("Discord", self.open_discord)):
            item = NavItem(bottom, key, cmd, nav_w)
            item.pack(padx=px(14), pady=px(1))
            self.nav[key] = item

        main = tk.Frame(r, bg=BG)
        main.pack(side="left", fill="both", expand=True)
        pad = px(28)
        top = tk.Frame(main, bg=BG)
        top.pack(fill="x", padx=pad, pady=(px(22), px(18)))
        titles = tk.Frame(top, bg=BG)
        titles.pack(side="left")
        self.page_lbl = label(titles, "Dashboard", 17, TEXT, True)
        self.page_lbl.pack(anchor="w")
        self.subtitle = label(titles, "", 9, MUTED)
        self.subtitle.pack(anchor="w")
        self.pill = Pill(top)
        self.pill.pack(side="right")
        self.routine_var = tk.StringVar(value=self.cfg["routine"])
        self.routine_seg = Dropdown(top, self.routine_var, ROUTINES, command=self.on_routine)
        self.routine_seg.pack(side="right", padx=(0, px(10)))
        Btn(top, "How to use the app", self.open_tour, "normal", padx=px(14), pady=px(7), font=(FONT_SEMI, 9),
            radius=px(9)).pack(side="right", padx=(0, px(10)))
        label(top, CREDIT, 9, MUTED).pack(side="right", padx=(0, px(12)))
        self.tab_var = tk.StringVar(value="Dashboard")
        self.tab_card = tk.Frame(main, bg=BG)
        self.tab_card.pack(fill="both", expand=True, padx=pad, pady=(0, px(22)))

        # ---- Dashboard ----
        dash = tk.Frame(self.tab_card, bg=BG)
        hero = card(dash)
        hero.pack(fill="x")
        row = tk.Frame(hero, bg=CARD)
        row.pack(fill="x", padx=px(24), pady=(px(20), 0))
        self.eyebrow = label(row, "READY", 8, DIM, True)
        self.eyebrow.pack(side="left")
        self.next_lbl = label(row, "", 8, DIM, True)
        self.next_lbl.pack(side="right")
        trow = tk.Frame(hero, bg=CARD)
        trow.pack(fill="x", padx=px(23), pady=(px(6), 0))
        self.now_lbl = label(trow, "Ready", 22, TEXT, True)
        self.now_lbl.pack(side="left", anchor="s")
        self.timer_lbl = label(trow, "", 28, DIM, True)
        self.timer_lbl.pack(side="right", anchor="s")
        self.detail_lbl = label(hero, "", 10, MUTED)
        self.detail_lbl.pack(anchor="w", padx=px(24), pady=(px(2), 0))
        self.prog = tk.Canvas(hero, height=px(6), bg=CARD, highlightthickness=0, bd=0)
        self.prog.pack(fill="x", padx=px(24), pady=(px(18), px(18)))
        self.prog.bind("<Configure>", lambda e: self.draw_progress())
        tk.Frame(hero, bg=EDGE, height=1).pack(fill="x")
        ctrl = tk.Frame(hero, bg=CARD)
        ctrl.pack(fill="x", padx=px(24), pady=px(16))
        big = (FONT_SEMI, 10)
        self.start_btn = Btn(ctrl, "Start", self.on_start, "primary", padx=px(26), pady=px(9), font=big, radius=px(10))
        self.pause_btn = Btn(ctrl, "Pause", self.on_pause, padx=px(20), pady=px(9), font=big, radius=px(10))
        self.stop_btn = Btn(ctrl, "Stop", self.on_stop, "danger", padx=px(20), pady=px(9), font=big, radius=px(10))
        for b in (self.start_btn, self.pause_btn, self.stop_btn):
            b.pack(side="left", padx=(0, px(8)))
        self.keys_hint = label(ctrl, "", 8, DIM)
        self.keys_hint.pack(side="right")

        metrics = tk.Frame(dash, bg=BG)
        metrics.pack(fill="x", pady=(px(14), 0))
        self.stat_lbls = {}
        for i, (key, name) in enumerate((("retries", "Runs done"), ("rate", "Success"), ("best", "Best time"),
                                         ("avg", "Average"), ("hour", "Per hour"))):
            mc = card(metrics)
            mc.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else px(12), 0))
            metrics.grid_columnconfigure(i, weight=1, uniform="m")
            inner = tk.Frame(mc, bg=CARD)
            inner.pack(fill="both", padx=px(18), pady=px(15))
            label(inner, name.upper(), 7, DIM, True).pack(anchor="w")
            v = label(inner, "-", 18, TEXT, True)
            v.pack(anchor="w", pady=(px(3), 0))
            self.stat_lbls[key] = v

        act = card(dash)
        act.pack(fill="both", expand=True, pady=(px(14), 0))
        ahead = tk.Frame(act, bg=CARD)
        ahead.pack(fill="x", padx=px(22), pady=(px(16), px(4)))
        label(ahead, "Activity", 10, TEXT, True).pack(side="left")
        label(ahead, "live log", 8, DIM).pack(side="right")
        abody = tk.Frame(act, bg=CARD)
        abody.pack(fill="both", expand=True, padx=px(6), pady=(0, px(10)))
        self.log_txt = tk.Text(abody, bg=CARD, fg=MUTED, font=("Consolas", 9), relief="flat", wrap="word", bd=0,
                               height=6, padx=px(16), pady=px(6), highlightthickness=0, state="disabled",
                               selectbackground=ACCENT_BG, spacing1=px(2), spacing3=px(2))
        bar = ThinScrollbar(abody, self.log_txt.yview)
        self.log_txt.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y", padx=(0, px(6)))
        self.log_txt.pack(side="left", fill="both", expand=True)
        self.log_txt.tag_configure("ts", foreground=DIM)
        self.tabs["Dashboard"] = dash

        def page_card(name):
            page = tk.Frame(self.tab_card, bg=BG)
            box = card(page)
            box.pack(fill="both", expand=True)
            self.tabs[name] = page
            return box

        # ---- Runs ----
        runs = page_card("Runs")
        rhead = tk.Frame(runs, bg=CARD)
        rhead.pack(fill="x", padx=px(24), pady=(px(20), px(10)))
        label(rhead, "LAST RUN", 8, DIM, True).pack(side="left")
        self.last_run_lbl = label(rhead, "", 8, DIM, True)
        self.last_run_lbl.pack(side="right")
        self.breakdown = tk.Canvas(runs, bg=CARD, highlightthickness=0, bd=0, height=px(24))
        self.breakdown.pack(fill="x", padx=px(24))
        self.breakdown.bind("<Configure>", lambda e: self.draw_breakdown())
        tk.Frame(runs, bg=EDGE, height=1).pack(fill="x", padx=px(24), pady=px(16))
        label(runs, "THIS SESSION", 8, DIM, True).pack(anchor="w", padx=px(24))
        self.history_frame = tk.Frame(runs, bg=CARD)
        self.history_frame.pack(fill="x", padx=px(24), pady=(px(8), px(18)))

        # ---- Analytics ----
        gpage = tk.Frame(self.tab_card, bg=BG)
        self.tabs["Graph"] = gpage
        krow = tk.Frame(gpage, bg=BG)
        krow.pack(fill="x", pady=(0, px(14)))
        self.kpi_lbls = {}
        for i, (key, name) in enumerate((("done", "Runs"), ("per_hour", "Per hour"), ("avg", "Average time"),
                                         ("best", "Best time"), ("rate", "Success"), ("rescued", "Failsafes"))):
            mc = card(krow)
            mc.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else px(10), 0))
            krow.grid_columnconfigure(i, weight=1, uniform="k")
            inner = tk.Frame(mc, bg=CARD)
            inner.pack(fill="both", padx=px(16), pady=px(12))
            label(inner, name.upper(), 7, DIM, True).pack(anchor="w")
            v = label(inner, "-", 15, TEXT, True)
            v.pack(anchor="w", pady=(px(2), 0))
            self.kpi_lbls[key] = v
        graph = card(gpage)
        graph.pack(fill="both", expand=True)
        gfoot = tk.Frame(graph, bg=CARD)
        gfoot.pack(side="bottom", fill="x", padx=px(22), pady=(0, px(16)))
        self.graph_note = label(gfoot, "Last 24 hours, this routine", 8, DIM)
        self.graph_note.pack(side="left")
        Btn(gfoot, "Send to Discord", lambda: self.send_graph(), "normal", padx=px(14), pady=px(6),
            font=(FONT_SEMI, 9), radius=px(8)).pack(side="right")
        Btn(gfoot, "Save picture", self.save_graph, "ghost", padx=px(14), pady=px(6),
            font=(FONT_SEMI, 9), radius=px(8)).pack(side="right", padx=(0, px(6)))
        self.graph_lbl = tk.Label(graph, bg=CARD, bd=0)
        self.graph_lbl.pack(fill="both", expand=True, padx=px(20), pady=(px(20), px(8)))
        self.graph_lbl.bind("<Configure>", lambda e: self.schedule_graph())
        self.graph_job = None

        # ---- Loot ----
        loot = page_card("Loot")
        lgrid = tk.Frame(loot, bg=CARD)
        lgrid.pack(fill="x", padx=px(24), pady=(px(22), 0))
        self.loot_lbls = {}
        for i, kind in enumerate(("main",) + FRAGMENT_KINDS + SERUM_KINDS):
            cell = tk.Frame(lgrid, bg=CARD)
            cell.grid(row=i // 5, column=i % 5, sticky="w", pady=(0, px(16)))
            lgrid.grid_columnconfigure(i % 5, weight=1)
            v = label(cell, "0", 16, TEXT, True)
            v.pack(anchor="w")
            name = label(cell, "", 7, DIM, True)
            name.pack(anchor="w")
            self.loot_lbls[kind] = (name, v)
        tk.Frame(loot, bg=EDGE, height=1).pack(fill="x", padx=px(24), pady=(px(2), px(16)))
        sgrid = tk.Frame(loot, bg=CARD)
        sgrid.pack(fill="x", padx=px(24), pady=(0, px(20)))
        for i, (key, name) in enumerate((("completed", "Completed"), ("failed", "Failed"), ("session", "Session"),
                                         ("rescues", "Failsafes"))):
            cell = tk.Frame(sgrid, bg=CARD)
            cell.grid(row=0, column=i, sticky="w")
            sgrid.grid_columnconfigure(i, weight=1)
            v = label(cell, "-", 16, TEXT, True)
            v.pack(anchor="w")
            label(cell, name.upper(), 7, DIM, True).pack(anchor="w")
            self.stat_lbls[key] = v

        # ---- All-time stats ----
        tot = page_card("Stats")
        self.total_lbls = {}
        for fam, word in (("missions", "Missions"), ("raids", "Female Raid")):
            box = tk.Frame(tot, bg=CARD)
            box.pack(fill="x", padx=px(24), pady=(px(22), 0))
            label(box, word, 11, TEXT, True).pack(anchor="w")
            grid = tk.Frame(box, bg=CARD)
            grid.pack(fill="x", pady=(px(10), 0))
            for i, (key, name) in enumerate((("runs", "Started"), ("retries", "Done"), ("completed", "Completed"),
                                             ("failed", "Failed"), ("rescues", "Failsafes"))):
                cell = tk.Frame(grid, bg=CARD)
                cell.grid(row=0, column=i, sticky="w")
                grid.grid_columnconfigure(i, weight=1)
                v = label(cell, "0", 14, TEXT, True)
                v.pack(anchor="w")
                label(cell, name.upper(), 7, DIM, True).pack(anchor="w")
                self.total_lbls[(fam, key)] = v
            loot_line = label(box, "", 9, MUTED, wraplength=px(620), justify="left")
            loot_line.pack(anchor="w", pady=(px(10), 0))
            self.total_lbls[(fam, "loot")] = loot_line
            best_line = label(box, "", 9, MUTED, wraplength=px(620), justify="left")
            best_line.pack(anchor="w", pady=(px(2), 0))
            self.total_lbls[(fam, "best")] = best_line

        # ---- Appearance ----
        self.build_appearance()
        self.build_build_page()
        self.build_optimiser_page()

        self.refresh_runs()
        self.show_tab("Dashboard")
        self.apply_routine()
        self.set_status("idle")

    def build_build_page(self):
        page = tk.Frame(self.tab_card, bg=BG)
        self.tabs["Build"] = page
        self.build_box = card(page)
        self.build_box.pack(fill="both", expand=True)
        self.build_inner = None
        self.refresh_build_page()

    def refresh_build_page(self):
        """Show only what the picked routine needs: its skill layout picture and its build."""
        if getattr(self, "build_box", None) is None:
            return
        if self.build_inner is not None:
            self.build_inner.destroy()
        routine = self.cfg["routine"]
        if routine == "Universal" and self.cfg["timings"]["Universal"].get("rage"):
            routine = "Universal (Rage)"
        b = BUILDS[routine]
        inner = tk.Frame(self.build_box, bg=CARD)
        inner.pack(fill="both", expand=True, padx=px(24), pady=px(20))
        self.build_inner = inner
        head = tk.Frame(inner, bg=CARD)
        head.pack(fill="x")
        label(head, "What you need for %s" % routine, 13, TEXT, True).pack(side="left")
        label(head, "pick another routine at the top to see its build", 8, DIM).pack(side="right")
        body = tk.Frame(inner, bg=CARD)
        body.pack(fill="both", expand=True, pady=(px(14), 0))
        left = tk.Frame(body, bg=CARD)
        left.pack(side="left", anchor="n")
        w = px(430)
        try:
            im = Image.open(resource_path("assets", "layouts", b["layout"] + ".png")).convert("RGB")
            im = im.resize((w, int(im.height * w / im.width)), Image.LANCZOS)
            self.build_photo = ImageTk.PhotoImage(im)
            tk.Label(left, image=self.build_photo, bg=CARD, bd=0).pack(anchor="w")
        except Exception:
            pass
        label(left, "Put each skill on the key shown under it - the top row before you shift, the bottom row after. "
                    "Different keys? Change them in Settings > Keybinds.", 8, DIM, wraplength=w,
              justify="left").pack(anchor="w", pady=(px(8), 0))
        right = tk.Frame(body, bg=CARD)
        right.pack(side="left", fill="both", expand=True, padx=(px(22), 0), anchor="n")
        below = ("Optional", "No Feathered Bicorn?", "Avoid", "One-time setup", "Before the first raid")  # under the picture
        firsts = {"right": True, "left": True}
        right_texts = []
        for title, text, strong in b["rows"]:
            side = "left" if title in below else "right"
            col, wrap = (left, w) if side == "left" else (right, px(260))
            label(col, title.upper(), 7, ACCENT if strong else DIM, True).pack(
                anchor="w", pady=(0 if firsts[side] and side == "right" else px(10) if side == "left" else px(7), 0))
            t = label(col, text, 10, TEXT, strong, wraplength=wrap, justify="left")
            t.pack(anchor="w")
            if side == "right":
                right_texts.append(t)
            firsts[side] = False
        # wrap the right column's text to the room it really has (it changes with the window width)
        right.bind("<Configure>", lambda e: [t.configure(wraplength=max(px(120), e.width - px(6))) for t in right_texts])

    def open_tour(self):
        GuideWindow(self, APP_TOUR.splitlines(), "How to use the app")

    # ---- Build optimiser ----
    def build_optimiser_page(self):
        page = tk.Frame(self.tab_card, bg=BG)
        self.tabs["Optimiser"] = page
        o = self.cfg["optimiser"]
        top = card(page)
        top.pack(fill="x")
        row = tk.Frame(top, bg=CARD)
        row.pack(fill="x", padx=px(20), pady=(px(16), px(10)))
        self.opt_ps = tk.StringVar(value=o["playstyle"])
        Segmented(row, self.opt_ps, bo.PLAYSTYLES, command=lambda v: self.on_opt_setting()).pack(side="left")
        small = dict(padx=px(14), pady=px(7), font=(FONT_SEMI, 9), radius=px(9))
        Btn(row, "How to use", self.open_opt_tutorial, "ghost", **small).pack(side="right")
        Btn(row, "Edit list", self.open_opt_edit, "ghost", **small).pack(side="right")
        self.opt_mem_btn = Btn(row, "Scan memories", lambda: self.start_scan("memories"), "normal", **small)
        self.opt_mem_btn.pack(side="right", padx=(0, px(6)))
        self.opt_scan_btn = Btn(row, "Scan my perks", lambda: self.start_scan("perks"), "primary", **small)
        self.opt_scan_btn.pack(side="right", padx=(0, px(6)))
        row2 = tk.Frame(top, bg=CARD)
        row2.pack(fill="x", padx=px(20), pady=(0, px(14)))
        label(row2, "FAMILY", 7, DIM, True).pack(side="left")
        self.opt_family = tk.StringVar(value=o["family"])
        Dropdown(row2, self.opt_family, bo.FAMILIES, command=lambda v: self.on_opt_setting()).pack(
            side="left", padx=(px(8), px(20)))
        label(row2, "CAPSTONES UNLOCKED", 7, DIM, True).pack(side="left")
        self.opt_caps = {}
        for cat in ("Offense", "Defense", "Support"):
            v = tk.BooleanVar(value=cat in o["capstones"])
            self.opt_caps[cat] = v
            Toggle(row2, v, command=self.on_opt_setting).pack(side="left", padx=(px(10), px(5)))
            label(row2, cat, 9, MUTED).pack(side="left")
        row3 = tk.Frame(top, bg=CARD)
        row3.pack(fill="x", padx=px(20), pady=(0, px(14)))
        label(row3, "SCAN", 7, DIM, True).pack(side="left")
        self.opt_rar_pills = {}
        for r in bo.RARITIES:
            pill = Pill(row3, font=(FONT_SEMI, 8))
            pill.configure(cursor="hand2")
            pill.pack(side="left", padx=(px(8) if r == bo.RARITIES[0] else px(5), 0))
            pill.bind("<Button-1>", lambda e, r_=r: self.toggle_scan_rarity(r_))
            self.opt_rar_pills[r] = pill
        self.opt_rar_note = label(row3, "", 8, DIM)
        self.opt_rar_note.pack(side="left", padx=(px(10), 0))
        self.draw_scan_rarities()
        self.opt_status = label(row3, "", 8, DIM)
        self.opt_status.pack(side="right")
        self.opt_scroll = ScrollFrame(page)
        self.opt_scroll.pack(fill="both", expand=True, pady=(px(14), 0))
        self.opt_board = None
        self.refresh_optimiser()
        self.update_scan_buttons()

    @staticmethod
    def autowrap(frame, labels, pad=None):
        """Wrap these labels to the frame's real width (it changes with the window). The margin is bigger than a
        label's own border, so a frame that sizes itself to its labels can only shrink - never grow forever."""
        pad = px(10) if pad is None else pad

        def on(e):
            w = max(px(40), e.width - pad)
            for lb in labels:
                try:
                    if abs(int(lb.cget("wraplength")) - w) > 2:
                        lb.configure(wraplength=w)
                except tk.TclError:
                    pass
        frame.bind("<Configure>", on, add="+")

    def draw_scan_rarities(self):
        on = set(self.cfg["optimiser"]["scan_rarities"])
        light = UI.get("light")
        for r, pill in self.opt_rar_pills.items():
            col = bo.RARITY_COLOR[r]
            col = mix(col, "#000000", 0.3) if light else col
            if r in on:
                pill.set(r, mix(CARD, col, 0.22), col)
            else:
                pill.set(r, CARD2, DIM)
        off = [r for r in bo.RARITIES if r not in on]
        self.opt_rar_note.configure(text=("skipped: " + ", ".join(off) + " - click to scan them too") if off else
                                    "every rarity is scanned")

    def toggle_scan_rarity(self, r):
        on = self.cfg["optimiser"]["scan_rarities"]
        if r in on:
            if len(on) == 1:
                return  # something has to be scanned
            on.remove(r)
        else:
            on.append(r)
        self.cfg["optimiser"]["scan_rarities"] = [x for x in bo.RARITIES if x in on]
        save_config(self.cfg)
        self.draw_scan_rarities()
        self.refresh_optimiser()

    def open_opt_tutorial(self):
        GuideWindow(self, OPT_TUTORIAL.splitlines(), "Build optimiser - how to use it")

    def opt_owned(self):
        o = self.cfg["optimiser"]
        return dict(o["perks"]), set(o["memories"])

    def on_opt_setting(self):
        o = self.cfg["optimiser"]
        o["playstyle"] = self.opt_ps.get()
        o["family"] = self.opt_family.get()
        o["capstones"] = [c for c, v in self.opt_caps.items() if v.get()]
        save_config(self.cfg)
        self.refresh_optimiser()

    def refresh_optimiser(self):
        if getattr(self, "opt_scroll", None) is None:
            return
        if self.opt_board is not None:
            self.opt_board.destroy()
        o = self.cfg["optimiser"]
        ps, fam, caps = o["playstyle"], o["family"], tuple(o["capstones"])
        perks, mems = self.opt_owned()
        scanned = bool(perks)
        if scanned:
            build = bo.best_build(ps, perks, mems, fam, caps)
            nxt = bo.get_next(build, perks, mems, fam, caps, rarities=set(o["scan_rarities"]))
            why = bo.reasons(build, perks)
        else:
            allp, allm = bo.ideal_owned()
            build = bo.best_build(ps, allp, allm, fam, caps)
            nxt, why = [], []
        board = tk.Frame(self.opt_scroll.inner, bg=BG)
        board.pack(fill="both", expand=True)
        self.opt_board = board
        light = UI.get("light")

        def rcol(rarity):
            c = bo.RARITY_COLOR.get(rarity, TEXT)
            return mix(c, "#000000", 0.3) if light else c

        head = tk.Frame(board, bg=BG)
        head.pack(fill="x", pady=(0, px(8)))
        label(head, ("BEST BUILD FROM WHAT YOU OWN - %s" % ps.upper()) if scanned else
              ("BEST POSSIBLE BUILD - %s" % ps.upper()), 8, ACCENT, True).pack(side="left")
        if not scanned:
            label(head, "every perk at +10 - scan your perks to see your own", 8, DIM).pack(side="left", padx=(px(10), 0))
        if o["scanned_at"]:
            label(head, "%d perks, %d memories - scanned %s" % (
                len(perks), len(mems), time.strftime("%d %b %H:%M", time.localtime(o["scanned_at"]))),
                8, DIM).pack(side="right")
        tiles = tk.Frame(board, bg=BG)
        tiles.pack(fill="x")
        n = len(build.slots)
        for i, (slot, c) in enumerate(zip(build.slots, build.chosen)):
            divine = bool(c) and bo.PERKS[c[0]]["rarity"] == "Divine"
            gold = rcol("Divine")
            t = RoundCard(tiles, fill=CARD, edge=(gold, gold) if divine else (EDGE_HI, EDGE))
            t.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else px(10), 0))
            tiles.grid_columnconfigure(i, weight=1, uniform="slot")
            inner = tk.Frame(t, bg=CARD)
            inner.pack(fill="both", expand=True, padx=px(14), pady=px(12))
            wrap = [label(inner, slot.name.upper(), 7, DIM, True, wraplength=px(60), justify="left")]
            wrap[0].pack(anchor="w")
            if not c:
                wrap.append(label(inner, "Nothing for this slot", 10, DIM, wraplength=px(60), justify="left"))
                wrap[-1].pack(anchor="w", pady=(px(8), 0))
                self.autowrap(inner, wrap)
                continue
            name, lv = c
            p = bo.PERKS[name]
            wrap.append(label(inner, name, 11, rcol(p["rarity"]), True, wraplength=px(60), justify="left"))
            wrap[-1].pack(anchor="w", pady=(px(5), 0))
            wrap.append(label(inner, "%s  -  +%d" % (p["rarity"], lv), 8, MUTED, wraplength=px(60), justify="left"))
            wrap[-1].pack(anchor="w")
            for line in bo.perk_lines(name, lv, 2, ps):
                wrap.append(label(inner, line, 8, mix(TEXT, MUTED, 0.35), wraplength=px(60), justify="left"))
                wrap[-1].pack(anchor="w", pady=(px(4), 0))
            self.autowrap(inner, wrap)
        low = tk.Frame(board, bg=BG)
        low.pack(fill="x", pady=(px(12), 0))
        low.grid_columnconfigure(0, weight=3, uniform="low")
        low.grid_columnconfigure(1, weight=2, uniform="low")
        left = card(low)
        left.grid(row=0, column=0, sticky="nsew")
        lin = tk.Frame(left, bg=CARD)
        lin.pack(fill="both", expand=True, padx=px(20), pady=px(16))
        label(lin, "MEMORIES", 7, ACCENT, True).pack(anchor="w")
        chips = tk.Frame(lin, bg=CARD)
        chips.pack(anchor="w", fill="x", pady=(px(8), 0))
        required = bo.RULES[ps]["memories"]
        if build.memories:
            rowc = None
            for j, m in enumerate(build.memories):
                if j % 3 == 0:
                    rowc = tk.Frame(chips, bg=CARD)
                    rowc.pack(anchor="w")
                pill = Pill(rowc, font=(FONT_SEMI, 8))
                req = m in required
                pill.set(m + ("  -  required" if req else ""), mix(CARD, GOOD, 0.18) if req else CARD2,
                         GOOD if req else TEXT)
                pill.pack(side="left", padx=(0, px(6)), pady=(0, px(6)))
        else:
            nm = label(chips, "No memories yet - open Equipment > Prestige in Roblox and press Scan memories.", 9, DIM,
                       wraplength=px(200), justify="left")
            nm.pack(anchor="w")
            self.autowrap(chips, [nm])
        label(lin, "WHY THIS BUILD", 7, ACCENT, True).pack(anchor="w", pady=(px(12), px(4)))
        lines = why or (["The strongest perk for each slot at +10, using the game's numbers for %s and the "
                          "macro's rules." % ps] if not scanned else ["Every perk you own was checked in every slot "
                                                                     "it fits."])
        never = bo.RULES[ps]["never"]["perks"]
        if never and not scanned:
            lines.append("Never used for %s: %s (they change how you move, which the routines rely on)."
                         % (ps, ", ".join(never)))
        why_lbls = []
        for s in lines:
            why_lbls.append(label(lin, s, 9, mix(TEXT, MUTED, 0.25), wraplength=px(200), justify="left"))
            why_lbls[-1].pack(anchor="w", pady=(0, px(3)))
        self.autowrap(lin, why_lbls)
        right = card(low)
        right.grid(row=0, column=1, sticky="nsew", padx=(px(12), 0))
        rin = tk.Frame(right, bg=CARD)
        rin.pack(fill="both", expand=True, padx=px(20), pady=px(16))
        label(rin, "GET NEXT", 7, ACCENT, True).pack(anchor="w")
        if not scanned:
            steps = ["In Roblox open Equipment > Perks and click your Body slot - the perk list shows.",
                     "Press Scan my perks. The macro clicks each perk and reads it (Stop key or mouse in the "
                     "top-left corner stops it).",
                     "Open Equipment > Prestige and press Scan memories (and again on the memory Storage).",
                     "Set your family and unlocked capstones above."]
            for j, s in enumerate(steps):
                r = tk.Frame(rin, bg=CARD)
                r.pack(fill="x", pady=(px(8), 0))
                num = Pill(r, font=(FONT_SEMI, 8))
                num.set(str(j + 1), ACCENT_BG, ACCENT_SOFT)
                num.pack(side="left", anchor="n")
                tf = tk.Frame(r, bg=CARD)
                tf.pack(side="left", fill="x", expand=True, padx=(px(8), 0))
                st = label(tf, s, 9, TEXT, wraplength=px(120), justify="left")
                st.pack(anchor="w")
                self.autowrap(tf, [st])
        elif not nxt:
            done = label(rin, "Nothing left to get - this is the best %s build there is." % ps, 9, MUTED,
                         wraplength=px(150), justify="left")
            done.pack(anchor="w", pady=(px(8), 0))
            self.autowrap(rin, [done])
        for j, r in enumerate(nxt):
            rowf = tk.Frame(rin, bg=CARD)
            rowf.pack(fill="x", pady=(px(10), 0))
            num = Pill(rowf, font=(FONT_SEMI, 8))
            num.set(str(j + 1), mix(CARD, BAD, 0.2) if r["required"] else ACCENT_BG, BAD if r["required"] else ACCENT_SOFT)
            num.pack(side="left", anchor="n")
            gain = "required" if r["required"] else "+%d%%" % round(r["gain"])
            label(rowf, gain, 10, BAD if r["required"] else GOOD, True).pack(side="right", anchor="n",
                                                                           padx=(px(8), 0))
            txt = tk.Frame(rowf, bg=CARD)
            txt.pack(side="left", fill="x", expand=True, padx=(px(8), 0))
            t1 = label(txt, r["title"], 10, TEXT, True, wraplength=px(120), justify="left")
            t1.pack(anchor="w")
            t2 = label(txt, r["detail"], 8, MUTED, wraplength=px(120), justify="left")
            t2.pack(anchor="w")
            self.autowrap(txt, [t1, t2])
        if scanned and nxt:
            label(rin, "%% = how much stronger your %s build gets." % ps, 7, DIM).pack(anchor="w", pady=(px(12), 0))
        redraw_cards(board)

    def update_scan_buttons(self):
        if getattr(self, "opt_scan_btn", None) is None:
            return
        scanning = self.scanner.running()
        b = self.opt_scan_btn
        if scanning:
            b.style_name, b.command = "danger", self.stop_scan
            b.set_text("Stop scan")
            b.set_enabled(True)
        else:
            b.style_name, b.command = "primary", lambda: self.start_scan("perks")
            b.set_text("Scan my perks")
            b.set_enabled(not self.engine.running())
        self.opt_mem_btn.set_enabled(not scanning and not self.engine.running())

    def stop_scan(self):
        if self.scanner.running():
            self.scanner.stop()
            self.opt_status.configure(text="Stopping the scan...")

    def start_scan(self, what):
        if self.engine.running():
            self.add_log("Stop the macro first - the scan uses the mouse")
            return
        if self.scanner.start(what):
            stop_key = key_display(self.cfg["keys"].get("scan_stop", "esc"))
            self.scan_progress = "Scanning your %s..." % what
            self.opt_status.configure(text="Scanning - press %s or move the mouse to stop it" % stop_key)
            self.mini.show()  # on top of Roblox: what it's doing and how to stop it
            self.add_log("Build optimiser: reading your %s from the game..." % what)
            self.update_scan_buttons()

    def scan_done(self, res):
        if not self.engine.running():
            self.mini.hide()
        o = self.cfg["optimiser"]
        if res.get("ok"):
            if res["what"] == "perks":
                perks = res.get("perks") or {}
                if res.get("all_tabs"):
                    o["perks"] = perks  # every tab was read: this is the whole list
                else:
                    for n, lv in perks.items():
                        o["perks"][n] = max(o["perks"].get(n, -1), lv)
                o["scanned_at"] = time.time()
                msg = "Read %d kinds of perks in %s" % (len(perks), fmt_dur(res.get("seconds", 0)))
                if res.get("skipped"):
                    msg += ", %d tiles skipped by your filter" % res["skipped"]
                if not res.get("all_tabs"):
                    msg += " (one category - open the next tab in Roblox and scan again to add it)"
            else:
                got = res.get("memories") or []
                o["memories"] = [m for m in bo.MEMORIES if m in set(o["memories"]) | set(got)]
                o["memories_at"] = time.time()
                msg = "Read %d memories: %s" % (len(got), ", ".join(got))
            save_config(self.cfg)
            self.add_log("Build optimiser: " + msg)
            self.opt_status.configure(text=msg if len(msg) < 90 else msg[:87] + "...")
        else:
            self.add_log("Build optimiser: " + res.get("error", "scan failed"))
            self.opt_status.configure(text=res.get("error", "scan failed")[:90])
        self.update_scan_buttons()
        self.refresh_optimiser()
        try:
            present(self.root)
        except Exception:
            pass

    def open_opt_edit(self):
        OptimiserEditWindow(self)

    def build_appearance(self):
        page = tk.Frame(self.tab_card, bg=BG)
        self.tabs["Appearance"] = page
        cur = self.cfg["app"]["theme"]
        acc_now = (self.cfg["app"]["accent"] or THEMES[cur]["accent"]).lower()
        box = card(page)
        box.pack(fill="x")
        inner = tk.Frame(box, bg=CARD)
        inner.pack(fill="x", padx=px(24), pady=px(20))
        label(inner, "Theme", 11, TEXT, True).pack(anchor="w")
        label(inner, "Colours for every window. Changes apply right away.", 9, MUTED).pack(anchor="w", pady=(px(2), px(14)))
        grid = tk.Frame(inner, bg=CARD)
        grid.pack(anchor="w")
        W, H = px(164), px(96)
        for i, name in enumerate(THEMES):
            t = THEMES[name]
            acc = self.cfg["app"]["accent"] or t["accent"]
            tile = tk.Frame(grid, bg=CARD)
            tile.grid(row=i // 3, column=i % 3, padx=(0, px(14)), pady=(0, px(14)), sticky="w")
            cv = tk.Canvas(tile, width=W, height=H, bg=CARD, highlightthickness=0, bd=0, cursor="hand2")
            cv.pack()
            sel = name == cur
            imgs = []

            def put(img, x, y):
                imgs.append(img)
                cv.create_image(x, y, image=img, anchor="nw")
            put(rounded_image(W, H, px(12), ACCENT if sel else t["edge_hi"]), 0, 0)
            b = px(2) if sel else 1
            put(rounded_image(W - 2 * b, H - 2 * b, px(11), t["bg"]), b, b)
            put(rounded_image(px(30), H - px(16), px(6), t["side"]), px(8), px(8))
            put(rounded_image(px(14), px(4), px(2), acc), px(16), px(18))
            put(rounded_image(px(14), px(4), px(2), t["dim"]), px(16), px(28))
            put(rounded_image(W - px(54), px(32), px(7), t["card"]), px(46), px(8))
            put(rounded_image(px(40), px(5), px(2), t["text"]), px(54), px(16))
            put(rounded_image(px(28), px(9), px(4), acc), px(54), px(26))
            put(rounded_image((W - px(60)) // 2, px(36), px(7), t["card"]), px(46), px(48))
            put(rounded_image((W - px(60)) // 2, px(36), px(7), t["card"]), px(52) + (W - px(60)) // 2, px(48))
            cv.images = imgs
            cv.bind("<Button-1>", lambda e, n=name: self.set_theme(n))
            label(tile, name, 9, TEXT if sel else MUTED, sel).pack(anchor="w", pady=(px(6), 0))

        box2 = card(page)
        box2.pack(fill="x", pady=(px(14), 0))
        inner2 = tk.Frame(box2, bg=CARD)
        inner2.pack(fill="x", padx=px(24), pady=px(20))
        label(inner2, "Accent colour", 11, TEXT, True).pack(anchor="w")
        label(inner2, "Buttons, highlights, progress and the selected page.", 9, MUTED).pack(anchor="w",
                                                                                         pady=(px(2), px(14)))
        row = tk.Frame(inner2, bg=CARD)
        row.pack(anchor="w")
        S = px(34)
        for col in ACCENT_PRESETS:
            cv = tk.Canvas(row, width=S, height=S, bg=CARD, highlightthickness=0, bd=0, cursor="hand2")
            cv.pack(side="left", padx=(0, px(8)))
            imgs = []
            if col.lower() == acc_now:
                imgs.append(rounded_image(S, S, S // 2, TEXT))
                cv.create_image(0, 0, image=imgs[-1], anchor="nw")
                imgs.append(rounded_image(S - px(4), S - px(4), (S - px(4)) // 2, CARD))
                cv.create_image(px(2), px(2), image=imgs[-1], anchor="nw")
            imgs.append(rounded_image(S - px(10), S - px(10), (S - px(10)) // 2, col))
            cv.create_image(px(5), px(5), image=imgs[-1], anchor="nw")
            cv.images = imgs
            cv.bind("<Button-1>", lambda e, c=col: self.set_accent(c))
        Btn(row, "Custom...", self.pick_accent, "normal", padx=px(14), pady=px(6), font=(FONT_SEMI, 9),
            radius=px(8)).pack(side="left", padx=(px(6), px(6)))
        Btn(row, "Theme default", lambda: self.set_accent(""), "ghost", padx=px(12), pady=px(6), font=(FONT_SEMI, 9),
            radius=px(8)).pack(side="left")
        label(inner2, "Current accent: %s%s" % (ACCENT.upper(), "" if self.cfg["app"]["accent"] else " (theme default)"),
              8, DIM).pack(anchor="w", pady=(px(14), 0))

    def set_theme(self, name):
        if name != self.cfg["app"]["theme"]:
            self.cfg["app"]["theme"] = name
            save_config(self.cfg)
            self.retheme()

    def set_accent(self, color):
        if color != self.cfg["app"]["accent"]:
            self.cfg["app"]["accent"] = color
            save_config(self.cfg)
            self.retheme()

    def pick_accent(self):
        from tkinter import colorchooser
        try:
            res = colorchooser.askcolor(color=ACCENT, title="Accent colour", parent=self.root)
        except tk.TclError:
            return
        if res and res[1] and HEX_COLOR.match(res[1]):
            self.set_accent(res[1].lower())

    def retheme(self):
        """Rebuild the windows with the current theme (the macro keeps running)."""
        apply_theme(self.cfg["app"]["theme"], self.cfg["app"]["accent"])
        page = self.tab_var.get()
        settings_page = None
        if self.settings is not None and self.settings.top.winfo_exists():
            settings_page = getattr(self.settings, "page_name", None)
            self.settings.close()
        mini = self.mini.pill is not None
        self.mini.hide()
        if self.graph_job is not None:
            self.root.after_cancel(self.graph_job)
            self.graph_job = None
        for w in self.root.winfo_children():
            if not isinstance(w, tk.Toplevel):
                w.destroy()
        self.root.configure(bg=BG)
        dark_titlebar(self.root)
        now_title, step = self.now_title, self.current_step
        self.build()
        self.log_txt.configure(state="normal")
        for ts, text in self.log_lines:
            self.log_txt.insert("end", ts + "   ", "ts")
            self.log_txt.insert("end", text + "\n")
        self.log_txt.see("end")
        self.log_txt.configure(state="disabled")
        self.show_tab(page if page in self.tabs else "Dashboard")
        self.set_status(self.engine.state)
        if self.engine.running():
            self.set_now(now_title)
            self.set_step(step)
        self.refresh_stats()
        if mini:
            self.mini.show()
        if settings_page and not self.headless:
            self.open_settings(settings_page)

    def show_tab(self, name):
        for f in self.tabs.values():
            f.pack_forget()
        self.tabs[name].pack(fill="both", expand=True)
        self.tab_var.set(name)
        for key, item in self.nav.items():
            item.set_selected(key == name)
        self.page_lbl.configure(text=NAV_TEXT.get(name, name))
        if name == "Dashboard":
            self.apply_subtitle()
        else:
            self.subtitle.configure(text=PAGE_SUBTITLES.get(name, ""))
        redraw_cards(self.tabs[name])
        if name == "Optimiser" and not self.cfg["optimiser"].get("tutorial_seen") and not self.headless:
            self.cfg["optimiser"]["tutorial_seen"] = True
            save_config(self.cfg)
            self.root.after(250, self.open_opt_tutorial)
        if name == "Graph":
            self.schedule_graph()

    # ---- stats graph ------------------------------------------------------------------------------
    def graph_routine(self):
        return self.engine.routine if self.engine.running() else self.cfg["routine"]

    def schedule_graph(self, delay=120):
        if self.graph_job is not None:
            self.root.after_cancel(self.graph_job)
        self.graph_job = self.root.after(delay, self.draw_graph)

    def draw_graph(self):
        self.graph_job = None
        if self.tab_var.get() != "Graph" or not self.graph_lbl.winfo_viewable():
            return
        w, h = self.graph_lbl.winfo_width(), self.graph_lbl.winfo_height()
        if w < 60 or h < 60:
            return
        now = time.time()
        routine = self.graph_routine()
        try:
            runs = read_run_log(now - 24 * 3600, routine)
            num = report_numbers(runs, now)
            for key in ("done", "per_hour", "avg", "best", "rate", "rescued"):
                self.kpi_lbls[key].configure(text=str(num[key]) if num["done"] else "-")
            img = render_analytics(runs, routine, now, size=(w, h), scale=UI["scale"])
        except Exception as e:
            self.graph_lbl.configure(image="", text="Could not draw the graph: %s" % e, fg=DIM)
            return
        if img.size != (w, h):
            img = img.resize((w, h), Image.LANCZOS)
        self.graph_photo = ImageTk.PhotoImage(img)
        self.graph_lbl.configure(image=self.graph_photo, text="")
        self.graph_note.configure(text="Last 24 hours, %s" % routine)

    def save_graph(self):
        routine = self.graph_routine()
        try:
            png = report_png(routine, self.engine.session)
            path = os.path.join(DATA_DIR, "stats_report.png")
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(png)
            os.startfile(path)
        except Exception as e:
            self.add_log("Could not save the stats picture (%s)" % e)

    def send_graph(self, note=None, quiet=False):
        """Send the stats report picture to Discord."""
        say = note or (lambda text, color=None: self.add_log(text))
        if not self.discord.ready():
            say("Discord isn't set up (Settings > Discord)", WARN)
            return False
        routine = self.graph_routine()
        try:
            png = report_png(routine, self.engine.session)
        except Exception as e:
            say("Could not draw the stats graph (%s)" % e, BAD)
            return False
        self.discord.send("Stats report - %s, last 24 hours" % routine, png=png)
        if not quiet:
            say("Stats graph sent to Discord", GOOD)
        return True

    def graph_timer(self):
        """Every minute: keep the Graph tab current; send the hourly Discord graph when it's turned on."""
        e = self.engine
        if self.tab_var.get() == "Graph" and self.visible():
            self.schedule_graph(10)
        if e.running() and e.session["start"] and self.cfg["discord"].get("notify_graph") and self.discord.ready():
            last = self.last_graph_sent or e.session["start"]
            if time.time() - last >= 3600:
                self.last_graph_sent = time.time()
                if self.send_graph(quiet=True):
                    self.add_log("Discord: hourly stats graph sent")
        elif not e.running():
            self.last_graph_sent = None
        self.root.after(60000, self.graph_timer)

    # ---- helpers -----------------------------------------------------------------------------
    def step_names(self):
        return ROUTINE_STEPS[self.engine.routine if self.engine.running() else self.cfg["routine"]]

    def apply_routine(self):
        routine = self.cfg["routine"]
        raid = routine == "Female Raid"
        if self.tab_var.get() == "Dashboard":
            self.apply_subtitle()
        self.refresh_build_page()
        self.loot_lbls["main"][0].configure(text="VESSELS" if raid else "SCROLLS")
        for kind in FRAGMENT_KINDS + SERUM_KINDS:
            self.loot_lbls[kind][0].configure(text=LOOT_SHORT[kind].upper())
        self.set_step(None)
        self.refresh_stats()

    def apply_subtitle(self):
        hints = {"Blood Awakening": "Colossal + Blood Awakening", "Shiki": "Shiki build", "Universal": "Thunder spears",
                 "Female Raid": "Female Raid - set the chest spots in Settings"}
        self.subtitle.configure(text=hints[self.cfg["routine"]])

    def on_routine(self, value):
        if self.engine.running():
            self.routine_var.set(self.cfg["routine"])
            self.routine_seg.set_text("%s   \u25be" % self.cfg["routine"])
            self.add_log("Stop the macro before changing the routine")
            return
        self.cfg["routine"] = value
        save_config(self.cfg)
        self.apply_routine()
        self.add_log("Routine: %s" % value)
        if value == "Female Raid" and not self.cfg["timings"]["Female Raid"]["chest1"]:
            self.add_log("Female Raid: pick the chest spots in Settings > Timings > Female Raid first")

    def refresh_hotkey_labels(self):
        k = self.cfg["keys"]
        self.pause_btn.set_text("Resume" if self.engine.paused else "Pause")
        self.keys_hint.configure(text="%s  start        %s  pause / resume        %s  stop" % (
            key_display(k["start"]), key_display(k["pause"]), key_display(k["stop"])))

    def update_buttons(self):
        running = self.engine.running()
        self.start_btn.set_enabled(not running or self.engine.state == "waiting")
        self.start_btn.set_text("Start now" if running and self.engine.state == "waiting" else "Start")
        self.pause_btn.set_enabled(running)
        self.stop_btn.set_enabled(running)
        self.routine_seg.set_enabled(not running)
        self.refresh_hotkey_labels()
        self.update_scan_buttons()

    def add_log(self, text):
        ts = time.strftime("%H:%M:%S")
        self.log_lines.append((ts, text))
        del self.log_lines[:-400]
        self.log_txt.configure(state="normal")
        self.log_txt.insert("end", ts + "   ", "ts")
        self.log_txt.insert("end", text + "\n")
        lines = int(self.log_txt.index("end-1c").split(".")[0])
        if lines > 600:
            self.log_txt.delete("1.0", "%d.0" % (lines - 500))
        self.log_txt.see("end")
        self.log_txt.configure(state="disabled")
        if self.log_file:
            try:
                self.log_file.write("%s  %s\n" % (ts, text))
                self.log_file.flush()
            except Exception:
                pass

    def set_status(self, status):
        text, bg, fg = STATUS_LOOK.get(status, STATUS_LOOK["idle"])
        self.pill.set("●  " + text, bg, fg)
        if status == "idle":
            self.set_now("Ready", "Press Start, then click into Roblox")
        self.update_buttons()
        self.mini.update()

    def set_step(self, name):
        self.current_step = name
        names = self.step_names()
        i = names.index(name) if name in names else -1
        if i < 0:
            routine = self.engine.routine if self.engine.running() else self.cfg["routine"]
            self.eyebrow.configure(text="WAITING" if self.engine.running() else "%s  ·  %d STEPS" % (
                routine.upper(), len(names)))
            self.next_lbl.configure(text="FIRST  ·  %s" % names[0].upper())
        else:
            self.eyebrow.configure(text="STEP %d OF %d" % (i + 1, len(names)))
            self.next_lbl.configure(text=("NEXT  ·  %s" % names[i + 1].upper()) if i + 1 < len(names) else "")
        self.draw_progress()

    def draw_progress(self):
        c = self.prog
        W = c.winfo_width()
        if W < 20:
            return
        names = self.step_names()
        n = len(names)
        cur = names.index(self.current_step) if self.current_step in names else -1
        gap, h = px(4), px(6)
        sw = (W - gap * (n - 1)) / float(n)
        live = mix(ACCENT, ACCENT_SOFT, round(self.breath * 6) / 6.0 * 0.45)
        imgs = []
        c.delete("all")
        for i in range(n):
            col = CARD2 if cur < 0 or i > cur else SEG_DONE if i < cur else live
            x0 = int(round(i * (sw + gap)))
            x1 = int(round(i * (sw + gap) + sw))
            img = rounded_image(max(2, x1 - x0), h, h // 2, col)
            c.create_image(x0, 0, image=img, anchor="nw")
            imgs.append(img)
        c.images = imgs

    def visible(self):
        try:
            return self.root.state() == "normal"
        except tk.TclError:
            return False

    def breathe(self):
        if self.current_step is not None and self.engine.running() and not self.engine.paused and self.visible():
            self.breath = (math.sin(time.time() * 2 * math.pi / 1.8) + 1) / 2
            self.draw_progress()
        self.root.after(90, self.breathe)

    def set_now(self, title, detail=None):
        self.now_title = title
        self.now_lbl.configure(text=title)
        if detail is not None:
            self.detail_lbl.configure(text=detail)
        self.mini.update()

    def refresh_stats(self):
        s = self.engine.session
        raid = (self.engine.raid_mode if self.engine.running() else self.cfg["routine"] == "Female Raid")
        self.stat_lbls["retries"].configure(text=str(s["retries"]))
        self.stat_lbls["completed"].configure(text=str(s["completed"]))
        self.stat_lbls["failed"].configure(text=str(s["failed"]))
        done = s["completed"] + s["failed"]
        self.stat_lbls["rate"].configure(text=("%d%%" % (100 * s["completed"] // done)) if done else "-")
        self.stat_lbls["rescues"].configure(text=str(s["rescues"]))
        lengths = s["lengths"][-20:]
        self.stat_lbls["avg"].configure(text=fmt_run(sum(lengths) / len(lengths)) if lengths else "-")
        routine = self.engine.routine if self.engine.running() else self.cfg["routine"]
        self.stat_lbls["best"].configure(text=fmt_run(self.cfg["stats"].get("best", {}).get(routine)))
        if s["start"]:
            elapsed = max(1.0, time.time() - s["start"] - s["paused"])
            self.stat_lbls["session"].configure(text=fmt_dur(time.time() - s["start"]))
            self.stat_lbls["hour"].configure(text=("%.1f" % (s["retries"] * 3600.0 / elapsed)) if s["retries"] else "-")
        else:
            self.stat_lbls["session"].configure(text="-")
            self.stat_lbls["hour"].configure(text="-")
        main = "vessel" if raid else "scroll"
        self.loot_lbls["main"][1].configure(text=str(s["loot"][main]))
        for kind in FRAGMENT_KINDS + SERUM_KINDS:
            self.loot_lbls[kind][1].configure(text=str(s["loot"][kind]))
        for fam in ("missions", "raids"):
            st = self.cfg["stats"][fam]
            for key in ("runs", "retries", "completed", "failed", "rescues"):
                self.total_lbls[(fam, key)].configure(text=str(st[key]))
            fmain = "vessel" if fam == "raids" else "scroll"
            parts = ["%s %d" % (LOOT_SHORT[k], st["loot"][k]) for k in (fmain,) + FRAGMENT_KINDS + SERUM_KINDS if st["loot"][k]]
            self.total_lbls[(fam, "loot")].configure(text="Loot: " + (", ".join(parts) if parts else "none yet"))
            names = ("Female Raid",) if fam == "raids" else ("Blood Awakening", "Shiki", "Universal")
            bests = self.cfg["stats"].get("best", {})
            self.total_lbls[(fam, "best")].configure(
                text="Best: " + "   ".join("%s %s" % (n, fmt_run(bests.get(n))) for n in names))
        self.mini.update()

    def timer_tick(self):
        if not self.visible():  # minimized: nothing to draw
            self.root.after(500, self.timer_tick)
            return
        e = self.engine
        t0 = e.mission_t0
        if t0 is not None and e.running():
            if not e.paused:
                self.timer_lbl.configure(text=fmt_run(time.time() - t0), fg=TEXT)
        else:
            hist = e.session["history"]
            last = hist[-1]["time"] if hist else None
            self.timer_lbl.configure(text=fmt_run(last) if last else "", fg=DIM)
        self.root.after(150, self.timer_tick)

    def refresh_runs(self):
        hist = self.engine.session["history"]
        for w in self.history_frame.winfo_children():
            w.destroy()
        if not hist:
            self.last_run_lbl.configure(text="")
            label(self.history_frame, "No runs yet - they show up here with their time, result and loot.", 9, DIM).pack(anchor="w")
            self.draw_breakdown()
            return
        last = hist[-1]
        self.last_run_lbl.configure(text="#%d   %s%s" % (last["n"], fmt_run(last["time"]), "   NEW BEST" if last["best"] else ""),
                                    fg=ACCENT_SOFT if last["best"] else DIM)
        colors = {"completed": GOOD, "failed": BAD}
        for row, ent in enumerate(reversed(hist[-8:])):
            res = "Failsafe" if ent["rescued"] else {"completed": "Completed", "failed": "Failed"}.get(ent["result"], "-")
            cells = (("#%d" % ent["n"], DIM, False), (fmt_run(ent["time"]), TEXT, True),
                     (res, colors.get(ent["result"], WARN if ent["rescued"] else MUTED), False),
                     (", ".join(LOOT_SHORT[k] for k in ent["loot"]) or "no loot", MUTED, False),
                     ("\u2605 best" if ent["best"] else "", ACCENT_SOFT, True))
            for col, (text, color, bold) in enumerate(cells):
                label(self.history_frame, text, 9, color, bold).grid(row=row, column=col, sticky="w",
                                                                      padx=(0, px(18)), pady=px(1))
        self.history_frame.grid_columnconfigure(3, weight=1)
        self.draw_breakdown()

    def draw_breakdown(self):
        c = self.breakdown
        c.delete("all")
        hist = self.engine.session["history"]
        steps = hist[-1]["steps"] if hist else []
        W = c.winfo_width()
        if not steps or W < 120:
            c.configure(height=px(20))
            c.create_text(0, px(10), text="Each step of the last run, so you can see where the time goes.",
                          fill=DIM, font=(FONT, 9), anchor="w")
            return
        row_h, name_w, val_w, bar_h = px(19), px(110), px(56), px(7)
        c.configure(height=row_h * len(steps))
        longest = max(d for _, d in steps) or 1.0
        imgs = []
        for i, (name, dur) in enumerate(steps):
            y = i * row_h + row_h // 2
            c.create_text(0, y, text=name, fill=MUTED, font=(FONT, 9), anchor="w")
            bw = max(bar_h, int((W - name_w - val_w) * dur / longest))
            img = rounded_image(bw, bar_h, bar_h // 2, ACCENT if dur == longest else SEG_DONE)
            c.create_image(name_w, y - bar_h // 2, image=img, anchor="nw")
            imgs.append(img)
            c.create_text(W, y, text="%.1fs" % dur, fill=TEXT, font=(FONT_SEMI, 9), anchor="e")
        c.images = imgs

    def tick_clock(self):
        if self.engine.running():
            if self.visible():
                self.refresh_stats()
            else:
                self.mini.update()
        self.root.after(1000, self.tick_clock)

    def status_text(self):
        e = self.engine
        s = e.session
        if not e.running():
            phase = "Not running"
        elif e.paused:
            phase = "Paused"
        else:
            phase = STATUS_LOOK.get(e.state, STATUS_LOOK["idle"])[0] + " - " + self.now_title
        return "%s (%s). This session: %d done, %d completed, %d failed, %d failsafes." % (
            phase, self.cfg["routine"], s["retries"], s["completed"], s["failed"], s["rescues"])

    def stats_text(self):
        lines = []
        for fam, word in (("missions", "Missions"), ("raids", "Raids")):
            st = self.cfg["stats"][fam]
            if not st["runs"]:
                continue
            main = "vessel" if fam == "raids" else "scroll"
            loot = ", ".join("%s %d" % (LOOT_SHORT[k], st["loot"][k]) for k in (main,) + FRAGMENT_KINDS + SERUM_KINDS
                             if st["loot"][k])
            lines.append("%s (all time): %d started, %d done, %d completed, %d failed, %d failsafes. Loot: %s"
                         % (word, st["runs"], st["retries"], st["completed"], st["failed"], st["rescues"], loot or "none"))
        s = self.engine.session
        if s["start"]:
            lines.append("This session: %d done in %s" % (s["retries"], fmt_dur(time.time() - s["start"])))
        return "\n".join(lines) or "No runs yet."

    # ---- actions -----------------------------------------------------------------------------
    def on_start(self):
        if self.scanner.running():
            self.add_log("A build scan is running - wait for it or press Stop")
            return
        if self.engine.running():
            if self.engine.state == "waiting":
                self.engine.request_manual_start()
            return
        prev = user32.GetForegroundWindow()
        prev_is_ours = window_pid(prev) == os.getpid()
        if self.engine.start():
            self.add_log("Starting %s..." % self.cfg["routine"])
            self.update_buttons()
            self.refresh_stats()
            if self.cfg["app"]["mini_bar"]:
                self.mini.show()
            if self.cfg["app"]["minimize_on_start"]:
                self.root.iconify()

            def refocus():
                # The status bar / minimizing must not keep the keyboard: give it back to the game.
                if prev and not prev_is_ours:
                    user32.SetForegroundWindow(prev)
                elif self.cfg["app"]["focus_roblox"]:
                    if focus_roblox() is None:
                        self.add_log("Roblox isn't open yet - click into it once it is")
            self.root.after(200, refocus)

    def on_pause(self):
        if self.engine.running():
            paused = self.engine.toggle_pause()
            if not paused:
                self.add_log("Resuming...")
            self.refresh_hotkey_labels()

    def on_stop(self):
        if self.scanner.running():
            self.scanner.stop()
        if self.engine.running():
            self.add_log("Stopping...")
            self.engine.stop()

    def on_bot_command(self, cmd):
        e = self.engine
        say = self.discord.send
        self.add_log("Discord command: !%s" % cmd)
        if cmd == "start":
            if e.running():
                say("Already running. " + self.status_text())
            else:
                self.on_start()
                say("Starting %s..." % self.cfg["routine"])
        elif cmd == "pause":
            if not e.running():
                say("The macro isn't running.")
            elif e.paused:
                say("Already paused - use !resume.")
            else:
                self.on_pause()
                say("Paused.")
        elif cmd == "resume":
            if e.running() and e.paused:
                self.on_pause()
                say("Resumed.")
            else:
                say("Nothing to resume.")
        elif cmd == "stop":
            if e.running():
                self.on_stop()
                say("Stopping the macro...")
            else:
                say("The macro isn't running.")
        elif cmd == "reconnect":
            if not e.running():
                say("Start the macro first (!start).")
            elif not e.reconnect_on:
                missing = reconnect_missing(self.cfg, e.raid_mode)
                say("Reconnect is off. " + (("Still needed: " + ", ".join(missing) + ".") if missing else
                                            "Turn it on in Settings > Reconnect, then restart the macro."))
            elif e.reconnecting:
                say("Already reconnecting.")
            else:
                e.rc_request = True
                say("Reconnecting: closing Roblox, rejoining and clicking through the lobby...")
        elif cmd == "screenshot":
            say("Screenshot", screenshot=True)
        elif cmd == "stats":
            say(self.stats_text())
        elif cmd == "graph":
            self.send_graph(quiet=True)
        elif cmd == "status":
            say(self.status_text())
        else:
            say("Commands: " + BOT_COMMANDS_TEXT)

    def restore_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def open_settings(self, page=None):
        if self.settings is None or not self.settings.top.winfo_exists():
            self.settings = SettingsWindow(self)
        else:
            self.settings.top.deiconify()
            self.settings.top.lift()
        if page:
            self.settings.show_page(page)

    def open_guide(self):
        GuideWindow(self)

    def open_feedback(self):
        FeedbackWindow(self)

    def open_discord(self):
        """Opens the Colossal Macro Discord invite in the browser (help, updates, support tickets)."""
        try:
            opened = webbrowser.open(DISCORD_INVITE)
        except Exception:
            opened = False
        if opened:
            self.add_log("Opened the Colossal Macro Discord: " + DISCORD_INVITE)
        else:
            self.root.clipboard_clear()
            self.root.clipboard_append(DISCORD_INVITE)
            self.add_log("Couldn't open your browser - the Discord link is copied, paste it into one: "
                         + DISCORD_INVITE)

    def _all_windows(self):
        wins = [self.root]
        if self.settings is not None and self.settings.top.winfo_exists():
            wins.append(self.settings.top)
        return wins

    def _current_monitor(self):
        mons = list_monitors()
        idx = self.cfg["app"]["monitor"]
        if self.settings is not None and self.settings.top.winfo_exists():
            name = self.settings.mon_var.get()
            if name in self.settings.mon_names:
                idx = self.settings.mon_names.index(name)
        return mons[idx] if idx < len(mons) else mons[0]

    def _countdown(self, seconds, then):
        """Hide our windows, show a small countdown so the user can switch to Roblox, then run `then`."""
        mon = self._current_monitor()
        wins = self._all_windows()
        for w in wins:
            w.withdraw()
        w, h = px(300), px(46)
        toast = FloatingPill(self.root, w, h, alpha=0.97)
        txt = toast.canvas.create_text(w // 2, h // 2, text="", fill=TEXT, font=(FONT_SEMI, 11))
        toast.place(mon["left"] + (mon["width"] - w) // 2, mon["top"] + px(60))

        def step(n):
            if n <= 0:
                toast.destroy()
                self.root.after(250, lambda: then(mon, wins))
                return
            toast.canvas.itemconfigure(txt, text="Switch to Roblox   %d" % n)
            self.root.after(1000, lambda: step(n - 1))
        step(seconds)

    def _restore(self, wins):
        for w in wins:
            try:
                w.deiconify()
            except tk.TclError:
                pass
        if self.settings is not None and self.settings.top.winfo_exists():
            self.settings.top.lift()

    def screen_task(self, mode, hint, on_done):
        def go(mon, wins):
            try:
                img = grab_monitor(mon)
            except Exception as e:
                self._restore(wins)
                messagebox.showerror(APP_NAME, "Could not take a screenshot: %s" % e)
                return

            def finished(result):
                self._restore(wins)
                on_done(result)
            ScreenOverlay(self.root, mon, img, mode, hint, finished)
        self._countdown(3, go)

    def image_task(self, mon, img, hint, on_done):
        """Drag a box on a saved screenshot (shown full screen on `mon`)."""
        wins = self._all_windows()
        for w in wins:
            w.withdraw()

        def finished(result):
            self._restore(wins)
            on_done(result)
        self.root.after(150, lambda: ScreenOverlay(self.root, mon, img, "box", hint, finished))

    def detection_test(self, on_done):
        def go(mon, wins):
            lines = []
            det = None
            try:
                det = Detector(self.cfg, lambda t: None, mon=game_region(mon))
                shot = det.grab()
                if shot is None:
                    lines.append("The screen came back black - is Roblox on this screen?")
                else:
                    seen_extra = []
                    for key, p in PICTURES.items():
                        if not det.has(key):
                            if p["group"] == "Reconnect":
                                lines.append("%s: no picture yet" % p["label"])
                            continue
                        need = det.threshold(key)
                        scales = (RETRY_SCALES if key.startswith("retry") or key == "start" else det.end_scales()
                                  if p["group"] in ("Loot", "Results") else (1.0,))
                        best = det.best_any(key, shot, scales)
                        score = max(0.0, best.score) if best else 0.0
                        src = "your picture" if det.own.get(key) else "built-in"
                        if p["group"] in ("Loot", "Results"):
                            if score >= need:
                                seen_extra.append("%s (%.2f)" % (p["label"], score))
                            continue
                        state = "SEEN" if score >= need else "not seen"
                        lines.append("%s: %s (score %.2f, needs %.2f, %s)" % (p["label"], state, score, need, src))
                    lines.append("Results / loot seen: %s" % (", ".join(seen_extra) if seen_extra else "none"))
            except Exception as e:
                lines.append("Test failed: %s" % e)
            finally:
                if det is not None:
                    det.close()
            self._restore(wins)
            on_done(lines)
        self._countdown(3, go)

    # ---- events ------------------------------------------------------------------------------
    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self.add_log(msg[1])
                elif kind == "status":
                    self.set_status(msg[1])
                elif kind == "step":
                    self.set_step(msg[1])
                elif kind == "show":
                    self.set_now(msg[1], msg[2])
                elif kind == "detail":
                    self.detail_lbl.configure(text=msg[1])
                elif kind == "stats":
                    self.refresh_stats()
                elif kind == "save":
                    save_config(self.cfg)
                elif kind == "trace":
                    if self.log_file:
                        self.log_file.write(msg[1])
                        self.log_file.flush()
                elif kind == "done":
                    save_config(self.cfg)
                    self.mini.hide()
                    self.update_buttons()
                    self.refresh_stats()
                    if self.root.state() == "iconic":
                        self.restore_window()
                elif kind == "hotkey":
                    self.on_hotkey(msg[1])
                elif kind == "opt_progress":
                    self.scan_progress = msg[1].replace("Reading your perks - ", "Scanning - ")
                    if getattr(self, "opt_status", None) is not None:
                        self.opt_status.configure(text=msg[1])
                    self.mini.update()
                elif kind == "opt_done":
                    self.scan_done(msg[1])
                elif kind == "bot":
                    self.on_bot_command(msg[1])
                elif kind == "run":
                    self.refresh_runs()
                    self.refresh_stats()
                    if self.tab_var.get() == "Graph":
                        self.schedule_graph(400)
                elif kind == "discord_test":
                    if self.settings is not None and self.settings.top.winfo_exists():
                        self.settings.discord_test_result(msg[1], msg[2])
        except queue.Empty:
            pass
        self.root.after(50, self.poll)

    def on_hotkey(self, action):
        if action == "start":
            self.on_start()
        elif action == "pause":
            self.on_pause()
        elif action == "stop":
            self.on_stop()
        elif action == "scan_stop":
            self.stop_scan()

    def hotkey_loop(self):
        prev = {}
        last = {}
        while True:
            try:
                if not self.binding:
                    now = time.time()
                    for action in HOTKEYS:
                        down = key_is_down(self.cfg["keys"][action])
                        if down and not prev.get(action) and now - last.get(action, 0) > 0.3:
                            last[action] = now
                            self.q.put(("hotkey", action))
                        prev[action] = down
                else:
                    prev = {a: True for a in HOTKEYS}  # ignore keys held while binding
            except Exception:
                pass
            time.sleep(0.03)

    def on_close(self):
        if self.engine.running():
            self.engine.stop()
            if self.engine.thread:
                self.engine.thread.join(timeout=2)
        try:
            self.engine.release_all()
        except Exception:
            pass
        save_config(self.cfg)
        if self.log_file:
            try:
                self.log_file.close()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def selftest(out_path):
    """Builds every window without showing it and checks the bundled files - nothing is pressed, shown or sent.
    Usage: "Colossal Macro.exe" --selftest result.txt"""
    lines = []

    def ok(name, cond, extra=""):
        lines.append(("PASS " if cond else "FAIL ") + name + ((" - " + extra) if extra else ""))

    try:
        ok("SendInput struct size", ctypes.sizeof(INPUT) == 40, str(ctypes.sizeof(INPUT)))
        ok("guide bundled", os.path.isfile(resource_path(GUIDE_FILE)))
        ok("icon bundled", os.path.isfile(resource_path("assets", "icon.ico")))
        for key, p in PICTURES.items():
            if p["files"]:
                imgs = [read_image(resource_path("assets", *rel.split("/"))) for rel in p["files"].values()]
                ok("picture '%s' bundled" % key, all(i is not None for i in imgs), "%d file(s)" % len(imgs))
        app = App(headless=True)
        ok("main window builds", True)
        for routine in ROUTINES:
            app.cfg["routine"] = routine
            app.apply_routine()
        ok("all routines switch", True)
        for name in THEMES:
            app.cfg["app"]["theme"] = name
            app.retheme()
        app.cfg["app"]["theme"] = "Midnight"
        app.retheme()
        ok("every theme builds", set(app.tabs) == {"Optimiser", "Dashboard", "Build", "Runs", "Graph", "Loot", "Stats",
                                                   "Appearance"} and app.tab_var.get() in app.tabs)
        app.open_settings()
        app.settings.top.withdraw()
        for page in SettingsWindow.NAV:
            app.settings.show_page(page)
        for sec in TIMING_SECTIONS:
            app.settings.show_tsec(sec)
        timings, bad = app.settings.read_timings()
        ok("settings window builds, timings read back", not bad and all(len(timings[s]) == len(FIELDS[s]) for s in TIMING_SECTIONS))
        g = GuideWindow(app)
        g.top.withdraw()
        ok("guide window builds", True)
        t = GuideWindow(app, APP_TOUR.splitlines(), "How to use the app")
        t.top.withdraw()
        ok("app tour builds", True)
        t2 = GuideWindow(app, OPT_TUTORIAL.splitlines(), "Build optimiser - how to use it")
        t2.top.withdraw()
        ok("optimiser tutorial builds, with its picture", len(t2.images) == 1, "%d picture(s)" % len(t2.images))
        saved_opt = json.loads(json.dumps(app.cfg["optimiser"]))  # nothing here is saved to your settings
        for ps_ in bo.PLAYSTYLES:
            app.cfg["optimiser"]["playstyle"] = ps_
            app.refresh_optimiser()
        app.cfg["optimiser"]["perks"] = {"Warchief": 3, "Immortal": 5}
        app.refresh_optimiser()
        app.cfg["optimiser"] = saved_opt
        app.refresh_optimiser()
        ok("build optimiser page builds (every playstyle, scanned and not)", "Optimiser" in app.tabs)
        b_ = bo.best_build("Thunder Spear", *bo.ideal_owned())
        ok("build optimiser solves", [c[0] for c in b_.chosen if c] == ["Godforged", "Kengo", "Immortal", "Munitions Master"],
           ", ".join(c[0] for c in b_.chosen if c))
        ok("screen reading (Windows text recognition) available", bo.ocr_available(),
           "" if bo.ocr_available() else str(bo._OCR_IMPORT_ERROR or "no OCR language"))
        try:  # read a perk name off a picture, like the scan does
            pic = Image.new("RGB", (900, 220), (20, 20, 26))
            try:
                fnt = ImageFont.truetype("seguisb.ttf", 46)
            except Exception:
                fnt = ImageFont.load_default()
            ImageDraw.Draw(pic).text((40, 40), "AVATAR OF YMIR", font=fnt, fill=(235, 235, 235))
            ImageDraw.Draw(pic).text((40, 130), "+10", font=fnt, fill=(235, 235, 235))
            got = bo.read_perk_panel(bo.ocr_lines(cv2.cvtColor(np.array(pic), cv2.COLOR_RGB2BGR)))
            ok("screen reading reads a perk name and level", got == ("Avatar of Ymir", 10), str(got))
        except Exception as e:
            ok("screen reading reads a perk name and level", False, "%s: %s" % (type(e).__name__, e))
        ok("build page for every routine", set(ROUTINES) <= set(BUILDS) and all(
            os.path.isfile(resource_path("assets", "layouts", BUILDS[r]["layout"] + ".png")) for r in BUILDS))
        fw = FeedbackWindow(app)
        log = ["12:00:%02d  line %d" % (i % 60, i) for i in range(400)] + ["12:01:00  Settings folder: %s" % DATA_DIR]
        url, n = feedback_issue_url("Next mission not found\nafter retry", "tester", fw.info(), log)
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        ok("feedback window builds; GitHub link fits and hides the Windows name",
           url.startswith("https://github.com/%s/issues/new?" % FEEDBACK_REPO)
           and len(urllib.parse.quote(url, safe="")) <= FEEDBACK_URL_MAX
           and q["title"][0] == "Feedback: Next mission not found" and 0 < n < len(log)
           and "Settings folder: ~" in q["body"][0] and os.path.expanduser("~") not in q["body"][0],
           "%d chars, %d log lines" % (len(url), n))
        fw.top.destroy()
        url, body, headers = build_discord_request(dict(DEFAULT_DISCORD, mode="webhook", url="https://discord.com/api/webhooks/1/x"),
                                                   "hi", {"title": "t"}, b"\x89PNG", True)
        ok("discord message builds", url.endswith("/x") and b"payload_json" in body and "multipart" in headers["Content-Type"])
        fake = [{"t": time.time() - i * 400, "routine": "Blood Awakening", "seconds": 45.0, "result": "completed",
                 "loot": ["scroll"], "rescued": False} for i in range(20)]
        pics = [render_report(fake, "Blood Awakening", time.time(), {"start": time.time() - 900, "retries": 2}),
                render_report(fake, "Blood Awakening", time.time(), size=(578, 230), compact=True),
                render_report([], "Female Raid", time.time(), size=(300, 400), compact=True)]
        ok("stats graph draws", [p.size for p in pics] == [(960, 840), (578, 230), (300, 400)])
        det = Detector(app.cfg, lambda t: None)
        t0 = time.perf_counter()
        shot = det.grab()
        ms = (time.perf_counter() - t0) * 1000
        ok("screen capture", shot is not None, "%dx%d in %.0f ms" % (det.mon["width"], det.mon["height"], ms))
        if shot is not None:
            det.start_visible(False)
            det.start_visible(True)
            det.roi_find("start")
            det.find_retry(shot)
            det.find_grab(shot)
            for kind in LOOT_KINDS + ("completed", "failed", "shiki4", "finish", "heatwave"):
                det.find(kind, shot)
            ok("detection runs", True)
        det.close()
        app.root.destroy()
    except Exception:
        lines.append("FAIL exception:\n" + traceback.format_exc())
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    if not sys.platform.startswith("win"):
        print("Colossal Macro only runs on Windows.")
        return
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2])
        return
    App().run()


if __name__ == "__main__":
    main()
