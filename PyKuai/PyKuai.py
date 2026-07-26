import sys
import os
import json
import importlib.util
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QPushButton, QLabel, QStackedWidget, QLineEdit,
                               QFrame, QMessageBox, QTreeWidget, QTreeWidgetItem,
                               QSystemTrayIcon, QMenu)
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QFont, QIcon, QFontDatabase, QPixmap, QAction

# ==========================================
# 全局路径与配置 (单文件 EXE 终极适配版)
# ==========================================
if getattr(sys, 'frozen', False):
    # 打包成 exe 后，资源会被自动解压到 sys._MEIPASS 这个临时秘密基地
    BASE_DIR = sys._MEIPASS
    # 获取 exe 文件真正所在的物理目录
    RUN_DIR = os.path.dirname(sys.executable)
else:
    # 源码开发状态
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RUN_DIR = BASE_DIR

# 核心资源（打包进 exe，运行时从临时目录读取）
SCRIPTS_DIR = os.path.join(BASE_DIR, "Scripts")
IMGS_DIR = os.path.join(BASE_DIR, "imgs")
TOOLS_DIR = os.path.join(BASE_DIR, "tools")
ICON_PATH = os.path.join(IMGS_DIR, "script.ico")
FONT_PATH = os.path.join(TOOLS_DIR, "zpix.ttf")

# ==========================================
# 修复 1: 收藏夹数据存放到用户 C盘 的文档(Documents)文件夹中
# ==========================================
DOCS_DIR = os.path.join(os.path.expanduser("~"), "Documents")
if not os.path.exists(DOCS_DIR):
    try:
        os.makedirs(DOCS_DIR, exist_ok=True)
    except Exception:
        pass
FAV_PATH = os.path.join(DOCS_DIR, ".pykuai_fav.json")


