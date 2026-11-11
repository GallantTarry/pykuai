English | [简体中文](https://github.com/GallantTarry/pykuai/blob/main/README.zh-CN.md)

# 🐍 PyKuai — Open-Source CS & Developer Script Toolbox

> **An open-source, modular CLI & TUI script toolbox built for Computer Science workflows, developer utilities, and community sharing.**  
> *"The Lord is my shepherd."* — Author: **TuKuai** ([GallantTarry](https://github.com/GallantTarry))

---

## 🌟 Overview & Design Philosophy

**PyKuai** *(from Chinese "Kuai", meaning fast)* is an open-source **micro-kernel + drop-in 3-letter plugin toolbox** built for Computer Science students, engineers, and Python developers. Rather than leaving handy automation scripts buried in scattered local folders, PyKuai gives them a clean, shareable terminal runtime—so anyone can install it out of the box or drop in standard three-letter `.py` engines to help others solve everyday media, asset, and workflow tasks:

* **Zero-Config Micro-Kernel**: Drop any compliant three-letter lowercase `.py` module (`^[a-z]{3}$`) implementing `BaseEngine` into `pykuai/engines/`. PyKuai automatically discovers it and wires it into the interactive tool tray (`tt`), CLI subcommand router, and dependency scanner (`pp`) with zero boilerplate.
* **Two-Tier Command Ergonomics**:
  * **Doubled 2-letter global commands** (`tt`, `pp`, `vv`, `cc`, `hh`, `gg`) deliver instant muscle-memory navigation across the REPL console.
  * **3-letter tool engines** (`ifc`, `ytd`, ...) isolate every tool behind clean, conflict-free namespaces.
* **Dual-Mode Execution**: Run every engine either interactively through mouse-clickable **Rich / Textual** terminal panels or headlessly from direct CLI flags in automation scripts.
* **Cyber-Dark Tactile Experience**: Features an ASCII banner, an optional desktop pixel-snake launch sequence (`--fast` to skip), Windows Terminal visual integration, drag-and-drop image detection, and toggleable retro CC0 arcade sound effects.

---

## 📁 Repository Architecture

```text
pykuai/
├── .github/
│   └── workflows/
│       └── publish.yml         # GitHub Actions Trusted Publishing workflow for PyPI
├── pyproject.toml              # Package metadata, optional extras & pykuai CLI entrypoint
├── README.md                   # English documentation (GitHub homepage & PyPI)
├── README.zh-CN.md             # Chinese documentation (简体中文说明文档)
├── .gitignore                  # Git ignore rules (caches, builds, IDE configs & temp outputs)
├── .backup_engines/            # Legacy standalone reference scripts (not loaded at runtime)
└── pykuai/                     # Core Python package
    ├── __init__.py             # Version & author metadata
    ├── __main__.py             # python -m pykuai module entrypoint
    ├── cli.py                  # Main dispatcher (interactive REPL & direct CLI modes)
    ├── core/                   # Micro-kernel infrastructure
    │   ├── audio.py            # Non-blocking CC0 retro SFX player & persistent settings
    │   ├── base.py             # Abstract BaseEngine plugin contract
    │   ├── deps.py             # Dependency scanner & visual/CLI installer (pp)
    │   ├── intro.py            # High-DPI pixel-snake desktop launch intro (snake.wav)
    │   ├── registry.py         # Auto-discovery registry for 3-letter engine modules
    │   ├── tools.py            # Binary toolchain resolver (bundled tools/, PATH, ~/.pykuai)
    │   ├── tray.py             # Interactive Tool Tray & engine subcommand dispatcher (tt)
    │   ├── tui.py              # Textual Cyber-Dark widgets & global SFX input/click hooks
    │   ├── ui.py               # Rich Cyber-Dark theme, ASCII banner, greeting & console hooks
    │   └── watchdog.py         # Windows Terminal settings.json guard & exit cleanup
    ├── engines/                # Plug-and-play 3-letter tool engines
    │   ├── ifc.py              # ifc: Image Format Converter & multi-size ICO packer
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
    └── tools/                  # Local portable Windows binaries & pixel font
        ├── ffmpeg.exe          # Audio/video muxing & transcoding
        ├── ffprobe.exe         # Media stream analyzer
        ├── yt-dlp.exe          # Standalone stream extractor binary
        ├── UnRAR.exe           # RAR extraction utility
        └── zpix.ttf            # Recommended pixel-style terminal font
```

### Module Breakdown

1. **Root Configuration, CI & Archive**
   * **[pyproject.toml](https://github.com/GallantTarry/pykuai/blob/main/pyproject.toml)**: Defines package metadata (`>=3.9`), core dependencies (`rich`, `textual`, `openpyxl`, `Pillow`, `pypdf`), optional extras (`office`, `media`, `cv`, `archive`, `ui`, `all`), and the `pykuai` console script entrypoint.
   * **[.github/workflows/publish.yml](https://github.com/GallantTarry/pykuai/blob/main/.github/workflows/publish.yml)**: Passwordless PyPI Trusted Publishing pipeline triggered on `v*` / `pykuaiv*` tags or `workflow_dispatch`.
   * **[.backup_engines/](https://github.com/GallantTarry/pykuai/tree/main/.backup_engines)**: Historical archive of 10 pre-refactor scripts kept for reference only (`registry.py` does not load them).

2. **Micro-Kernel (`pykuai/core/`)**
   * **[cli.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/cli.py)** & **[tray.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/tray.py)**: Routes bare `pykuai` launches into the interactive REPL (with live keystroke/paste burst SFX and drag-and-drop image handling for `ifc`), or routes `pykuai tt <tool> [args]` directly to the target engine. `tt` also hosts the bottom-right global `SFX ON / OFF` toggle.
   * **[base.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/base.py)** & **[registry.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/registry.py)**: Defines the `BaseEngine` interface and automatically scans `pykuai/engines/` for lowercase 3-letter `.py` plugins.
   * **[tui.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/tui.py)**, **[ui.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/ui.py)** & **[audio.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/audio.py)**: Provides the Cyber-Dark Rich theme, pixel-telegraph greeting, reusable Textual chips/dialogs (`PyKuaiStudioApp`, `ToggleChip`, `ActionChip`, `SfxToggleChip`), non-blocking WAV SFX hooks, and persistent `~/.pykuai/settings.json` state.
   * **[deps.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/deps.py)** & **[tools.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/tools.py)**: Scans engine requirements (`pp`) against the active Python environment and resolves external binaries (`ffmpeg`, `ffprobe`, `yt-dlp`, `UnRAR`) across bundled `tools/`, system `PATH`, and `~/.pykuai/tools/`.
   * **[intro.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/intro.py)** & **[watchdog.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/core/watchdog.py)**: Drives the pixel-snake intro animation and cleanly restores Windows Terminal title/icon metadata on exit.

3. **Built-In Engines (`pykuai/engines/`)**
   * **[ifc.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/engines/ifc.py)** (`ifc` — *Image Format Converter*): Multi-format converter (`PNG`, `JPG`, `WEBP`, `BMP`, `GIF`, `TIFF`, `AVIF`, `ICO`) powered by `Pillow`, with an interactive format/layer picker (`IfcStudioApp`) and multi-resolution `.ico` sharpening.
   * **[ytd.py](https://github.com/GallantTarry/pykuai/blob/main/pykuai/engines/ytd.py)** (`ytd` — *YouTube Download*): Media & stream downloader powered by `yt-dlp` and `FFmpeg`, supporting YouTube (with EJS challenge/JS runtime resolution), Bilibili, X/Twitter, best-quality MP4 muxing, and MP3/M4A extraction (`YtdStudioApp`).

---

## 🚀 Dual-Mode Usage & Global Commands

### 1. Interactive Console Mode (REPL)

Launch the workbench from any terminal:

```bash
pykuai
# Skip the pixel-snake launch intro:
pykuai --fast
```

Inside the console, use the **6 doubled-letter global commands**:

| Command | Meaning | Description |
| :--- | :--- | :--- |
| `tt` | **Tool Tray** | Open the interactive Tool Tray (with bottom-right SFX toggle), or run `tt <tool> [args]` |
| `pp` | **Pull Packages** | Inspect and install missing plugin dependencies (`pp --check` / `pp -y`) |
| `vv` | **View Version** | Display version, author signature, and open-source credits |
| `cc` | **Clear Console** | Clear the screen and redraw the Cyber-Dark banner |
| `hh` | **Help Hub** | Show the global command quick-reference table |
| `gg` | **Good Game** | Exit cleanly and restore the original terminal title and icon |

> 💡 **Pro Tip**: Dragging or pasting an image path directly into the REPL prompt automatically opens `ifc` for quick conversion.

### 2. Direct CLI Mode

Run tools headlessly or script them in pipelines without starting the REPL:

```bash
# Open the interactive Tool Tray (prints a clean table in non-TTY pipes)
pykuai tt

# Convert images or build multi-resolution .ico files (ifc)
pykuai tt ifc logo.png -t webp
pykuai tt ifc logo.png -t ico -s 16,32,48,256 -o app.ico

# Download video or extract audio (ytd)
pykuai tt ytd "https://www.youtube.com/watch?v=..." -f best
pykuai tt ytd "https://www.youtube.com/watch?v=..." -f mp3 -o ./music

# Audit or install dependencies (pp)
pykuai pp --check
pykuai pp -y

# Help & version
pykuai hh
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

> Note on external binaries: PyPI packages remain lightweight and pure-Python plus static SFX/icon assets. `ytd` works out of the box once `ffmpeg` / `yt-dlp` are available on your system `PATH` or inside `~/.pykuai/tools/`.

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

Restart `pykuai`—no core edits or manual registration needed. `pdf` appears immediately in `tt`, and `pp` automatically tracks its `requires` packages.

---

## 🙏 Open-Source Credits & Assets

* **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — Stream extraction engine powering `pykuai tt ytd`
* **[FFmpeg](https://ffmpeg.org/)** — Media muxing and MP3/M4A audio transcoding
* **[Pillow](https://python-pillow.org/)** — Multi-format image processing powering `pykuai tt ifc`
* **[Textual](https://textual.textualize.io/)** & **[Rich](https://github.com/Textualize/rich)** — Cyber-Dark interactive TUI widgets and console rendering
* **[Kenney Audio](https://kenney.nl/)** & **[CC0 Public Domain Sounds](https://github.com/lavenderdotpet/CC0-Public-Domain-Sounds)** — Retro CC0 UI click, key, enter, paste, telegraph, and pixel-snake sound effects
