# 🐍 PyKuai (Cyber Script Workbench)

> **极客暗黑终端脚本工作台 & 插拔式自动化工具箱**  
> *"The Lord is my shepherd."* —— Author: **TuKuai** | Username: **GallantTarry**

---

## 🌟 核心理念与架构

`pykuai` 是一个由 `rich` 驱动的高扩展性、模块化终端脚本工作台。告别传统臃肿的 GUI 界面与冗余布局代码，将注意力彻底释放回归到**纯净的数据处理逻辑**与**极致的终端美学**。

```text
pykuai/
├── pyproject.toml              # 现代化包配置与控制台脚本入口 (pykuai)
├── pykuai/
│   ├── cli.py                  # 主控制台：双模式分流 (一击脱离 vs 沉浸交互)
│   ├── core/
│   │   ├── base.py             # 引擎基类规范 (BaseEngine)
│   │   ├── registry.py         # 插件动态自动发现与按需加载器 (Auto-Discovery)
│   │   ├── ui.py               # 终端极客美学资产 (ASCII 小蛇、面板、翠绿动态进度条)
│   │   └── tools.py            # 统一底层二进制工具定位器 (FFmpeg, UnRAR, yt-dlp)
│   ├── engines/                # 随插即用引擎库 (全量复刻 11 大功能)
│   │   ├── archive.py          # 01. RAR/ZIP 矩阵解压引擎
│   │   ├── excel_merge.py      # 02. Excel 多表垂直合并工具
│   │   ├── excel_split.py      # 03. Excel 总表条件拆分
│   │   ├── scanner.py          # 04. 图片转黑白扫描件 (转PDF)
│   │   ├── ico_maker.py        # 05. PNG 转多分辨率 ICO 容器
│   │   ├── pdf_split.py        # 06. PDF 断点拆分引擎
│   │   ├── img_compress.py     # 07. 万能图片压缩
│   │   ├── video_compress.py   # 08. 万能视频极限压缩 (FFmpeg)
│   │   ├── media_fetch.py      # 09. 音视频链接获取引擎 (yt-dlp)
│   │   ├── web_sniffer.py      # 10. JS 动态节点嗅探脚本生成
│   │   └── office_fixed.py     # 11. 采购报价多表定式合并
│   └── tools/                  # 预置二进制依赖工具
```

---

## 🚀 极客双模式交互

### 1. 沉浸式终端模式 (Interactive Console)
只需在任何终端中输入 `pykuai` 并回车，系统将清屏并以霓虹翠绿（`#10b981`）呈现 ASCII 小蛇与系统矩阵，进入全中文交互式问答菜单：

```bash
pykuai
```

```text
       ___
     /  •  \
  ~<(___    \       PyKuai [v1.2.7]
        \    \      >> Cyber Script Workbench <<
    _.-' '---'--._  Author: TuKuai | User: GallantTarry
   (  (________)  ) _ "The Lord is my shepherd."
    \____________/_/'

┌─ [⚡ PyKuai 挂载引擎矩阵列表] ────────────────────────────────────────────────────────┐
│ 序号 │ 核心指令       │ 引擎别名          │ 功能说明与特性                             │ 分类         │
├──────┼────────────────┼───────────────────┼────────────────────────────────────────────┼──────────────┤
│  1   │ archive        │ extract, unrar    │ RAR/ZIP 矩阵解压 (递归穿透 + 密码解密)      │ 通用办公     │
│  2   │ excel-merge    │ merge-excel       │ Excel 多表垂直合并 (消除空格 + 防数字截断) │ 通用办公     │
│  3   │ excel-split    │ split-excel       │ Excel 总表条件拆分 (按指定列值分组导出)     │ 通用办公     │
│  4   │ pdf-split      │ split-pdf         │ PDF 断点拆分引擎 (指定页码分子重组切割)    │ 通用办公     │
│  5   │ scanner        │ scan, scan-img    │ 图片转黑白扫描件 (高斯自适应二值化转PDF)   │ 多媒体与图像 │
│  6   │ ico            │ make-ico, png2ico │ PNG 转多分辨率 ICO 容器 (16~256多图层)     │ 多媒体与图像 │
│  7   │ img-compress   │ compress-img      │ 万能图片压缩 (Lanczos重采样 + 画质压缩)    │ 多媒体与图像 │
│  8   │ video-compress │ vid-min           │ 万能视频极限压缩 (自动算码率压至指定MB)    │ 多媒体与图像 │
│  9   │ media-fetch    │ download, ytdl    │ 音视频链接获取引擎 (yt-dlp 视频/音频MP3)   │ 多媒体与图像 │
│ 10   │ web-sniffer    │ sniffer, js-dump  │ JS 动态节点嗅探 (一键复制到剪贴板破反爬)   │ 针对性专精   │
│ 11   │ office-fixed   │ nari-merge        │ 采购报价多表定式合并 (20列特征表头扫描)    │ 针对性专精   │
└────────────────────────────────────────────────────────────────────────────────────┘

[?] 请输入功能序号或命令名称 (输入 0 或 q 退出): 
```

### 2. 一击脱离模式 (Direct Command)
明确需求时，直接敲指令跑完即退，纯净高效，完美契合脚本管道：

```bash
# 递归穿透解压当前目录所有压缩包，支持加密包
pykuai archive ./my_archives -p 123456

# 合并文件夹下所有 Excel，对齐列头并保留长手机号
pykuai excel-merge ./data_folder -o 汇总表.xlsx

# 将总表按“部门”列拆分成几十个独立文件
pykuai excel-split total.xlsx -c 部门

# 将手机拍的照片一键转成无底灰的纯净黑白扫描件 PDF
pykuai scanner ./receipt.jpg

# 制作多尺寸 Windows 高清图标
pykuai ico logo.png

# 在第 15 页处将长 PDF 物理切断为上下两卷
pykuai pdf-split handbook.pdf -p 15

# 将视频高保真极限压制到微信/邮箱限制的 25MB 大小
pykuai video-compress large_movie.mp4 -t 25

# 提取 Bilibili / YouTube 视频的最佳画质或 MP3 音频
pykuai media-fetch "https://www.bilibili.com/video/BV1..." -f video
pykuai media-fetch "https://www.youtube.com/watch?v=..." -f audio

# 一键把破反爬表格嗅探 JS 代码刷入剪贴板
pykuai web-sniffer
```

---

## 🛠️ 安装与本地开发

在项目根目录下通过可编辑模式安装：

```bash
cd c:\Users\TuKuai\Documents\GitHub\pykuai
pip install -e .
```

安装后，`pykuai` 指令将立即注册至全局环境变量中，在任意路径打开终端均可瞬间召唤！

---

## 🧩 如何扩展新引擎？（随插即用）

只需要在 `pykuai/engines/` 目录下新建一个 Python 文件（例如 `my_tool.py`），继承 `BaseEngine`：

```python
from pykuai.core.base import BaseEngine
from rich.console import Console

class MyToolEngine(BaseEngine):
    name = "my-tool"
    aliases = ["mt"]
    description = "我的定制自动化小引擎"
    category = "个人定制"

    def register_args(self, parser):
        parser.add_argument("--target", help="目标")

    def run_direct(self, args, console: Console) -> int:
        console.print(f"[green]执行任务: {args.target}[/green]")
        return 0

    def run_interactive(self, console: Console) -> int:
        console.print("[green]交互式执行任务...[/green]")
        return 0
```

保存后，`pykuai` 会通过动态反射自动发现它，立即出现在主菜单与命令行中，**完全无需修改核心代码！**
