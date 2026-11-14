English | [简体中文](https://github.com/GallantTarry/pykuai/blob/main/README.zh-CN.md)

# 🐍 PyKuai (v1.2.8) — Open-Source CS & Developer Script Toolbox(may be console)

> **An open-source, modular CLI & TUI script toolbox built for Computer Science workflows, developer utilities, and community sharing.**  
> *"The Lord is my shepherd."* — Author: **TuKuai** ([GallantTarry](https://github.com/GallantTarry))

---

## 🌟 Overview & Design Philosophy

**PyKuai** *(from Chinese "Kuai", meaning fast)* is an open-source **micro-kernel + drop-in 3-letter plugin toolbox** built for Computer Science students, engineers, and Python developers. Rather than leaving handy automation scripts buried in scattered local folders, PyKuai gives them a unified terminal runtime so anyone can install and use them out of the box—or drop in standard three-letter `.py` engines to share with the community:

* **Zero-Config Micro-Kernel**: Drop any compliant three-letter lowercase `.py` module (`^[a-z]{3}$`) implementing [`BaseEngine`](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/base.py) into `pykuai/engines/`. PyKuai automatically discovers it and wires it into the Tool Tray (`tt`), CLI subcommand router, and dependency scanner (`pp`) with zero boilerplate.
* **Two-Tier Command Ergonomics**:
  * **Doubled 2-letter global commands** (`tt`, `pp`, `xp`, `cc`) plus `help` / `gg` deliver instant muscle-memory navigation across the REPL console.
  * **3-letter tool engines** (`ifc`, `ytd`, ...) keep every utility isolated behind clean, collision-free namespaces.
* **Dual-Mode Execution & In-App Guides**: Run every engine either interactively through mouse-clickable **Rich / Textual** Cyber-Dark Studios (press `?` or `F1`, or click `?` in the top-right corner, for a full in-app feature guide) or headlessly via direct CLI flags in automation scripts.
* **Cyber-Dark Tactile Experience**: Features an ASCII banner, an optional high-DPI desktop pixel-snake launch sequence (`--fast` to skip), Windows Terminal title/icon protection, drag-and-drop image routing, and toggleable retro CC0 arcade sound effects persisted in `~/.pykuai/settings.json`.

---

## 📁 Repository Architecture

```text
pykuai/
├── .github/
│   └── workflows/
│       └── publish.yml         # GitHub Actions Trusted Publishing workflow for PyPI
├── pyproject.toml              # Package metadata, optional extras & pykuai CLI entrypoint
├── README.md                   # English documentation (GitHub homepage & PyPI)
├── README.zh-CN.md             # Chinese documentation (简体中文详细说明文档)
├── .gitignore                  # Git ignore rules (caches, builds, heavy binaries & temp outputs)
├── .backup_engines/            # Historical archive of 10 pre-refactor scripts (not loaded at runtime)
└── pykuai/                     # Core Python package
    ├── __init__.py             # Version (1.2.8) & author metadata
    ├── __main__.py             # python -m pykuai module entrypoint
    ├── cli.py                  # Main dispatcher (interactive REPL & direct CLI modes)
    ├── core/                   # Micro-kernel infrastructure
    │   ├── __init__.py         # Core package marker
    │   ├── audio.py            # Non-blocking CC0 retro SFX player & persistent settings
    │   ├── base.py             # Abstract BaseEngine plugin contract
    │   ├── deps.py             # Dependency scanner & visual/CLI installer (pp)
    │   ├── intro.py            # High-DPI pixel-snake desktop launch intro (snake.wav)
    │   ├── registry.py         # Auto-discovery registry for 3-letter engine modules
    │   ├── tools.py            # Binary toolchain resolver & verified Windows FFmpeg installer
    │   ├── tray.py             # Interactive Tool Tray & subcommand dispatcher (tt)
    │   ├── tui.py              # Textual Cyber-Dark widgets, help modal (?/F1) & SFX hooks
    │   ├── ui.py               # Rich Cyber-Dark theme, ASCII banner, greeting & console hooks
    │   ├── watchdog.py         # Windows Terminal settings.json guard & exit cleanup
    │   └── yt_auth.py          # Isolated Chromium YouTube sign-in helper -> ~/.pykuai/cookies.txt
    ├── engines/                # Plug-and-play 3-letter tool engines
    │   ├── __init__.py         # Engines package marker
    │   ├── ifc.py              # ifc: Image Format Converter & multi-resolution ICO packer
    │   └── ytd.py              # ytd: YouTube & media downloader (yt-dlp + FFmpeg)
    ├── assets/                 # Visual & audio assets
    │   ├── icon.ico            # High-DPI multi-resolution application icon
    │   └── sfx/                # Retro CC0 sound effects
    │       ├── click.wav       # Button click SFX
    │       ├── enter.wav       # Command / dialog submit SFX
    │       ├── key.wav         # Keyboard typing & backspace SFX
    │       ├── paste.wav       # Clipboard paste & file drop SFX
    │       ├── snake.wav       # Launch pixel-snake hiss SFX
    │       └── type.wav        # Pixel-telegraph greeting SFX
    └── tools/                  # Lightweight portable Windows binaries & pixel font
        ├── yt-dlp.exe          # Standalone stream extractor binary (2026.10.26)
        ├── UnRAR.exe           # RAR extraction utility (7.30 beta 2)
        └── zpix.ttf            # Recommended pixel-style terminal font
                                # (ffmpeg/ffprobe resolved from PATH or auto-installed to ~/.pykuai/tools/)
```

### Module Breakdown

1. **Root Configuration, CI & Archive**
   * **[pyproject.toml](https://github.com/GallantTarry/pykuai/blob/main/pyproject.toml)**: Defines package metadata (`1.2.8`, Python `>=3.9`), core dependencies (`rich`, `textual`, `openpyxl`, `Pillow`, `pypdf`), optional extras (`office`, `media`, `cv`, `archive`, `ui`, `all`), package data (`tools/*`, `assets/*`, `assets/sfx/*`), and the `pykuai` console entrypoint.
   * **[.github/workflows/publish.yml](https://github.com/GallantTarry/pykuai/blob/main/.github/workflows/publish.yml)**: Passwordless PyPI Trusted Publishing pipeline (OIDC) triggered on `v*` / `pykuaiv*` tags or manual `workflow_dispatch`.
   * **[.backup_engines/](https://github.com/GallantTarry/pykuai/tree/main/.backup_engines)**: Reference archive of 10 pre-refactor standalone scripts (`archive.py`, `excel_merge.py`, `excel_split.py`, `img_compress.py`, `media_fetch.py`, `office_fixed.py`, `pdf_split.py`, `scanner.py`, `video_compress.py`, `web_sniffer.py`). Never loaded by `registry.py`.

2. **Micro-Kernel (`pykuai/core/`)**
   * **[cli.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/cli.py)** & **[tray.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/tray.py)**: Routes bare `pykuai` launches into the interactive REPL (with live keystroke, cursor, history, clipboard paste burst SFX, and automatic drag-and-drop image launch for `ifc`), or routes `pykuai tt <tool> [args]` directly to the target engine. `tt` includes a `?`/`F1` guide modal and bottom-right `🔊 SFX ON / 🔇 SFX OFF` toggle.
   * **[base.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/base.py)** & **[registry.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/registry.py)**: Defines the `BaseEngine` interface (including `help_text` and `launch_with_path`) and automatically registers valid 3-letter `.py` plugins under `pykuai/engines/`.
   * **[tui.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/tui.py)**, **[ui.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/ui.py)** & **[audio.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/audio.py)**: Provides the Cyber-Dark Rich theme, pixel-telegraph greeting, reusable Textual widgets (`PyKuaiStudioApp`, `StudioHeader`, `HelpChip`, `HelpModalScreen`, `ToggleChip`, `ActionChip`, `SfxToggleChip`, `pick_multi`, `pick_one`), non-blocking CC0 WAV SFX playback, and persistent `~/.pykuai/settings.json`.
   * **[deps.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/deps.py)**: Powers `pp`, auditing declared engine `requires` and AST imports against the active Python environment with clickable selection or CLI `--check` / `-y` / `--all` / `-U` modes.
   * **[tools.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/tools.py)** & **[yt_auth.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/yt_auth.py)**: Resolves external tools (`ffmpeg`, `ffprobe`, `yt-dlp`, `UnRAR`, Node/Deno JS runtimes) across bundled `tools/`, system `PATH`, and `~/.pykuai/tools/`, downloads & SHA256-verifies Windows `FFmpeg`/`FFprobe` essentials on demand (`urllib` + `curl`/direct fallback), and drives the extension-free isolated browser YouTube login flow (`~/.pykuai/yt-session` → `~/.pykuai/cookies.txt`).
   * **[intro.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/intro.py)** & **[watchdog.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/watchdog.py)**: Plays the high-DPI desktop pixel-snake launch animation (`snake.wav`) and safely restores Windows Terminal title/icon state on exit.

3. **Built-In Engines (`pykuai/engines/`)**
   * **[ifc.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/engines/ifc.py)** (`ifc` — *Image Format Converter*)
   * **[ytd.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/engines/ytd.py)** (`ytd` — *YouTube Download*)

---

## 🧰 Built-In Engines & Key Features

### 1. `ifc` — Image Format Converter
* **Formats**: Exports to `ICO`, `PNG`, `JPG`, `WEBP`, `BMP`, `GIF`, `TIFF`, and `AVIF`; reads broader sources including `JPEG`, `TIF`, `ICNS`, `TGA`, `PPM`, `DDS`, and `PSD`.
* **Smart Image Pipeline**: Automatically normalizes EXIF orientation, extracts the highest-resolution layer from `ICO`/`ICNS` or first frame of animated images, flattens transparent pixels onto solid white when targeting `JPG`/`BMP`, and performs atomic temp-file writes to prevent half-written files or accidental self-overwrite.
* **Multi-Resolution `.ico` Packaging**: Toggle any combination of sizes from `8` to `256` px (`Std`, `All`, `Web` presets), pads non-square images cleanly onto a transparent square canvas, and applies subtle `UnsharpMask` sharpening on tiny layers (`<= 32px`, toggleable or `--no-sharpen`).
* **Lossy Quality Control**: Studio chips (`80%` / `90%` / `92%` / `95%` / `100%`) or CLI `-q 1..100` (default `92`) for `JPG`, `WEBP`, and `AVIF`.

### 2. `ytd` — YouTube & Media Downloader
* **Profiles & Aliases**: `best` (Auto-muxed MP4), `1080p`, `720p`, `mp3` (`--audio-quality 0`), and `m4a` (CLI aliases: `video`/`mp4` → `best`, `audio` → `mp3`).
* **Scope, Subtitles & Probing**: Switch cleanly between `Single` (`--no-playlist`, even with `&list=`) and `Playlist` (`--yes-playlist`), download & embed English/Chinese captions (`--subs`), or inspect all available streams without downloading (`-F` / `Formats`).
* **Extension-Free `Login YouTube` (`--login`)**: Windows Chrome/Edge (`127+`) locks its cookie DB (`yt-dlp #7271`) and enforces App-Bound Encryption (`#10927`). Click **`Login YouTube`** in Studio (or run `pykuai tt ytd --login`) to sign in inside an isolated browser profile (`~/.pykuai/yt-session`)—PyKuai captures the authenticated session automatically into `~/.pykuai/cookies.txt` without touching your personal browser or needing third-party extensions. Interactive downloads hitting YouTube's sign-in gate also offer to open this login flow and retry immediately.
* **Smart Resilience & On-Demand FFmpeg**: Automatically wires `ejs:github` challenge solving when Node/Deno is installed, prefers bundled `yt-dlp.exe` when Python `yt-dlp` lacks `curl_cffi`, auto-detects `cookies.txt` across save/working dirs, `~/.pykuai/cookies.txt`, and `~/Downloads`, and prompts to install SHA256-verified Windows FFmpeg/FFprobe binaries into `~/.pykuai/tools/` (`--install-ffmpeg`) whenever missing.

---

## 🚀 Dual-Mode Usage & Global Commands

### 1. Interactive Console Mode (REPL)

Launch the workbench from any terminal:

```bash
pykuai
# Skip the pixel-snake launch intro (also supports --no-intro or -f):
pykuai --fast
```

Inside the console, use the core commands (`help` prints the table, `gg` quits, and the banner's right-side `🔊 SFX ON / 🔇 SFX OFF` pill toggles global audio on click):

| Command | Meaning | Description |
| :--- | :--- | :--- |
| `tt` | **Tool Tray** | Open the interactive Tool Tray, or run `tt <tool> [args]` |
| `pp` | **Pull Packages** | Audit and install/upgrade plugin dependencies (`pp --check` / `pp -y` / `pp -U`) |
| `xp` | **XP Playground** | Launch the 3D cutscene & virtual Windows XP CRT playground (`HEX 3D`) |
| `cc` | **Clear Console** | Clear the screen and redraw the Cyber-Dark banner |

> 💡 **Pro Tip**: Dragging or pasting an image file path straight into the REPL prompt automatically opens `ifc` pre-loaded with that image.

### 2. Direct CLI Mode

Run tools headlessly or script them in pipelines without entering the REPL:

```bash
# Open interactive Tool Tray (prints a summary table when piped/non-TTY)
pykuai tt

# Image format conversion & multi-layer .ico generation (ifc)
pykuai tt ifc logo.png -t webp -q 90
pykuai tt ifc logo.png -t ico -s 16,32,48,256 -o app.ico

# YouTube & media download, stream probing, login & FFmpeg setup (ytd)
pykuai tt ytd "https://www.youtube.com/watch?v=..." -f best
pykuai tt ytd "https://www.youtube.com/watch?v=..." -f mp3 --subs -o ./music
pykuai tt ytd "https://www.youtube.com/watch?v=..." -F
pykuai tt ytd --login
pykuai tt ytd --install-ffmpeg

# Audit, install, or upgrade dependencies (pp)
pykuai pp --check
pykuai pp -y
pykuai pp -y --all -U

# Help & version
pykuai help
pykuai xp
pykuai --version
```

---

## 🛠️ Installation & Development Setup

Install directly from PyPI or in editable mode from source:

```bash
# Core workbench from PyPI
pip install pykuai

# With optional media download tools or full extras
pip install "pykuai[media]"
pip install "pykuai[all]"

# Local editable install for development
git clone https://github.com/GallantTarry/pykuai.git
cd pykuai
pip install -e .
pip install -e ".[all]"
```

Once installed, launch from anywhere using `pykuai` or `python -m pykuai`.

> **Note on External Binaries**: Git and PyPI distributions stay lightweight (~30 MiB) by bundling `yt-dlp.exe`, `UnRAR.exe`, and `zpix.ttf` without heavy FFmpeg binaries. On Windows, if `ffmpeg` / `ffprobe` are not already on `PATH` or in `~/.pykuai/tools/`, `ytd` automatically prompts to download and SHA256-verify official FFmpeg essentials into `~/.pykuai/tools/` (or run `pykuai tt ytd --install-ffmpeg`).

---

## 🧩 Extending PyKuai (3-Letter Plugin Contract)

Create a `.py` file named with **three lowercase letters** (e.g. `pykuai/engines/pdf.py`) subclassing [`BaseEngine`](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/base.py):

```python
# -*- coding: utf-8 -*-
import argparse
from rich.console import Console
from pykuai.core.base import BaseEngine


class MyToolEngine(BaseEngine):
    name = "pdf"
    description = "Merge or split PDF documents"
    usage = "tt pdf | tt pdf <files> [-o output]"
    category = "Document"
    requires = ["pypdf>=3.0.0"]
    help_text = "Click Merge or Split in interactive mode, or pass PDF files via CLI."

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("files", nargs="*", help="Input PDF file paths")
        parser.add_argument("-o", "--output", default="merged.pdf", help="Output file path")

    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        if not args.files:
            return self.run_interactive(console)
        console.print(f"[#00FF00]Processing {len(args.files)} file(s)...[/#00FF00]")
        return 0

    def run_interactive(self, console: Console) -> int:
        from pykuai.core.tui import pick_one
        mode = pick_one("Select PDF Action", [("Merge PDFs", "merge"), ("Split PDF", "split")])
        if mode:
            console.print(f"[#00FF00]Selected mode: {mode}[/#00FF00]")
        return 0
```

Restart `pykuai`—no core edits or manual registration needed. `pdf` appears immediately in `tt`, and `pp` automatically tracks its `requires` packages and imports.

---

## ✨ What's New in v1.2.8

* **XP Playground (`xp`)**: Redesigned the arcade experience as `xp`, featuring a 3D bedroom-to-PC intro leading into a minimalist Windows XP Bliss desktop with `HEX 3D` and a focused `START` -> `OFF` shutdown menu.
* **Home Banner & Clickable Global `SFX` Toggle**: Placed author/version details alongside the `PYKUAI` banner, added a mouse-clickable `SFX ON` / `SFX OFF` sound toggle, and simplified REPL navigation to `xp`, `help`, and `gg`.
* **Visual & Input Fixes**: Eliminated unwanted blue click-selection stripes in the `xp` desktop view and trimmed extra chrome bars.

---

## ✨ What's New in v1.2.7

* **Built-In `Login YouTube` (`--login`)**: Added [`yt_auth.py`](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/yt_auth.py) and `Login YouTube` in `YtdStudioApp`, enabling zero-extension sign-in via an isolated Chromium profile (`~/.pykuai/yt-session`) that saves `~/.pykuai/cookies.txt` and retries YouTube bot-check blocks interactively.
* **Lean Distribution & Auto FFmpeg Installer (`--install-ffmpeg`)**: Removed ~200 MiB `ffmpeg.exe` / `ffprobe.exe` binaries from Git/PyPI packages while adding SHA256-verified on-demand installation into `~/.pykuai/tools/` with proxy/curl fallbacks.
* **Universal Studio Feature Guides (`?` / `F1`)**: Added clickable top-right `?` help buttons and `HelpModalScreen` documentation dialogs across `tt`, `pp`, `ifc`, and `ytd`.
* **Reliability & Toolchain Upgrades**: Updated bundled `yt-dlp.exe` (`2026.10.26`) and `UnRAR.exe` (`7.30 beta 2`), preferred bundled `yt-dlp.exe` when Python `yt-dlp` lacks `curl_cffi`, improved responsive narrow-terminal Studio layouts and URL/path sanitization, and added Windows Chromium lock fallback.

---

## 🙏 Open-Source Credits & Assets

* **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — Stream extraction engine powering `pykuai tt ytd`
* **[FFmpeg](https://ffmpeg.org/)** — Media muxing and MP3/M4A audio transcoding
* **[Pillow](https://python-pillow.org/)** — Multi-format image processing powering `pykuai tt ifc`
* **[Textual](https://textual.textualize.io/)** & **[Rich](https://github.com/Textualize/rich)** — Cyber-Dark interactive TUI widgets and console rendering
* **[Kenney Audio](https://kenney.nl/)** & **[CC0 Public Domain Sounds](https://github.com/lavenderdotpet/CC0-Public-Domain-Sounds)** — Retro CC0 UI click, key, enter, paste, telegraph, and pixel-snake sound effects
