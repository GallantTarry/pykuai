# 🐍 PyKuai (Cyber Script Workbench)

> **Modular Cyber-Dark CLI Script Workbench & Plug-in Automation Toolkit**  
> *"The Lord is my shepherd."* — Author: **TuKuai** | Username: **GallantTarry**

---

## 🌟 Core Philosophy & Architecture

`pykuai` is a minimalist, high-extensibility CLI script workbench powered by `rich`. Built on a microkernel + plug-in engine architecture, it lets you add new command-line utilities simply by dropping a Python module into `pykuai/engines/`—no boilerplate registration or GUI clutter required.

```text
pykuai/
├── pyproject.toml              # Package metadata & global CLI entrypoint (pykuai)
├── pykuai/
│   ├── cli.py                  # Master console: Interactive REPL vs Direct CLI execution
│   ├── core/
│   │   ├── base.py             # BaseEngine contract (name, description, usage, requires, args, direct, interactive)
│   │   ├── deps.py             # Global Pull Packages (`pp`) dependency scanner & installer
│   │   ├── registry.py         # Dynamic engine auto-discovery & registration
│   │   ├── tray.py             # Visual Tool Tray (`tt`) launcher & subcommand dispatcher
│   │   ├── intro.py            # High-DPI desktop pixel snake intro animation
│   │   ├── ui.py               # Cyber-dark Rich theme, banner, progress bars & identity hooks
│   │   ├── tui.py              # Mouse-clickable interactive terminal UI widgets (Textual)
│   │   ├── watchdog.py         # Background Windows Terminal settings.json lifecycle guard
│   │   └── tools.py            # Bundled & system binary locator (FFmpeg, UnRAR, yt-dlp)
│   ├── engines/                # Plug-and-play script engines
│   │   ├── ico_maker.py        # ico: PNG to multi-resolution Windows ICO container
│   │   └── media_fetch.py      # media: Video & audio downloader (powered by yt-dlp & FFmpeg)
│   └── assets/                 # Multi-res High-DPI icon assets
```

---

## 🚀 Dual-Mode Execution

### 1. Interactive Console Mode (`pykuai`)
Run `pykuai` in any terminal to enter the Cyber-Dark REPL console:

```bash
pykuai
# Skip intro animation:
pykuai --fast
```

Built-in console commands (strictly 1-to-1 unique):
* `tt` — Tool Tray (browse & launch script tools visually, or run `tt <tool> [args]`)
* `hh` — Help Hub (show global commands and syntax)
* `cc` — Clear console and refresh banner
* `pp` — Pull Packages (inspect and install global dependencies visually)
* `gg` — Exit safely (automatically restores terminal title & icon)
* Drag and drop an image file directly into the console to invoke the `ico` engine automatically

### 2. Direct CLI Mode (`pykuai <command>`)
Execute tools directly from the shell without entering the REPL—ideal for scripts and pipelines:

```bash
# Open interactive Tool Tray (or list tools when piped)
pykuai tt

# Convert a PNG to a multi-resolution Windows .ico file
pykuai tt ico logo.png

# Specify custom layer sizes and output path
pykuai tt ico logo.png -s 16,32,48,256 -o app.ico

# Download video (MP4) or extract MP3 audio via yt-dlp & FFmpeg
pykuai tt media "https://www.youtube.com/watch?v=..." -f best
pykuai tt media "https://www.youtube.com/watch?v=..." -f mp3 -o ./music

# Inspect or install global script dependencies
pykuai pp --check
pykuai pp -y

# Show CLI help or version
pykuai hh
pykuai --version
```

---

## 🛠️ Installation & Local Development

Install in editable mode from the repository root:

```bash
pip install -e .
```

Once installed, the `pykuai` command is available globally from any terminal directory.

---

## 🧩 Writing New Script Engines (Plug-and-Play)

Create a new `.py` file inside `pykuai/engines/` (for example, `doc_pdf.py`) and subclass `BaseEngine`:

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

Save the file and launch `pykuai`. Auto-discovery picks it up immediately inside Tool Tray (`tt`), and `pp` detects its `requires` / imports automatically without modifying any core files.

---

## 🙏 Third-Party Tools & Attribution

* **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — Stream extraction engine powering `pykuai tt media`
* **[FFmpeg](https://ffmpeg.org/)** — Video/audio muxing and MP3/M4A transcoding engine
* **[Textual](https://textual.textualize.io/)** & **[Rich](https://github.com/Textualize/rich)** — Cyber-Dark interactive TUI framework
