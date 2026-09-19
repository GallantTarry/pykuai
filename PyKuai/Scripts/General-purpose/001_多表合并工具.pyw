# -*- coding: utf-8 -*-
import os
import pandas as pd
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QFileDialog, QMessageBox, QApplication, QTextEdit)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QFont, QFontDatabase, QTextCursor


class PluginWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setSpacing(15)

        # 1. 标题 (统一为极客橙 #FF9800)
        title_lbl = QLabel("Excel 多表合并工具")
        title_lbl.setStyleSheet("color: #FF9800; font-size: 22px; font-weight: bold;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        desc_lbl = QLabel("✅ 智能对齐消除表头空格 | ✅ 强制锁定长数字(防手机号丢失)")
        desc_lbl.setStyleSheet("color: #AAAAAA; font-size: 13px;")
        desc_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_lbl)

        layout.addSpacing(10)

        # 2. 文件夹选择交互区 (对齐批量解压的深色输入框)
        folder_layout = QHBoxLayout()
        self.lbl_folder = QLabel("目标工作区:")
        self.lbl_folder.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_folder.setFixedWidth(90)

        self.entry_folder = QLineEdit()
        self.entry_folder.setPlaceholderText("请选择存放待合并 Excel 的文件夹路径...")
        self.entry_folder.setStyleSheet("""
            QLineEdit {
                background-color: rgba(0, 0, 0, 100);
                color: #00FF00;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px;
            }
            QLineEdit:focus { border: 1px solid #00FF00; }
        """)

        self.btn_browse = QPushButton("检索...")
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        self.btn_browse.setStyleSheet("""
            QPushButton { background-color: #444; color: white; border-radius: 5px; padding: 8px 15px; font-weight: bold; }
            QPushButton:hover { background-color: #666; }
        """)
        self.btn_browse.clicked.connect(self.select_folder)

        folder_layout.addWidget(self.lbl_folder)
        folder_layout.addWidget(self.entry_folder)
        folder_layout.addWidget(self.btn_browse)
        layout.addLayout(folder_layout)

        # 3. 新增：实时终端日志框 (统一为终端绿代码流风格)
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setStyleSheet("""
            QTextEdit {
                background-color: rgba(10, 10, 10, 200);
                color: #00FF00;
                border: 1px solid #333;
                border-radius: 5px;
                padding: 10px;
                font-size: 13px;
            }
        """)
        self.log_console.setText("等待初始化合并指令 (自动跳过异常文件)...\n")
        layout.addWidget(self.log_console)

        # 4. 核心执行按钮 (统一为镂空霓虹绿特效)
        self.btn_start = QPushButton("🚀 一键合并")
        self.btn_start.setFixedSize(220, 45)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setStyleSheet("""
            QPushButton { 
                background-color: transparent; 
                color: #00FF00; 
                border: 1px solid #00FF00;
                font-weight: bold; 
                font-size: 15px; 
                border-radius: 6px; 
            }
            QPushButton:hover { background-color: rgba(0, 255, 0, 30); box-shadow: 0 0 10px #00FF00; }
            QPushButton:disabled { color: #555; border: 1px solid #555; background-color: transparent; }
        """)
        self.btn_start.clicked.connect(self.start_merge)

        layout.addWidget(self.btn_start, 0, Qt.AlignCenter)

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "请选择存放待合并Excel的文件夹")
        if folder_path:
            self.entry_folder.setText(folder_path)
            self.log_console.append(f"> 目标战区已锁定: {folder_path}\n> 引擎已准备就绪。")
            self.log_console.moveCursor(QTextCursor.End)

    def start_merge(self):
        folder_path = self.entry_folder.text().strip()

        if not folder_path:
            QMessageBox.warning(self, "操作提示", "请先选择存放待合并Excel的文件夹！")
            return

        self.btn_start.setText("⚙️ 引擎合并中...")
        self.btn_start.setDisabled(True)
        self.btn_browse.setDisabled(True)

        self.log_console.clear()
        self.log_console.append(f"🚀 启动雷达扫描，分析目录下 Excel 文件...\n" + "-" * 40)
        # 强制刷新UI，让日志立刻显示
        QApplication.processEvents()

        try:
            all_data = []
            file_count = 0
            error_files = []

            for file in os.listdir(folder_path):
                if (file.endswith('.xlsx') or file.endswith('.xls')) and not file.startswith('~$'):
                    if "汇总表_合并结果" in file:
                        continue

                    file_path = os.path.join(folder_path, file)

                    self.log_console.append(f"⏳ 正在提取数据: {file} ...")
                    self.log_console.moveCursor(QTextCursor.End)
                    QApplication.processEvents()

                    try:
                        sheet_dict = pd.read_excel(file_path, sheet_name=None, dtype=str)
                        for sheet_name, df in sheet_dict.items():
                            df.columns = df.columns.astype(str).str.strip()
                            df.dropna(how='all', axis=0, inplace=True)
                            df.dropna(how='all', axis=1, inplace=True)

                            if not df.empty:
                                df.insert(0, '数据来源_Sheet名', sheet_name)
                                df.insert(0, '数据来源_源文件名', file)
                                all_data.append(df)
                        file_count += 1
                        self.log_console.append(f"✅ 提取成功: {file}")
                    except Exception as e:
                        error_files.append((file, str(e)))
                        self.log_console.append(f"❌ 提取失败: {file} | 错误详情: {e}")

                    self.log_console.moveCursor(QTextCursor.End)
                    QApplication.processEvents()

            if all_data:
                self.log_console.append("-" * 40)
                self.log_console.append(f"🔄 正在进行底层数据垂直堆叠 (共 {file_count} 份有效文件)...")
                QApplication.processEvents()

                merged_df = pd.concat(all_data, ignore_index=True)
                merged_df.fillna("", inplace=True)
                output_file_path = os.path.join(folder_path, "汇总表_合并结果.xlsx")
                merged_df.to_excel(output_file_path, index=False)

                self.log_console.append(f"✅ 堆叠完毕！共生成 {len(merged_df)} 行明细数据。")
                self.log_console.append(f"📁 总表已保存至: 汇总表_合并结果.xlsx")

                msg = f"✅ 合并圆满完成！\n\n共读取了 {file_count} 个文件，总计合并 {len(merged_df)} 行数据。\n\n汇总表已安全保存至该文件夹下。"
                if error_files:
                    msg += f"\n\n⚠️ 另有 {len(error_files)} 个文件因异常被跳过。\n典型的报错如: {error_files[0][1]}"
                QMessageBox.information(self, "深度任务简报", msg)
            else:
                self.log_console.append("⚠️ 任务结束：没有提取到任何有效数据。")
                err_msg = "任务结束：没有提取到任何有效数据。\n请检查该文件夹下是否有合法的 Excel 文件，或者表格是否全为空。"
                if error_files:
                    err_msg += f"\n\n🚨 发现底层致命崩溃！\n后台尝试读取时发生了 {len(error_files)} 次异常。\n首个报错文件: {error_files[0][0]}\n报错详情: {error_files[0][1]}"
                QMessageBox.warning(self, "合并失败", err_msg)

        except Exception as e:
            self.log_console.append(f"❌ 运行异常: {e}")
            QMessageBox.critical(self, "运行异常",
                                 f"保存失败！\n提示：请检查目标文件夹是否有写入权限，或者“汇总表_合并结果.xlsx”是否正被 Excel 软件占用。\n\n报错详情: {e}")

        finally:
            self.btn_start.setText("🚀 一键合并全境")
            self.btn_start.setDisabled(False)
            self.btn_browse.setDisabled(False)
            self.log_console.moveCursor(QTextCursor.End)


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # 动态加载 ../../tools/zpix.ttf，保证单独双击运行测试时也是像素风
    tools_dir = os.path.abspath(os.path.join(current_dir, "../..", "tools"))
    font_path = os.path.join(tools_dir, "zpix.ttf")
    if os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id != -1:
            font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
            app.setFont(QFont(font_family, 10))

    icon_path = os.path.abspath(os.path.join(current_dir, "../..", "imgs", "script.ico"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = PluginWidget()
    window.setWindowTitle("Excel 多表一键合并工具 - 独立调试模式")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    window.resize(600, 450)
    window.show()
    sys.exit(app.exec())