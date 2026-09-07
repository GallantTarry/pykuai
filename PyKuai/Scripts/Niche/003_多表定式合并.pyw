# -*- coding: utf-8 -*-
import os
import pandas as pd
from openpyxl.styles import Alignment, Font, Border, Side
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QFileDialog, QMessageBox, QApplication, QTextEdit)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon


# =================================================================
# 后台异步合并线程：处理纯净数据截取与基础边框绘制
# =================================================================
class MergeWorker(QThread):
    log_signal = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(self, input_dir, output_file):
        super().__init__()
        self.input_dir = input_dir
        self.output_file = output_file

        # 强制标准化的 20 列定式表头
        self.target_columns = [
            "序号", "标包号", "物料编码", "规格及描述", "参考数量（只）", "品牌要求",
            "有偏差的应答规格型号", "*人民币60天账期单价（元）", "*正常交货期（周）",
            "*原厂最小包装数量", "*原厂最小起订数量", "*原厂包装方式",
            "*生命周期（即将停产/已停产）", "*原厂质保期（年）", "*是否接收承兑（是/否）",
            "型号偏差说明", "渠道性质", "备注", "应答单位", "应答轮次"
        ]

    def run(self):
        try:
            # 过滤掉隐藏文件和非 Excel 文件[cite: 27]
            files = [f for f in os.listdir(self.input_dir) if f.endswith(('.xlsx', '.xls')) and not f.startswith('~')]

            if not files:
                self.finished_signal.emit(False, "目标文件夹中没有找到有效的 Excel 文件！")
                return

            df_list = []
            for idx, file in enumerate(files):
                file_path = os.path.join(self.input_dir, file)
                self.log_signal.emit(f"[*] 正在解析 ({idx + 1}/{len(files)}): {file}")

                # 核心规则：跳过前 4 行，将原表的第 5 行（索引4）作为数据列名，且只读取前 20 列
                df = pd.read_excel(file_path, header=4, usecols=range(20))

                # 强制覆盖表头，防止不同文件表头存在细微错别字导致错位
                df.columns = self.target_columns

                # 剔除全空的无效行，防止空数据污染[cite: 27]
                df.dropna(how='all', inplace=True)
                df_list.append(df)

            self.log_signal.emit("\n>>> 数据读取完毕，正在执行底层垂直拼接...")

            # 拼接所有表格的数据部分[cite: 27]
            final_df = pd.concat(df_list, ignore_index=True)

            self.log_signal.emit(">>> 拼接完成，正在重绘全局格式与边框...")

            # 使用 openpyxl 引擎写入，以便后续操作单元格格式[cite: 27]
            with pd.ExcelWriter(self.output_file, engine='openpyxl') as writer:
                # 纯净版：不再需要预留空行，直接从第1行（索引0）开始写入数据[cite: 27]
                final_df.to_excel(writer, sheet_name='Sheet1', index=False, startrow=0)

                worksheet = writer.sheets['Sheet1']
                max_row = worksheet.max_row
                max_col = worksheet.max_column

                # 加粗首行表头并居中
                for col in range(1, max_col + 1):
                    cell = worksheet.cell(row=1, column=col)
                    cell.font = Font(bold=True)
                    cell.alignment = Alignment(horizontal='center', vertical='center')

                # ================= 添加全局边框样式 =================[cite: 27]
                thin_border = Border(left=Side(style='thin'),
                                     right=Side(style='thin'),
                                     top=Side(style='thin'),
                                     bottom=Side(style='thin'))

                # 遍历所有使用到的单元格，统一画上细边框[cite: 27]
                for row in worksheet.iter_rows(min_row=1, max_row=max_row, min_col=1, max_col=max_col):
                    for cell in row:
                        cell.border = thin_border

            self.finished_signal.emit(True,
                                      f"✅ 处理完毕！\n\n共合并 {len(files)} 份文件，生成 {len(final_df)} 行有效明细数据。")

        except Exception as e:
            self.finished_signal.emit(False, f"合并过程中发生异常，请检查文件是否被打开占用！\n\n报错详情: {str(e)}")


