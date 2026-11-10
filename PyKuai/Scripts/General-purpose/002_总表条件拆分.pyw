# -*- coding: utf-8 -*-
import os
import re
import pandas as pd
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QFileDialog, QMessageBox, QApplication, QComboBox, QTextEdit)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QFont, QFontDatabase, QTextCursor


def clean_filename(filename):
    """清洗文件名，替换Windows操作系统中不允许出现的非法字符"""
    if pd.isna(filename) or str(filename).strip() == "":
        return "空值或未指定"
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', str(filename))
    return safe_name.strip()


# =================================================================
# 核心规范：必须名为 PluginWidget 并继承自 QWidget
# =================================================================
class PluginWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setSpacing(15)

        # 1. 标题 (统一为极客橙 #FF9800)
        title_lbl = QLabel("Excel 总表条件拆分")
        title_lbl.setStyleSheet("color: #FF9800; font-size: 22px; font-weight: bold;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        # 2. 文件选择交互区
        file_layout = QHBoxLayout()
        self.lbl_file = QLabel("待拆分的总表:")
        self.lbl_file.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_file.setFixedWidth(100)

        self.entry_file = QLineEdit()
        self.entry_file.setReadOnly(True)
        self.entry_file.setPlaceholderText("请选择需要拆分的总表 Excel 文件...")
        self.entry_file.setStyleSheet("""
            QLineEdit {
                background-color: rgba(0, 0, 0, 100);
                color: #00FF00;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px;
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
        self.btn_browse.clicked.connect(self.select_file)

        file_layout.addWidget(self.lbl_file)
        file_layout.addWidget(self.entry_file)
        file_layout.addWidget(self.btn_browse)
        layout.addLayout(file_layout)

        # 3. 拆分条件选择区
        combo_layout = QHBoxLayout()
        self.lbl_combo = QLabel("拆分依据列:")
        self.lbl_combo.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_combo.setFixedWidth(100)

        self.combo_cols = QComboBox()
        self.combo_cols.setStyleSheet("""
            QComboBox {
                background-color: rgba(0, 0, 0, 100);
                color: #00FF00;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px;
            }
            QComboBox:disabled { color: #555; border: 1px solid #333; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #222;
                color: #00FF00;
                selection-background-color: #008800;
            }
        """)
        self.combo_cols.setDisabled(True)

        combo_layout.addWidget(self.lbl_combo)
        combo_layout.addWidget(self.combo_cols, 1)
        layout.addLayout(combo_layout)

        # 4. 新增：实时终端日志框 (统一为终端绿代码流风格)
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
        self.log_console.setText("等待初始化拆分指令 (将根据指定列精准切分数据并保存)...\n")
        layout.addWidget(self.log_console)

        # 5. 核心执行按钮 (统一为镂空霓虹绿特效)
        self.btn_start = QPushButton("🚀 一键执行拆分")
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
            QPushButton:hover { background-color: rgba(0, 255, 0, 30); }
            QPushButton:disabled { color: #555; border: 1px solid #555; background-color: transparent; }
        """)
        self.btn_start.setDisabled(True)
        self.btn_start.clicked.connect(self.start_split)

        layout.addWidget(self.btn_start, 0, Qt.AlignCenter)

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "请选择需要拆分的总表 Excel 文件",
            "",
            "Excel 电子表格 (*.xlsx *.xls)"
        )
        if file_path:
            self.entry_file.setText(file_path)
            self.log_console.append(f"\n>_ 锁定源数据表: {file_path}")
            self.log_console.moveCursor(QTextCursor.End)

            try:
                # 瞬间读取表头
                df_headers = pd.read_excel(file_path, nrows=0)
                columns = list(df_headers.columns.astype(str))

                self.combo_cols.clear()
                self.combo_cols.addItems(columns)
                self.combo_cols.setDisabled(False)
                self.btn_start.setDisabled(False)

                self.log_console.append(f">_ 成功解析表头，共找到 {len(columns)} 个可选拆分依据。")
                self.log_console.moveCursor(QTextCursor.End)

            except Exception as e:
                self.log_console.append(f"❌ 读取失败: {e}")
                QMessageBox.critical(self, "读取失败",
                                     f"无法解析该表格的列名，请检查文件是否被打开占用！\n\n报错详情: {e}")
                self.combo_cols.clear()
                self.combo_cols.setDisabled(True)
                self.btn_start.setDisabled(True)

    def start_split(self):
        file_path = self.entry_file.text().strip()
        split_col = self.combo_cols.currentText()

        if not file_path or not split_col:
            QMessageBox.warning(self, "操作提示", "请先选择要拆分的文件，并在下拉框中指定列名！")
            return

        self.btn_start.setText("⚙️ 引擎切割中...")
        self.btn_start.setDisabled(True)
        self.combo_cols.setDisabled(True)
        self.btn_browse.setDisabled(True)

        self.log_console.clear()
        self.log_console.append(f"🚀 启动切割引擎，拆分依据列:【{split_col}】\n" + "-" * 40)
        QApplication.processEvents()

        try:
            self.log_console.append("⏳ 正在将表格全量数据装载进内存，请稍候...")
            QApplication.processEvents()

            df = pd.read_excel(file_path)

            if split_col not in df.columns:
                self.log_console.append(f"❌ 严重错误: 表格中找不到列名 '{split_col}'。")
                QMessageBox.critical(self, "列名错误", f"表格中找不到列名 '{split_col}'，请重新选择！")
                self.reset_button()
                return

            base_dir = os.path.dirname(file_path)
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            output_dir = os.path.join(base_dir, f"{base_name}_按【{split_col}】拆分结果")

            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            grouped = df.groupby(split_col, dropna=False)
            success_count = 0
            error_count = 0

            self.log_console.append(f"✅ 装载完毕，共读取 {len(df)} 行数据。准备执行分组散列导出...")
            QApplication.processEvents()

            for name, group in grouped:
                safe_name = clean_filename(name)
                output_file_path = os.path.join(output_dir, f"{safe_name}.xlsx")

                self.log_console.append(f"[*] 正在导出子组: {safe_name} ({len(group)} 行)...")
                self.log_console.moveCursor(QTextCursor.End)
                QApplication.processEvents()

                try:
                    group.to_excel(output_file_path, index=False)
                    success_count += 1
                except Exception as e:
                    error_count += 1
                    self.log_console.append(f"❌ 生成失败: {safe_name}.xlsx | 报错: {e}")

            self.log_console.append("-" * 40)
            self.log_console.append(f"🎉 拆分完毕！成功: {success_count} 个，失败: {error_count} 个。")
            self.log_console.append(f"📁 保存目录: {output_dir}")
            self.log_console.moveCursor(QTextCursor.End)

            msg = f"✅ 拆分顺利完成！\n\n共按【{split_col}】拆分出 {success_count} 个独立 Excel 文件。\n📁 全部保存在原表所在目录的专属文件夹中。"
            if error_count > 0:
                msg += f"\n\n⚠️ 另有 {error_count} 个分组因特殊符号或未知原因保存失败。"

            QMessageBox.information(self, "拆分成功", msg)

        except Exception as e:
            self.log_console.append(f"❌ 运行异常: {e}")
            QMessageBox.critical(self, "运行异常", f"拆分过程中发生崩溃，请检查原表数据或是否被占用！\n\n报错详情: {e}")
        finally:
            self.reset_button()

    def reset_button(self):
        self.btn_start.setText("🚀 一键执行拆分")
        self.btn_start.setDisabled(False)
        self.combo_cols.setDisabled(False)
        self.btn_browse.setDisabled(False)
        self.log_console.moveCursor(QTextCursor.End)


# =================================================================
# 独立调试机制
# =================================================================
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
    window.setWindowTitle("Excel 总表条件拆分 - 独立调试模式")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    # 加高了窗口以便容纳新增的终端日志框
    window.resize(600, 450)
    window.show()
    sys.exit(app.exec())