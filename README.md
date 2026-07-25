少侠别急，血压先稳住！看到这个报错确实让人抓狂——明明代码里写了 `import img2pdf`，雷达也扫到了，怎么一打包进 exe 就翻车提示 `No module named 'img2pdf'` 呢？

这背后其实隐藏着 Python 打包界两个极其隐蔽的“坑”，我们把它们揪出来：

### 幕后黑手一：虚拟环境里到底装了没？（最常见）

回想一下，你在 PyCharm 里写 `004_图片转扫描件.pyw` 的时候，虽然代码里敲下了 `import img2pdf`，但你当前正在运行 `build_auto.py` 的那个 `.venv` 虚拟环境里，**到底有没有真真正正执行过 `pip install img2pdf` 呢？**

* 如果你的 `.venv` 里**没有安装**这个库，那么我们上一版 `build_auto.py` 里的 `is_third_party()` 校验函数在调用 `importlib.util.find_spec('img2pdf')` 时就会返回空，直接被雷达误判为“这不是第三方库”而无情过滤掉了！
* 结果就是：雷达根本没把它放进 `--hidden-import` 名单里，PyInstaller 打包时自然两手空空。

### 幕后黑手二：光靠 `--hidden-import` 往往不够硬核

像 `img2pdf`、`cv2` 这种涉及底层图片处理、PDF 生成的第三方库，它们内部往往还藏着一些静态资源、编码映射表或底层二进制组件。单纯告诉 PyInstaller “把这个模块引进来（hidden-import）”，它有时候只拿了代码骨架，把关键的血肉给漏了。

---

### 🛠️ 终极破局方案：给自动打包脚本加个“双保险”

为了彻底杜绝这种灵异事件，我们直接把 `build_auto.py` 升级为“智能雷达 + 饱和式全收割”版本。

请把你的 **`build_auto.py`** 整体替换为以下升级版代码。它不仅会自动扫描，还会对类似 `img2pdf`、`cv2` 这种容易翻车的核心库使用官方最硬核的 `collect_all` 进行饱和式打包：

```python
import os
import ast
import subprocess
import importlib.util
from PyInstaller.utils.hooks import collect_all

def is_third_party(module_name):
    if module_name in ['PyKuai', 'ConfigManager']:
        return False
    try:
        spec = importlib.util.find_spec(module_name)
        if spec and spec.origin:
            if 'site-packages' in spec.origin or 'dist-packages' in spec.origin:
                return True
    except Exception:
        pass
    return False

class ImportVisitor(ast.NodeVisitor):
    def __init__(self):
        self.imports = set()

    def visit_Import(self, node):
        for alias in node.names:
            top_name = alias.name.split('.')[0]
            self.imports.add(top_name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            top_name = node.module.split('.')[0]
            self.imports.add(top_name)
        self.generic_visit(node)

def scan_file(file_path, imports_set):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=file_path)
        visitor = ImportVisitor()
        visitor.visit(tree)
        for imp in visitor.imports:
            if is_third_party(imp):
                imports_set.add(imp)
    except Exception as e:
        print(f"⚠️ 扫描文件 {file_path} 时出错: {e}")

def scan_project():
    found_imports = set()
    if os.path.exists("PyKuai.py"):
        scan_file("PyKuai.py", found_imports)
        
    scripts_dir = "Scripts"
    if os.path.exists(scripts_dir):
        for root, dirs, files in os.walk(scripts_dir):
            for file in files:
                if file.endswith(('.py', '.pyw')):
                    scan_file(os.path.join(root, file), found_imports)
                    
    return list(found_imports)

def main():
    print("==========================================")
    print("🚀 PyKuai 全自动智能打包雷达启动...")
    print("==========================================")
    
    # 1. 确保核心必选库即使雷达漏掉也强制加入
    hidden_imports = set(scan_project())
    forced_libs = ['cv2', 'img2pdf', 'numpy', 'PIL']
    for lib in forced_libs:
        if lib not in hidden_imports:
            hidden_imports.add(lib)
            print(f"🛡️ 强制挂载核心依赖库: {lib}")

    print(f"\n🎯 最终锁定的第三方依赖库: {list(hidden_imports)}\n")

    # 2. 动态收集容易翻车大库的所有底层资源（饱和式攻击）
    collected_binaries = []
    collected_datas = [
        ('Scripts', 'Scripts'), 
        ('imgs', 'imgs'), 
        ('tools', 'tools')
    ]
    collected_hidden = list(hidden_imports)

    for lib in ['cv2', 'img2pdf']:
        try:
            d, b, h = collect_all(lib)
            collected_datas.extend(d)
            collected_binaries.extend(b)
            collected_hidden.extend(h)
            print(f"📦 已通过 collect_all 饱和式捕获库: {lib}")
        except Exception as e:
            print(f"⚠️ 收集 {lib} 详情时跳过: {e}")

    # 去重
    collected_hidden = list(set(collected_hidden))

    # 3. 组装 PyInstaller 命令
    cmd = [
        "pyinstaller",
        "-F",
        "-w",
        "-i", "imgs/script.ico",
    ]

    for src, dst in collected_datas:
        cmd.extend(["--add-data", f"{src};{dst}"])

    for imp in collected_hidden:
        cmd.extend(["--hidden-import", imp])

    cmd.append("PyKuai.py")

    print("\n📦 正在呼叫 PyInstaller 进行全包封装...")
    print("------------------------------------------")

    try:
        subprocess.run(cmd, check=True)
        print("------------------------------------------")
        print("✨ 恭喜少侠！全自动饱和式打包大功告成！")
    except subprocess.CalledProcessError as e:
        print(f"❌ 打包中断，错误代码: {e}")

if __name__ == "__main__":
    main()

```

### 少侠只需做两步：

1. 先在 PyCharm 终端确认你的环境装了该库：输入 `pip install img2pdf`。
2. 用上面这个升级版的 `build_auto.py` 重新运行一次（它在代码里对 `img2pdf` 和 `cv2` 做了硬编码强制保护，绝不可能再漏掉）。

再试一次，绝对药到病除！
