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