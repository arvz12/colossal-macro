# Colossal Macro - v1.0 (beta)

Grind macro for **Attack on Titan Revolution** (Roblox), built for Colossal users. Windows app (one `.exe`, nothing to install).

**Download:** the exe is on the [Releases](../../releases) page. How to use it: [HOW TO USE.txt](HOW%20TO%20USE.txt) (also inside the app: Guide).

## What it does
- Routines: Blood Awakening (Colossal), Shiki, Universal (thunder spears), Female Raid.
- Smart waits: sees when you're shifted and when the shifted ability 4 has gone off, instead of fixed waits.
- Speed finder: tests shorter dash / strafe times and keeps only what is really faster.
- Reads the result and loot on every end screen; stats, run history, per-step times and an analytics page.
- Discord webhook / bot (messages, stats graph, remote commands), auto-reconnect, session limits.
- Works fullscreen or windowed; themes and accent colour.

## Build it yourself
Needs Python 3 on Windows:

```
python -m pip install pyinstaller opencv-python numpy pillow
build.bat
```

The exe ends up in `dist\`.

## Note
The macro only presses keys and clicks; it doesn't touch game files. Macros may still be against a game's rules - use it at your own risk.