# ==========================================
# 抽离说明文档：支持子目录绝对路径读取
# ==========================================
class ConfigManager:
    @staticmethod
    def get_description(script_full_path):
        base_name = os.path.splitext(script_full_path)[0]
        txt_path = f"{base_name}.txt"
        md_path = f"{base_name}.md"
        target_path = txt_path if os.path.exists(txt_path) else (md_path if os.path.exists(md_path) else None)
        if target_path:
            try:
                with open(target_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except Exception as e:
                return f">>> 伴生说明文档读取失败: {e}"
        return ">>> 暂无说明。请在同目录下创建一个同名的 .txt 或 .md 文件来书写说明。"


# ==========================================
# 第一部分：极客黑雾透明验证启动页
# ==========================================
class GeekBootScreen(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.init_ui()

        # 模拟打字特效的目标字符串与索引
        self.target_text = "HelloWorld"
        self.type_index = 0

        # 启动后稍微等待半秒，开始触发“键盘敲击”特效
        QTimer.singleShot(500, self.start_typing)

    def init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(500, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.bg_frame = QFrame(self)
        self.bg_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(15, 15, 15, 220);
                border-radius: 12px;
                border: 1px solid #333;
            }
        """)
        bg_layout = QVBoxLayout(self.bg_frame)
        bg_layout.setContentsMargins(30, 40, 30, 40)

        # 更新启动说明文本，包含作者、用户名和许可证信息
        self.lbl_sys = QLabel(
            "PyKuai Terminal [Version 2.0.0]\n"
            "Author: TuKuai | Username: GallantTarry\n"
            "License: MIT License\n"
            "Initializing secure connection...\n"
            "Waiting for override code:"
        )
        self.lbl_sys.setFont(QFont(QApplication.font().family(), 11))
        self.lbl_sys.setStyleSheet("color: #00FF00; background: transparent; border: none;")

        input_layout = QHBoxLayout()
        lbl_prompt = QLabel("root@pykuai:~# ")
        lbl_prompt.setFont(QFont(QApplication.font().family(), 12, QFont.Bold))
        lbl_prompt.setStyleSheet("color: #00FF00; background: transparent; border: none;")

        self.cmd_input = QLineEdit()
        self.cmd_input.setFont(QFont(QApplication.font().family(), 12, QFont.Bold))
        self.cmd_input.setStyleSheet("color: #00FF00; background: transparent; border: none;")
        self.cmd_input.returnPressed.connect(self.check_auth)

        input_layout.addWidget(lbl_prompt)
        input_layout.addWidget(self.cmd_input)

        bg_layout.addWidget(self.lbl_sys)
        bg_layout.addSpacing(20)
        bg_layout.addLayout(input_layout)
        bg_layout.addStretch()
        layout.addWidget(self.bg_frame)

    def start_typing(self):
        self.type_timer = QTimer(self)
        self.type_timer.timeout.connect(self.type_next_char)
        self.type_timer.start(120)

    def type_next_char(self):
        if self.type_index < len(self.target_text):
            current_text = self.cmd_input.text()
            self.cmd_input.setText(current_text + self.target_text[self.type_index])
            self.type_index += 1
        else:
            self.type_timer.stop()
            QTimer.singleShot(2000, self.check_auth)

    def check_auth(self):
        if self.cmd_input.text().strip().lower() == "helloworld":
            self.lbl_sys.setText("Access Granted. Welcome, Master.\nLoading PyKuai modules...")
            self.cmd_input.setDisabled(True)
            self.lbl_sys.setStyleSheet("color: #00FFFF; background: transparent; border: none;")
            QTimer.singleShot(600, self.enter_main)
        else:
            self.cmd_input.clear()
            self.lbl_sys.setText("Access Denied.\nInvalid override code:")
            self.lbl_sys.setStyleSheet("color: #FF0000; background: transparent; border: none;")

    def enter_main(self):
        self.close()
        self.main_window.show()


# ==========================================
# 第二部分：自定义暗黑拖拽栏 (带图标、自启设置、托盘最小化)
# ==========================================
class TitleBar(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(40)
        self.setStyleSheet("background: transparent; border: none; border-bottom: 1px solid #333;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)
        layout.setAlignment(Qt.AlignVCenter)

        lbl_icon = QLabel()
        if os.path.exists(ICON_PATH):
            pixmap = QPixmap(ICON_PATH).scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl_icon.setPixmap(pixmap)
        layout.addWidget(lbl_icon)
        layout.addSpacing(5)

        title = QLabel("PyKuai Workspace")
        title.setFont(QFont(QApplication.font().family(), 12, QFont.Bold))
        title.setStyleSheet("color: #00FF00;")
        layout.addWidget(title)

        layout.addStretch()

        self.btn_menu = QPushButton("≡")
        self.btn_menu.setFixedSize(30, 30)
        self.btn_menu.setToolTip("系统设置菜单")
        self.btn_menu.setStyleSheet("""
            QPushButton { color: #888; background: transparent; border: none; font-size: 18px; font-weight: bold; }
            QPushButton:hover { color: #00FFFF; }
        """)
        self.btn_menu.clicked.connect(self.show_settings_menu)
        layout.addWidget(self.btn_menu)

        layout.addSpacing(5)

        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(30, 30)
        self.btn_close.setToolTip("关闭窗口")
        self.btn_close.setStyleSheet("""
            QPushButton { color: #888; background: transparent; border: none; font-size: 16px; font-weight: bold; }
            QPushButton:hover { color: #FF4444; }
        """)
        self.btn_close.clicked.connect(self.parent.handle_close_btn)
        layout.addWidget(self.btn_close)

    def show_settings_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #222; color: #FFF; border: 1px solid #444; padding: 5px; font-size: 13px;} 
            QMenu::item { padding: 5px 20px; }
            QMenu::item:selected { background-color: #444; }
        """)

        action_startup = QAction("🚀 设置 / 取消开机自启", self)
        action_startup.triggered.connect(self.toggle_startup)
        menu.addAction(action_startup)

        menu.addSeparator()

        current_mode = getattr(self.parent, 'close_mode', 'tray')
        mode_text = "最小化到托盘" if current_mode == 'tray' else "彻底关闭程序"
        action_behavior = QAction(f"⚙️ X键功能 (点击切换) [当前: {mode_text}]", self)
        action_behavior.triggered.connect(self.toggle_close_behavior)
        menu.addAction(action_behavior)

        menu.exec(self.btn_menu.mapToGlobal(QPoint(0, self.btn_menu.height())))

    def toggle_close_behavior(self):
        if getattr(self.parent, 'close_mode', 'tray') == 'tray':
            self.parent.close_mode = 'quit'
            QMessageBox.information(self.parent, "设置", "X按钮功能已修改为：彻底退出程序。")
        else:
            self.parent.close_mode = 'tray'
            QMessageBox.information(self.parent, "设置", "X按钮功能已修改为：最小化到托盘。")

    # ==========================================
    # 修复 2: 开机自启逻辑修复 (正确写入 Python 或 EXE 执行路径)
    # ==========================================
    def toggle_startup(self):
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                                 winreg.KEY_ALL_ACCESS)
            app_name = "PyKuai_Workspace"

            try:
                winreg.QueryValueEx(key, app_name)
                winreg.DeleteValue(key, app_name)
                QMessageBox.information(self.parent, "开机自启设置", "已成功【取消】开机自启。")
            except FileNotFoundError:
                if getattr(sys, 'frozen', False):
                    # 如果是打包成的 exe，直接执行 exe 本身
                    cmd = f'"{sys.executable}"'
                else:
                    # 如果是源码运行，则需要用 python.exe 解释器执行当前脚本
                    script_path = os.path.abspath(sys.argv[0])
                    cmd = f'"{sys.executable}" "{script_path}"'

                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
                QMessageBox.information(self.parent, "开机自启设置", "已成功【开启】开机自启！")

            winreg.CloseKey(key)
        except Exception as e:
            QMessageBox.warning(self.parent, "错误", f"设置开机自启失败，请检查系统权限:\n{str(e)}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.parent.dragPos = event.globalPosition().toPoint() - self.parent.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.parent.move(event.globalPosition().toPoint() - self.parent.dragPos)
            event.accept()


# ==========================================
# 第三部分：全黑雾一体化主界面
# ==========================================
class PyKuaiMain(QMainWindow):
    def __init__(self):
        super().__init__()
        self.dragPos = QPoint()
        self.loaded_plugins = {}
        self.item_to_index = {}

        self.close_mode = 'tray'
        self.favorites = self.load_favorites_data()
        self.all_scripts_info = []

        self.init_ui()
        self.init_tray()
        self.load_scripts()

    def load_favorites_data(self):
        if os.path.exists(FAV_PATH):
            try:
                with open(FAV_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []

    def save_favorites_data(self):
        with open(FAV_PATH, 'w', encoding='utf-8') as f:
            json.dump(self.favorites, f, ensure_ascii=False)

    def init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        if os.path.exists(ICON_PATH):
            self.tray_icon.setIcon(QIcon(ICON_PATH))

        tray_menu = QMenu()
        tray_menu.setStyleSheet("""
            QMenu { background-color: #222; color: #FFF; border: 1px solid #444; font-size: 14px;} 
            QMenu::item { padding: 8px 25px; }
            QMenu::item:selected { background-color: #444; }
        """)

        action_show = QAction("显示主工作台", self)
        action_show.triggered.connect(self.showNormal)

        action_quit = QAction("彻底退出程序", self)
        action_quit.triggered.connect(QApplication.instance().quit)

        tray_menu.addAction(action_show)
        tray_menu.addSeparator()
        tray_menu.addAction(action_quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        self.tray_icon.activated.connect(
            lambda reason: self.showNormal() if reason == QSystemTrayIcon.DoubleClick else None)

    def handle_close_btn(self):
        if self.close_mode == 'tray':
            self.hide_to_tray()
        else:
            QApplication.instance().quit()

    def hide_to_tray(self):
        self.hide()
        self.tray_icon.showMessage("PyKuai Workspace", "程序已最小化到系统托盘区，后台持续运行中。",
                                   QSystemTrayIcon.Information, 2000)

    def init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.setFixedSize(820, 530)

        self.main_widget = QFrame(self)
        self.setCentralWidget(self.main_widget)
        self.main_widget.setStyleSheet("""
            QFrame#MainBG {
                background-color: rgba(20, 20, 20, 245);
                border-radius: 12px;
                border: 1px solid #444;
            }
        """)
        self.main_widget.setObjectName("MainBG")

        main_layout = QVBoxLayout(self.main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.title_bar = TitleBar(self)
        main_layout.addWidget(self.title_bar)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(15, 15, 15, 15)

        left_frame = QFrame()
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.setFont(QFont(QApplication.font().family(), 10))
        self.tree_widget.setStyleSheet("""
            QTreeWidget { 
                background: rgba(10, 10, 10, 100); 
                border: 1px solid #333; 
                border-radius: 6px; 
                outline: none; 
            }
            QTreeWidget::item { 
                color: #AAAAAA; 
                padding: 10px 5px; 
                border-bottom: 1px solid #222; 
            }
            QTreeWidget::item:hover { background-color: rgba(255, 255, 255, 10); }
            QTreeWidget::item:selected { 
                color: #00FF00; 
                font-weight: bold; 
                background-color: rgba(0, 255, 0, 15); 
                border-left: 3px solid #00FF00; 
            }
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {
                image: none;
            }
        """)
        self.tree_widget.itemClicked.connect(self.on_tree_item_clicked)
        left_layout.addWidget(self.tree_widget)

        left_frame.setFixedWidth(240)
        content_layout.addWidget(left_frame)

        self.stacked_widget = QStackedWidget()
        content_layout.addWidget(self.stacked_widget)
        main_layout.addLayout(content_layout)

    def load_scripts(self):
        if not os.path.exists(SCRIPTS_DIR):
            try:
                os.makedirs(SCRIPTS_DIR)
            except Exception:
                pass

        folder_mapping = {
            "General-purpose": "📁 泛用性",
            "Niche": "📁 针对性"
        }

        self.fav_root = QTreeWidgetItem(self.tree_widget, ["⭐ 我的收藏夹"])
        self.fav_root.setFont(0, QFont(QApplication.font().family(), 11, QFont.Bold))
        self.fav_root.setForeground(0, Qt.yellow)
        self.fav_root.setExpanded(True)

        page_index = 0
        has_scripts = False

        if os.path.exists(SCRIPTS_DIR):
            folders = [f for f in os.listdir(SCRIPTS_DIR) if os.path.isdir(os.path.join(SCRIPTS_DIR, f))]

            for folder_name in sorted(folders):
                folder_path = os.path.join(SCRIPTS_DIR, folder_name)
                scripts = [f for f in os.listdir(folder_path) if f.endswith(('.py', '.pyw'))]

                if not scripts:
                    continue

                has_scripts = True
                display_folder_name = folder_mapping.get(folder_name, f"📁 {folder_name}")

                parent_item = QTreeWidgetItem(self.tree_widget, [display_folder_name])
                parent_item.setFont(0, QFont(QApplication.font().family(), 11, QFont.Bold))
                parent_item.setForeground(0, Qt.white)

                for script_name in sorted(scripts):
                    display_name = os.path.splitext(script_name)[0]
                    script_full_path = os.path.join(folder_path, script_name)
                    desc_text = ConfigManager.get_description(script_full_path)

                    self.all_scripts_info.append({
                        "path": script_full_path,
                        "name": display_name,
                        "page_index": page_index
                    })

                    child_item = QTreeWidgetItem(parent_item, [f"  📄 {display_name}"])
                    self.item_to_index[id(child_item)] = page_index

                    page = self.create_script_page(script_full_path, display_name, desc_text)
                    self.stacked_widget.addWidget(page)

                    page_index += 1

                parent_item.setExpanded(True)

        self.refresh_favorites_tree()

        if not has_scripts:
            self.show_empty_state()

    def refresh_favorites_tree(self):
        for i in reversed(range(self.fav_root.childCount())):
            self.fav_root.removeChild(self.fav_root.child(i))

        for script in self.all_scripts_info:
            if script["path"] in self.favorites:
                fav_child = QTreeWidgetItem(self.fav_root, [f"  📄 {script['name']}"])
                fav_child.setForeground(0, Qt.cyan)
                self.item_to_index[id(fav_child)] = script["page_index"]

    def toggle_favorite(self, script_path, btn_widget):
        if script_path in self.favorites:
            self.favorites.remove(script_path)
            btn_widget.setText("⭐ 加入收藏夹")
            btn_widget.setStyleSheet(
                "QPushButton { color: #AAAAAA; border: 1px solid #666; background: transparent; border-radius: 6px; } QPushButton:hover { color: #FFF; border-color: #FFF; }")
        else:
            self.favorites.append(script_path)
            btn_widget.setText("🌟 已在收藏夹")
            btn_widget.setStyleSheet(
                "QPushButton { color: #FFFF00; border: 1px solid #FFFF00; background: rgba(255, 255, 0, 15); border-radius: 6px; }")

        self.save_favorites_data()
        self.refresh_favorites_tree()

    def show_empty_state(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        lbl = QLabel("No scripts found.\n请在 Scripts 文件夹下建立子目录并放入脚本。")
        lbl.setStyleSheet("color: #666; font-size: 14px;")
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)

        empty_item = QTreeWidgetItem(self.tree_widget, ["Empty Workspace"])
        self.stacked_widget.addWidget(page)
        self.item_to_index[id(empty_item)] = 0

    def on_tree_item_clicked(self, item, column):
        item_id = id(item)
        if item_id in self.item_to_index:
            self.stacked_widget.setCurrentIndex(self.item_to_index[item_id])

    def create_script_page(self, script_full_path, display_name, desc_text):
        inner_stack = QStackedWidget()
        inner_stack.setStyleSheet("background: transparent;")

        info_page = QWidget()
        info_layout = QVBoxLayout(info_page)
        info_layout.setContentsMargins(20, 10, 20, 20)

        title_layout = QHBoxLayout()
        title = QLabel(display_name)
        title.setFont(QFont(QApplication.font().family(), 20, QFont.Bold))
        title.setStyleSheet("color: #E0E0E0;")
        title_layout.addWidget(title)
        title_layout.addStretch()

        btn_fav = QPushButton()
        btn_fav.setFont(QFont(QApplication.font().family(), 10))
        btn_fav.setFixedSize(120, 30)
        if script_full_path in self.favorites:
            btn_fav.setText("🌟 已在收藏夹")
            btn_fav.setStyleSheet(
                "QPushButton { color: #FFFF00; border: 1px solid #FFFF00; background: rgba(255, 255, 0, 15); border-radius: 6px; }")
        else:
            btn_fav.setText("⭐ 加入收藏夹")
            btn_fav.setStyleSheet(
                "QPushButton { color: #AAAAAA; border: 1px solid #666; background: transparent; border-radius: 6px; } QPushButton:hover { color: #FFF; border-color: #FFF; }")

        btn_fav.clicked.connect(lambda: self.toggle_favorite(script_full_path, btn_fav))
        title_layout.addWidget(btn_fav)

        info_layout.addLayout(title_layout)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("border: none; background-color: #444; max-height: 1px;")
        info_layout.addWidget(line)
        info_layout.addSpacing(15)

        desc = QLabel(desc_text)
        desc.setFont(QFont(QApplication.font().family(), 11))
        desc.setStyleSheet("color: #AAAAAA; line-height: 1.5;")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        info_layout.addWidget(desc, stretch=1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_run = QPushButton("⚡ 运行/切入应用区")
        btn_run.setFont(QFont(QApplication.font().family(), 12, QFont.Bold))
        btn_run.setFixedSize(220, 45)
        btn_run.setStyleSheet("""
            QPushButton { background-color: rgba(0, 255, 0, 10); color: #00FF00; border: 1px solid #00FF00; border-radius: 6px; }
            QPushButton:hover { background-color: rgba(0, 255, 0, 30); box-shadow: 0 0 10px #00FF00; }
            QPushButton:pressed { background-color: rgba(0, 255, 0, 60); }
        """)

        btn_run.clicked.connect(lambda: self.render_plugin_to_view(script_full_path, inner_stack))
        btn_layout.addWidget(btn_run)

        info_layout.addLayout(btn_layout)
        inner_stack.addWidget(info_page)

        return inner_stack

    def render_plugin_to_view(self, script_path, container_stack):
        if not os.path.exists(script_path):
            QMessageBox.critical(self, "Error", "Script file not found!")
            return

        module_name = os.path.splitext(os.path.basename(script_path))[0]

        if module_name in self.loaded_plugins:
            container_stack.setCurrentIndex(1)
            return

        try:
            spec = importlib.util.spec_from_file_location(module_name, script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if hasattr(module, 'PluginWidget'):
                plugin_instance = module.PluginWidget()
                plugin_instance.setStyleSheet("background-color: transparent;")

                wrapper = QWidget()
                wrap_layout = QVBoxLayout(wrapper)
                wrap_layout.setContentsMargins(0, 0, 0, 0)

                header_layout = QHBoxLayout()
                btn_back = QPushButton("🔙 返回功能说明")
                btn_back.setFixedHeight(30)
                btn_back.setFont(QFont(QApplication.font().family(), 10, QFont.Bold))
                btn_back.setStyleSheet("""
                    QPushButton { background-color: transparent; color: #CCC; border: 1px solid #555; border-radius: 4px; padding: 0 15px;}
                    QPushButton:hover { background-color: rgba(255,255,255,10); border-color: #00FF00; color: #00FF00;}
                """)
                btn_back.clicked.connect(lambda: container_stack.setCurrentIndex(0))

                header_layout.addWidget(btn_back)
                header_layout.addStretch()

                wrap_layout.addLayout(header_layout)
                wrap_layout.addWidget(plugin_instance, stretch=1)

                container_stack.addWidget(wrapper)
                container_stack.setCurrentIndex(1)

                self.loaded_plugins[module_name] = wrapper
            else:
                QMessageBox.warning(self, "兼容性错误",
                                    f"脚本 [{module_name}] 不符合规范。\n缺少 'PluginWidget' 继承类。")
        except Exception as e:
            QMessageBox.critical(self, "运行时崩溃", f"加载插件失败:\n{str(e)}")


if __name__ == "__main__":
    # ==========================================
    # 辅助修复: 开机自启后，自动矫正工作目录，防止相对路径报错
    # ==========================================
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))
    else:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

    app = QApplication(sys.argv)

    # ==========================================
    # 修复 3: 单例启动文件锁
    # ==========================================
    if os.name == 'nt':
        import ctypes

        mutex_name = "PyKuai_SingleInstance_Mutex_Lock"
        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            QMessageBox.warning(None, "运行提示", "PyKuai 已经在后台运行中，请检查系统托盘！")
            sys.exit(0)
    else:
        import socket

        try:
            single_instance_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            single_instance_socket.bind(('127.0.0.1', 38452))
        except socket.error:
            QMessageBox.warning(None, "运行提示", "PyKuai 已经在后台运行中！")
            sys.exit(0)

    app.setQuitOnLastWindowClosed(False)

    font_id = QFontDatabase.addApplicationFont(FONT_PATH)
    if font_id != -1:
        font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
        custom_font = QFont(font_family, 11)
        custom_font.setStyleStrategy(QFont.PreferAntialias)
        app.setFont(custom_font)
    else:
        pass

    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))

    main_win = PyKuaiMain()
    boot = GeekBootScreen(main_win)
    boot.show()
    sys.exit(app.exec())