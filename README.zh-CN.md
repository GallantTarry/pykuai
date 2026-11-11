[English](https://github.com/GallantTarry/pykuai/blob/main/README.md) | 简体中文

# 🐍 PyKuai — 面向计算机专业的开源脚本工具箱

> **开源、模块化的 Python CLI / TUI 脚本工具箱——让实用开发者脚本开箱即用、共享互通**  
> *"The Lord is my shepherd."* — Author: **TuKuai** | Username: **GallantTarry**

---

## 🌟 核心定位与设计哲学

`pykuai`（取意自中文「快」）是一个面向**计算机专业学习者与开发者社区**的开源 **「微内核 + 即插即用三字母引擎」脚本工具箱**。与其让好用的 Python 小工具各自散落在本地文件夹里无人知晓，不如通过统一约定把它们变成开箱即用、人人都能安装复用的终端工具集，同时也支持轻松扩展与分享新插件：

* **大道至简，双层指令**：全局控制台指令统一采用**两位叠字小写字母**（`tt`、`pp`、`vv`、`cc`、`hh`、`gg`），所有功能插件统一采用**三位纯英文小写缩写**（如 `ifc`、`ytd`），兼顾输入速度与零重名冲突。
* **即放即用，免去繁琐注册**：在 `pykuai/engines/` 放入符合规范的三字母 `.py` 插件即可被内核自动识别并接入工具托盘（`tt`）、CLI 参数路由与依赖检查（`pp`）。
* **交互与直调双模式并行**：既能在终端内体验鼠标可点击的 Rich / Textual 赛博交互界面与复古 CC0 像素音效，也能直接在 Shell / 自动化流水线里传参静默执行。
* **界面英语化，开源回馈社区**：软件运行时界面、命令与交互文案保持简洁英文，便于与上游开源生态对齐并面向全球分享。

---

## 📁 目录结构与各板块作用说明

```text
pykuai/
├── .github/
│   └── workflows/
│       └── publish.yml         # GitHub Actions Trusted Publishing 自动构建与发布 PyPI 流水线
├── pyproject.toml              # 打包配置、依赖分组与全局 pykuai 命令入口
├── README.md                   # 项目英文主说明文档（用于 GitHub 首页与 PyPI 展示）
├── README.zh-CN.md             # 本项目中文详细说明文档
├── .gitignore                  # Git 忽略规则（缓存、构建产物、IDE 配置与临时输出）
├── .backup_engines/            # 历史旧版脚本归档目录（运行时不加载）
└── pykuai/                     # 核心 Python 包目录
    ├── __init__.py             # 包版本与作者元信息
    ├── __main__.py             # python -m pykuai 模块化启动入口
    ├── cli.py                  # 主控制台调度器（REPL 交互 / CLI 直达）
    ├── core/                   # 微内核基础设施板块
    │   ├── audio.py            # 复古 CC0 音效管理与开关持久化（~/.pykuai/settings.json）
    │   ├── base.py             # 插件契约基类 BaseEngine
    │   ├── deps.py             # 全局依赖检测与安装管理器（pp）
    │   ├── intro.py            # 高 DPI 桌面像素贪吃蛇开场动画（同步播放 snake.wav）
    │   ├── registry.py         # 三字母引擎自动扫描与注册器
    │   ├── tools.py            # 本地内置与系统工具链定位器
    │   ├── tray.py             # 交互式工具托盘与子命令分发器（tt）
    │   ├── tui.py              # Textual 赛博交互组件库与全局键鼠/粘贴/回车音效钩子
    │   ├── ui.py               # Rich 暗黑主题、极简 Banner、像素电报引导语及窗口标识钩子
    │   └── watchdog.py         # Windows Terminal settings.json 守护与退出清理进程
    ├── engines/                # 即插即用三字母功能引擎板块
    │   ├── ifc.py              # ifc: Image Format Converter（多格式图像转换与 ICO 打包）
    │   └── ytd.py              # ytd: YouTube Download（流媒体与音视频下载提取）
    ├── assets/                 # 视觉与音效静态资源板块
    │   ├── icon.ico            # 高 DPI 多尺寸应用图标
    │   └── sfx/                # 复古 CC0 音效资源子目录
    │       ├── click.wav       # 鼠标按钮点击音效
    │       ├── enter.wav       # 回车确认执行音效
    │       ├── key.wav         # 键盘打字与删除按键音效
    │       ├── paste.wav       # 内容粘贴与文件拖入音效
    │       ├── snake.wav       # 开场像素蛇「嘶嘶」音效
    │       └── type.wav        # 开场引导像素电报打字音效
    └── tools/                  # 本地轻量便携工具链与字体目录
        ├── yt-dlp.exe          # 独立流媒体解析可执行文件
        ├── UnRAR.exe           # RAR 压缩包解压外部工具
        └── zpix.ttf            # 推荐搭配的像素风格终端字体
                                # （ffmpeg/ffprobe 优先读取系统 PATH 或按需自动下载至 ~/.pykuai/tools/）
```

### 各板块详细职责

#### 1. 根目录配置、发布流水线与归档区
* **[.github/workflows/publish.yml](.github/workflows/publish.yml)**：配置基于 GitHub OIDC（Trusted Publisher）的无密钥 PyPI 自动构建与发布工作流，推送 `v*` 或 `pykuaiv*` 标签（或手动触发 `workflow_dispatch`）即可完成打包校验与发布。
* **[pyproject.toml](pyproject.toml)**：定义项目名称、版本号（`1.2.7`）、Python 版本下限（`>=3.9`）、核心依赖与可选分组（`office` / `media` / `cv` / `archive` / `ui` / `all`），注册全局 CLI 命令 `pykuai = "pykuai.cli:main"`，并声明打包资源。
* **[README.md](README.md)** / **[README.zh-CN.md](README.zh-CN.md)**：分别用于 GitHub / PyPI 展示的英文主文档与中文详尽手册。
* **[.backup_engines/](.backup_engines/)**：存放早期重构前保留的 10 个参考脚本（`archive.py`、`excel_merge.py`、`excel_split.py`、`img_compress.py`、`media_fetch.py`、`office_fixed.py`、`pdf_split.py`、`scanner.py`、`video_compress.py`、`web_sniffer.py`），仅作历史备份，不会被注册器自动加载。

#### 2. `pykuai/` 包入口区
* **[`pykuai/__init__.py`](pykuai/__init__.py)** / **[`pykuai/__main__.py`](pykuai/__main__.py)**：提供版本号/作者信息定义以及 `python -m pykuai` 启动支持。
* **[`pykuai/cli.py`](pykuai/cli.py)**：项目总入口。无子参数时依次启动开场动画、终端身份标识与初次进入的像素电报引导语，随后进入自研交互式控制台（REPL，内置逐字打字、拖入/粘贴突发检测、回车与历史记录音效）；有子参数时直接走无交互/快速命令行分支。支持拖入或粘贴常见图片路径自动唤醒 `ifc` 引擎。

#### 3. `pykuai/core/` 微内核层
* **[`ui.py`](pykuai/core/ui.py)**：负责 Cyber-Dark 主题配色、极简 ASCII Banner、像素电报逐字打印引导语（`play_console_greeting` 联动 `type.wav`），以及修改并在退出时恢复终端标题和图标。
* **[`intro.py`](pykuai/core/intro.py)**：负责启动时的高 DPI 桌面像素贪吃蛇开场过场动画，并联动播放/停止 `snake.wav`；使用 `--fast` 参数可跳过动画直达控制台。
* **[`audio.py`](pykuai/core/audio.py)**：非阻塞复古音效播放器，自动从 `pykuai/assets/sfx/` 加载 `.wav` 文件，并将工具托盘（`tt`）中切换的全局音效开关持久化保存至 `~/.pykuai/settings.json`。
* **[`tui.py`](pykuai/core/tui.py)**：基于 `Textual` 封装的鼠标可点击终端 UI 组件集（`ToggleChip`、`ActionChip`、`SfxToggleChip`、`PyKuaiStudioApp`），内置无额外子脚本界面干扰的全局点击（`click.wav`）、输入框打字/删除（`key.wav`）、粘贴（`paste.wav`）与回车提交（`enter.wav`）音效挂钩。
* **[`base.py`](pykuai/core/base.py)** 与 **[`registry.py`](pykuai/core/registry.py)**：定义所有插件必须实现的 `BaseEngine` 接口，并在运行时扫描 `pykuai/engines/` 中符合三位小写字母命名规范（`^[a-z]{3}$`）的模块实现零配置注册。
* **[`tray.py`](pykuai/core/tray.py)**：驱动 `tt` 指令，在终端内提供可鼠标/键盘选择的工具托盘界面（右下角内置全局复古音效开关 `🔊 SFX ON / 🔇 SFX OFF`），或将 `tt <tool> [args]` 直接分发至目标引擎执行。
* **[`deps.py`](pykuai/core/deps.py)**：驱动 `pp` 指令，自动扫描已注册引擎的依赖需求与环境缺失项，提供可视化勾选安装与 `--check` / `-y` 自动化模式。
* **[`tools.py`](pykuai/core/tools.py)**：统一优先定位 `pykuai/tools/` 下的便携工具链、系统 `PATH` 与 `~/.pykuai/tools/` 中的二进制可执行文件（如 `ffmpeg`、`ffprobe`、`yt-dlp`、`UnRAR` 及 JS 运行时），并在 Windows 缺失 `FFmpeg` 时支持 SHA256 校验后按需自动安装至 `~/.pykuai/tools/`。
* **[`watchdog.py`](pykuai/core/watchdog.py)**：后台守护 Windows Terminal `settings.json` 状态，防止控制台异常关闭时残留临时视觉配置。

#### 4. `pykuai/engines/` 即插即用工具引擎层
* **[`ifc.py`](pykuai/engines/ifc.py)**（`ifc` — *Image Format Converter*）：基于 `Pillow` 的多格式图像转换与多分辨率 `.ico` 图标容器打包引擎，支持 `PNG`、`JPG`、`WEBP`、`BMP`、`GIF`、`TIFF`、`AVIF`、`ICO` 互转，内置交互式格式与多尺寸层选择界面（`IfcStudioApp`）。
* **[`ytd.py`](pykuai/engines/ytd.py)**（`ytd` — *YouTube Download*）：基于 `yt-dlp` 与 `FFmpeg` 的音视频流下载引擎，支持 YouTube（自动集成 JS 运行时与 EJS 挑战解析）、Bilibili、X/Twitter 等平台，提供最佳画质 MP4 自动混流及 MP3/M4A 音频提取。

#### 5. `pykuai/assets/` 与 `pykuai/tools/` 静态资源与工具链区
* **[`pykuai/assets/`](pykuai/assets/)**：统一收纳应用视觉图标 `icon.ico` 与 `sfx/` 子目录中的 6 枚 CC0 复古波形音效（`snake.wav`、`type.wav`、`key.wav`、`enter.wav`、`click.wav`、`paste.wav`）。
* **[`pykuai/tools/`](pykuai/tools/)**：内置轻量级 Windows 便携命令行工具（`yt-dlp.exe`、`UnRAR.exe`）与复古像素字体 `zpix.ttf`；体积较大的 `ffmpeg.exe` / `ffprobe.exe` 不随 Git 仓库分发，缺失时可由 `ytd` 提示一键下载至 `~/.pykuai/tools/`（或执行 `pykuai tt ytd --install-ffmpeg`）。

---

## 🚀 双模式运行与全局指令

### 1. 交互式控制台模式（REPL）

在任意终端执行以下命令即可进入工作台：

```bash
pykuai
# 跳过开场贪吃蛇过场动画：
pykuai --fast
```

内置 **6 个双字母全局指令**：

| 指令 | 含义 | 作用说明 |
| :--- | :--- | :--- |
| `tt` | **Tool Tray** | 打开可视化工具托盘（右下角可直接点击开关全局音效），或执行 `tt <tool> [args]` |
| `pp` | **Pull Packages** | 检查并可视化安装插件所需依赖（支持 `pp --check` / `pp -y`） |
| `vv` | **View Version** | 查看版本号、作者签名及上游开源致谢信息 |
| `cc` | **Clear Console** | 清屏并重新绘制 Banner |
| `hh` | **Help Hub** | 查看全局指令帮助表 |
| `gg` | **Good Game** | 安全退出控制台并恢复原始终端标题与图标 |

> 💡 **快捷操作**：在控制台提示符处直接拖入或粘贴图片路径，会自动呼出 `ifc` 图像转换工具。

### 2. 直接命令行模式（CLI）

适合脚本编排与终端直调，不进入交互式循环：

```bash
# 打开工具托盘（在管道/非交互环境中自动输出工具列表）
pykuai tt

# 图像格式互转与多尺寸 ICO 打包（ifc）
pykuai tt ifc logo.png -t webp
pykuai tt ifc logo.png -t ico -s 16,32,48,256 -o app.ico

# 视频与音频下载提取（ytd）
pykuai tt ytd "https://www.youtube.com/watch?v=..." -f best
pykuai tt ytd "https://www.youtube.com/watch?v=..." -f mp3 -o ./music

# 依赖扫描与一键安装（pp）
pykuai pp --check
pykuai pp -y

# 查看帮助或版本号
pykuai hh
pykuai --version
```

---

## 🛠️ 安装与开发配置

通过 PyPI 直接安装或本地可编辑安装：

```bash
# 从 PyPI 安装核心版本
pip install pykuai

# 或连同媒体下载 / 全部可选依赖一起安装
pip install "pykuai[media]"
pip install "pykuai[all]"

# 克隆仓库后的本地可编辑安装（开发模式）
pip install -e .
pip install -e ".[all]"
```

安装完成后即可在任意目录使用 `pykuai` 或 `python -m pykuai`。

---

## 🧩 扩展新引擎（三字母插件规范）

在 `pykuai/engines/` 下新建一个以**三个纯小写英文字母**命名的 `.py` 文件（例如 `pdf.py`），继承 [`BaseEngine`](pykuai/core/base.py) 即可自动接入：

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

保存后无需改动任何核心文件，重启 `pykuai` 即可在 `tt` 中看到 `pdf`，同时 `pp` 会自动读取 `requires` 进行环境校验。

---

## 🙏 第三方开源工具与素材致谢

* **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — 驱动 `pykuai tt ytd` 的流媒体解析核心
* **[FFmpeg](https://ffmpeg.org/)** — 音视频混流与 MP3/M4A 转码引擎
* **[Pillow](https://python-pillow.org/)** — 驱动 `pykuai tt ifc` 的图像处理与多格式编码库
* **[Textual](https://textual.textualize.io/)** & **[Rich](https://github.com/Textualize/rich)** — Cyber-Dark 终端交互界面与渲染框架
* **[Kenney Audio](https://kenney.nl/)** & **[CC0 Public Domain Sounds](https://github.com/lavenderdotpet/CC0-Public-Domain-Sounds)** — 复古 CC0 界面点击、按键、回车、粘贴、像素电报与蛇嘶音效素材
