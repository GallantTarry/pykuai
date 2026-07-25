# -*- coding: utf-8 -*-
import os
import pandas as pd
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QFileDialog, QMessageBox, QApplication)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QFont


# =================================================================
# 核心规范：必须名为 PluginWidget 并继承自 QWidget
# =================================================================
class PluginWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        # 让插件自适应撑满主程序右侧区域
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setSpacing(20)

        # 1. 标题区域
        title_lbl = QLabel("Excel 多表一键合并引擎")
        title_lbl.setStyleSheet("color: #00FFFF; font-size: 22px; font-weight: bold; font-family: 'Microsoft YaHei';")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        # 2. 文件夹选择交互区
        folder_layout = QHBoxLayout()
        self.lbl_folder = QLabel("待合并文件夹:")
        self.lbl_folder.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")

        self.entry_folder = QLineEdit()
        self.entry_folder.setPlaceholderText("请选择存放待合并 Excel 的文件夹路径...")
        self.entry_folder.setStyleSheet("""
            QLineEdit {
                background-color: rgba(0, 0, 0, 100);
                color: #00FF00;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px;
                font-family: Consolas;
            }
            QLineEdit:focus { border: 1px solid #00FF00; }
        """)

        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        self.btn_browse.setStyleSheet("""
            QPushButton { 
                background-color: #444; 
                color: white; 
                border-radius: 5px; 
                padding: 8px 15px; 
                font-weight: bold;
            }
            QPushButton:hover { background-color: #666; }
        """)
        self.btn_browse.clicked.connect(self.select_folder)

        folder_layout.addWidget(self.lbl_folder)
        folder_layout.addWidget(self.entry_folder)
        folder_layout.addWidget(self.btn_browse)
        layout.addLayout(folder_layout)

        # 3. 核心执行按钮
        self.btn_start = QPushButton("🚀 开始一键合并")
        self.btn_start.setFixedSize(220, 45)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setStyleSheet("""
            QPushButton { 
                background-color: #4CAF50; 
                color: #111; 
                font-weight: bold; 
                font-size: 15px; 
                border-radius: 6px; 
            }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:disabled { background-color: #2e6030; color: #888; }
        """)
        self.btn_start.clicked.connect(self.start_merge)

        # 将按钮居中放置
        layout.addWidget(self.btn_start, 0, Qt.AlignCenter)

        # 弹簧将内容向上顶
        layout.addStretch()

    def select_folder(self):
        """调起系统弹窗选择文件夹"""
        folder_path = QFileDialog.getExistingDirectory(self, "请选择存放待合并Excel的文件夹")
        if folder_path:
            self.entry_folder.setText(folder_path)

    def start_merge(self):
        """核心合并逻辑 (平移自原有 pandas 逻辑)"""
        folder_path = self.entry_folder.text().strip()

        if not folder_path:
            QMessageBox.warning(self, "操作提示", "请先选择存放待合并Excel的文件夹！")
            return

        # 锁定按钮防误触
        self.btn_start.setText("正在拼命合并中...")
        self.btn_start.setDisabled(True)
        # 强制刷新 UI，避免主线程阻塞导致按钮文字没变过去
        QApplication.processEvents()

        try:
            all_data = []
            file_count = 0
            error_files = []

            # 遍历读取机制
            for file in os.listdir(folder_path):
                if (file.endswith('.xlsx') or file.endswith('.xls')) and not file.startswith('~$'):
                    # 防无限套娃：跳过工具自己生成的汇总表
                    if "汇总表_合并结果" in file:
                        continue

                    file_path = os.path.join(folder_path, file)
                    try:
                        sheet_dict = pd.read_excel(file_path, sheet_name=None, dtype=str)
                        for sheet_name, df in sheet_dict.items():
                            df = df.dropna(how='all')
                            if not df.empty:
                                df.insert(0, '数据来源_Sheet名', sheet_name)
                                df.insert(0, '数据来源_源文件名', file)
                                all_data.append(df)
                        file_count += 1
                    except Exception as e:
                        print(f"读取异常: {file}, 错误: {e}")
                        error_files.append(file)

            # 数据合并与输出
            if all_data:
                merged_df = pd.concat(all_data, ignore_index=True)
                output_file_path = os.path.join(folder_path, "汇总表_合并结果.xlsx")
                merged_df.to_excel(output_file_path, index=False)

                msg = f"✅ 合并圆满完成！\n\n共读取了 {file_count} 个文件，总计合并 {len(merged_df)} 行数据。\n汇总表已安全保存至该文件夹下。"
                if error_files:
                    msg += f"\n\n⚠️ 另有 {len(error_files)} 个文件读取失败被跳过(可能被密码加密或损坏)。"
                QMessageBox.information(self, "合并成功", msg)
            else:
                QMessageBox.warning(self, "合并失败",
                                    "任务结束：没有提取到任何有效数据。\n请检查该文件夹下是否有合法的 Excel 文件，或者表格是否全为空。")

        except Exception as e:
            QMessageBox.critical(self, "运行异常",
                                 f"保存失败！\n提示：请检查目标文件夹是否有写入权限，或者“汇总表_合并结果.xlsx”是否正被 Excel 软件占用。\n\n报错详情: {e}")

        finally:
            # 恢复按钮状态
            self.btn_start.setText("🚀 开始一键合并")
            self.btn_start.setDisabled(False)


# =================================================================
# 独立调试机制：被主程序 import 时会自动忽略这部分代码
# =================================================================
if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)

    # 动态寻址加载图标：脚本存放在 Scripts/，图标在 ../imgs/script.ico
    current_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.abspath(os.path.join(current_dir, "../..", "imgs", "script.ico"))

    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = PluginWidget()
    window.setWindowTitle("Excel 多表一键合并工具 - 独立调试模式")
    # 模拟主程序的黑雾背景色
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    window.resize(600, 250)
    window.show()
    sys.exit(app.exec())