# =================================================================
# 核心规范：必须名为 PluginWidget 并继承自 QWidget[cite: 27]
# =================================================================
class PluginWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setSpacing(15)

        # 1. 标题[cite: 27]
        title_lbl = QLabel("纯净版询价明细自动拼接器")
        title_lbl.setStyleSheet("color: #00FFFF; font-size: 22px; font-weight: bold; font-family: 'Microsoft YaHei';")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        # 2. 输入文件夹选择区[cite: 27]
        input_layout = QHBoxLayout()
        self.lbl_input = QLabel("待合并的文件夹:")
        self.lbl_input.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_input.setFixedWidth(120)

        self.entry_input = QLineEdit()
        self.entry_input.setReadOnly(True)
        self.entry_input.setPlaceholderText("请选择包含多个源 Excel 文件的文件夹...")
        self.entry_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(0, 0, 0, 100);
                color: #00FF00;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px;
                font-family: Consolas;
            }
        """)

        self.btn_input = QPushButton("选择目录")
        self.btn_input.setCursor(Qt.PointingHandCursor)
        self.style_browse_btn(self.btn_input)
        self.btn_input.clicked.connect(self.select_input_dir)

        input_layout.addWidget(self.lbl_input)
        input_layout.addWidget(self.entry_input)
        input_layout.addWidget(self.btn_input)
        layout.addLayout(input_layout)

        # 3. 输出文件路径选择区[cite: 27]
        output_layout = QHBoxLayout()
        self.lbl_output = QLabel("生成总表保存至:")
        self.lbl_output.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_output.setFixedWidth(120)

        self.entry_output = QLineEdit()
        self.entry_output.setReadOnly(True)
        self.entry_output.setPlaceholderText("请指定合并后 Excel 总表的保存位置与文件名...")
        self.entry_output.setStyleSheet(self.entry_input.styleSheet())

        self.btn_output = QPushButton("另存为...")
        self.btn_output.setCursor(Qt.PointingHandCursor)
        self.style_browse_btn(self.btn_output)
        self.btn_output.clicked.connect(self.select_output_file)

        output_layout.addWidget(self.lbl_output)
        output_layout.addWidget(self.entry_output)
        output_layout.addWidget(self.btn_output)
        layout.addLayout(output_layout)

        # 4. 透明实时日志区[cite: 27]
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("""
            QTextEdit {
                background-color: rgba(0, 0, 0, 100);
                color: #A9B7C6;
                border: 1px solid #444;
                border-radius: 5px;
                padding: 10px;
                font-family: Consolas, 'Microsoft YaHei';
                font-size: 13px;
            }
        """)
        self.log_area.append(
            ">_ 纯净版拼接引擎已就绪...\n>_ 执行规则：\n  1. 彻底切除前 4 行无关结构\n  2. 提取第 5 行作为规范表头 (共 20 列)\n  3. 提取第 6 行及以下所有数据垂直堆叠\n  4. 生成清爽数据源并重绘全局表格边框。")
        layout.addWidget(self.log_area)

        # 5. 核心执行按钮[cite: 27]
        self.btn_start = QPushButton("🚀 开始提取与拼接")
        self.btn_start.setFixedSize(260, 45)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setStyleSheet("""
            QPushButton { 
                background-color: #FF9800; 
                color: #111; 
                font-weight: bold; 
                font-size: 15px; 
                border-radius: 6px; 
            }
            QPushButton:hover { background-color: #F57C00; }
            QPushButton:disabled { background-color: #885A20; color: #888; }
        """)
        self.btn_start.clicked.connect(self.start_merge)

        layout.addWidget(self.btn_start, 0, Qt.AlignCenter)

    def style_browse_btn(self, btn):
        btn.setStyleSheet("""
            QPushButton { 
                background-color: #444; 
                color: white; 
                border-radius: 5px; 
                padding: 8px 15px; 
                font-weight: bold;
            }
            QPushButton:hover { background-color: #666; }
            QPushButton:disabled { background-color: #333; color: #777; }
        """)

    def select_input_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择包含 Excel 文件的文件夹")
        if dir_path:
            self.entry_input.setText(dir_path)
            self.log_area.append(f"\n>_ 锁定数据源目录: {dir_path}")

            if not self.entry_output.text():
                default_out = os.path.join(dir_path, "纯净版合并总表.xlsx")
                self.entry_output.setText(default_out)
                self.log_area.append(f">_ 自动配置默认输出路径: {default_out}")

    def select_output_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存合并后的文件",
            "纯净版合并总表.xlsx",
            "Excel 电子表格 (*.xlsx)"
        )
        if file_path:
            self.entry_output.setText(file_path)
            self.log_area.append(f">_ 锁定目标输出路径: {file_path}")

    def start_merge(self):
        input_dir = self.entry_input.text().strip()
        output_file = self.entry_output.text().strip()

        if not input_dir or not output_file:
            QMessageBox.warning(self, "操作提示", "请先选择输入文件夹和输出文件的保存路径！")
            return

        self.btn_start.setText("⏳ 正在纯净提取数据中...")
        self.btn_start.setDisabled(True)
        self.btn_input.setDisabled(True)
        self.btn_output.setDisabled(True)

        self.log_area.append("\n==============================================")
        self.log_area.append(">_ 引擎启动，开始执行纯净堆叠序列...")

        self.worker = MergeWorker(input_dir, output_file)
        self.worker.log_signal.connect(self.update_log)
        self.worker.finished_signal.connect(self.merge_finished)
        self.worker.start()

    def update_log(self, msg):
        self.log_area.append(msg)
        scrollbar = self.log_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def merge_finished(self, success, msg):
        self.btn_start.setText("🚀 开始提取与拼接")
        self.btn_start.setDisabled(False)
        self.btn_input.setDisabled(False)
        self.btn_output.setDisabled(False)

        self.log_area.append(msg)
        self.log_area.append("==============================================\n")

        if success:
            QMessageBox.information(self, "拼接成功", msg)
        else:
            QMessageBox.critical(self, "运行异常", msg)


# =================================================================
# 独立调试机制[cite: 27]
# =================================================================
if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.abspath(os.path.join(current_dir, "../..", "imgs", "script.ico"))

    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = PluginWidget()
    window.setWindowTitle("纯净数据合并 - 独立调试模式")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    window.resize(650, 420)
    window.show()
    sys.exit(app.exec())