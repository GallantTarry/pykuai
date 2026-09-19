# -*- coding: utf-8 -*-
import os
import pandas as pd
from openpyxl.styles import Alignment, Font, Border, Side
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QFileDialog, QMessageBox, QApplication, QTextEdit)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QFont, QFontDatabase, QTextCursor


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
        current_file = "未知文件"  # 新增：用于追踪当前正在处理的文件名
        try:
            # 过滤掉隐藏文件和非 Excel 文件
            files = [f for f in os.listdir(self.input_dir) if f.endswith(('.xlsx', '.xls')) and not f.startswith('~')]

            if not files:
                self.finished_signal.emit(False, "目标文件夹中没有找到有效的 Excel 文件！")
                return

            df_list = []
            for idx, file in enumerate(files):
                current_file = file  # 每次循环更新当前文件名，一旦后续崩溃就是它的锅
                file_path = os.path.join(self.input_dir, file)
                self.log_signal.emit(f"⏳ 正在解析 [{idx + 1}/{len(files)}]: {file}")

                # 1. 初始读取：不再预设 usecols，防止列数不足直接崩溃引发 out-of-bounds
                df_raw = pd.read_excel(file_path, header=None)

                # 将列数安全地统一调整为 20 列（多余的列丢弃，不足20列的自动用空值补齐）
                df_raw = df_raw.reindex(columns=range(20))

                header_index = -1

                # 2. 动态扫描：在前 30 行中寻找包含特定特征词的行作为真实表头
                search_limit = min(30, len(df_raw))
                for i in range(search_limit):
                    # 将这一行的所有非空值拼接成字符串，方便判断
                    row_values = [str(val).strip() for val in df_raw.iloc[i].values if pd.notna(val)]
                    row_str = "".join(row_values)

                    # 只要这一行同时包含这几个核心词，我们就认定它是表头所在行
                    if "物料编码" in row_str and "标包号" in row_str and "规格及描述" in row_str:
                        header_index = i
                        break

                # 3. 容错处理：如果没有检测到表头
                if header_index == -1:
                    self.log_signal.emit(f"❌ 报错跳过: {file} 未能在前 {search_limit} 行检测到标准表头！")
                    continue

                # 4. 数据截取：提取表头下方的数据，并应用标准列名
                df = df_raw.iloc[header_index + 1:].copy()
                df.columns = self.target_columns

                # 5. 剔除全空的无效行，防止空数据污染
                df.dropna(how='all', inplace=True)

                # 如果该文件只有表头没有数据，也可以选择跳过
                if not df.empty:
                    df_list.append(df)
                    self.log_signal.emit(f"✅ 提取成功: {file} (提取行数: {len(df)})")
                else:
                    self.log_signal.emit(f"⚠️ 警告抛弃: {file} 中只有表头，未包含实际明细数据。")

            self.log_signal.emit("-" * 40)
            self.log_signal.emit("🔄 数据读取完毕，正在执行底层垂直堆叠...")

            # 拼接所有表格的数据部分
            final_df = pd.concat(df_list, ignore_index=True)

            self.log_signal.emit("🖌️ 堆叠完成，正在重绘全局格式与边框线...")

            # 使用 openpyxl 引擎写入，以便后续操作单元格格式
            with pd.ExcelWriter(self.output_file, engine='openpyxl') as writer:
                # 纯净版：不再需要预留空行，直接从第1行（索引0）开始写入数据
                final_df.to_excel(writer, sheet_name='Sheet1', index=False, startrow=0)

                worksheet = writer.sheets['Sheet1']
                max_row = worksheet.max_row
                max_col = worksheet.max_column

                # 加粗首行表头并居中
                for col in range(1, max_col + 1):
                    cell = worksheet.cell(row=1, column=col)
                    cell.font = Font(bold=True)
                    cell.alignment = Alignment(horizontal='center', vertical='center')

                # ================= 添加全局边框样式 =================
                thin_border = Border(left=Side(style='thin'),
                                     right=Side(style='thin'),
                                     top=Side(style='thin'),
                                     bottom=Side(style='thin'))

                # 遍历所有使用到的单元格，统一画上细边框
                for row in worksheet.iter_rows(min_row=1, max_row=max_row, min_col=1, max_col=max_col):
                    for cell in row:
                        cell.border = thin_border

            self.log_signal.emit("-" * 40 + "\n🎉 纯净定式合并行动执行完毕！")
            self.finished_signal.emit(True,
                                      f"✅ 处理完毕！\n\n共合并 {len(files)} 份文件，生成 {len(final_df)} 行有效明细数据。")

        except Exception as e:
            self.log_signal.emit(f"❌ 底层调度崩溃: 处理表【{current_file}】时发生异常！\n{str(e)}")
            self.finished_signal.emit(False, f"处理表【{current_file}】时发生异常！请检查文件格式。\n\n报错详情: {str(e)}")


# =================================================================
# 核心规范：必须名为 PluginWidget 并继承自 QWidget
# =================================================================
class PluginWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setSpacing(15)

        # 1. 标题 (统一为极客橙 #FF9800)
        title_lbl = QLabel("纯净版询价明细自动拼接器")
        title_lbl.setStyleSheet("color: #FF9800; font-size: 22px; font-weight: bold;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        # 2. 输入文件夹选择区
        input_layout = QHBoxLayout()
        self.lbl_input = QLabel("待合并战区:")
        self.lbl_input.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_input.setFixedWidth(100)

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
            }
            QLineEdit:focus { border: 1px solid #00FF00; }
        """)

        self.btn_input = QPushButton("探测...")
        self.btn_input.setCursor(Qt.PointingHandCursor)
        self.style_browse_btn(self.btn_input)
        self.btn_input.clicked.connect(self.select_input_dir)

        input_layout.addWidget(self.lbl_input)
        input_layout.addWidget(self.entry_input)
        input_layout.addWidget(self.btn_input)
        layout.addLayout(input_layout)

        # 3. 输出文件路径选择区
        output_layout = QHBoxLayout()
        self.lbl_output = QLabel("导出工作区:")
        self.lbl_output.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")
        self.lbl_output.setFixedWidth(100)

        self.entry_output = QLineEdit()
        self.entry_output.setReadOnly(True)
        self.entry_output.setPlaceholderText("请指定合并后 Excel 总表的保存位置与文件名...")
        self.entry_output.setStyleSheet(self.entry_input.styleSheet())

        self.btn_output = QPushButton("指定...")
        self.btn_output.setCursor(Qt.PointingHandCursor)
        self.style_browse_btn(self.btn_output)
        self.btn_output.clicked.connect(self.select_output_file)

        output_layout.addWidget(self.lbl_output)
        output_layout.addWidget(self.entry_output)
        output_layout.addWidget(self.btn_output)
        layout.addLayout(output_layout)

        # 4. 透明实时日志区 (统一终端绿与滚动光标)
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
        self.log_console.setText(
            "等待初始化堆叠指令...\n"
            ">_ 执行准则：\n"
            "  1. 动态寻址定位 [物料编码] / [标包号] 物理表头锚点。\n"
            "  2. 提取锚点下方阵列数据并实施无缝堆叠。\n"
            "  3. 若前 30 帧未扫到有效表头，则触发熔断跳过。\n")
        layout.addWidget(self.log_console)

        # 5. 核心执行按钮 (统一镂空霓虹绿特效)
        self.btn_start = QPushButton("🚀 一键提取与拼接")
        self.btn_start.setFixedSize(260, 45)
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
        dir_path = QFileDialog.getExistingDirectory(self, "选择包含 Excel 文件的战区文件夹")
        if dir_path:
            self.entry_input.setText(dir_path)
            self.log_console.append(f"> 目标战区已锁定: {dir_path}")
            self.log_console.moveCursor(QTextCursor.End)

            if not self.entry_output.text():
                default_out = os.path.join(dir_path, "纯净版合并总表.xlsx")
                self.entry_output.setText(default_out)
                self.log_console.append(f"> 自动分配导出路径: {default_out}")
                self.log_console.moveCursor(QTextCursor.End)

    def select_output_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存合并后的文件",
            "纯净版合并总表.xlsx",
            "Excel 电子表格 (*.xlsx)"
        )
        if file_path:
            self.entry_output.setText(file_path)
            self.log_console.append(f"> 导出路径重新定向至: {file_path}")
            self.log_console.moveCursor(QTextCursor.End)

    def append_log(self, text):
        self.log_console.append(text)
        self.log_console.moveCursor(QTextCursor.End)

    def start_merge(self):
        input_dir = self.entry_input.text().strip()
        output_file = self.entry_output.text().strip()

        if not input_dir or not output_file:
            QMessageBox.warning(self, "权限拒绝", "请先选择目标战区和导出的存储路径！")
            return

        self.btn_start.setText("⚙️ 引擎堆叠提取中...")
        self.btn_start.setDisabled(True)
        self.btn_input.setDisabled(True)
        self.btn_output.setDisabled(True)

        self.log_console.clear()
        self.log_console.append("🚀 引擎启动，开始执行纯净堆叠序列...\n" + "-" * 40)
        self.log_console.moveCursor(QTextCursor.End)

        # 挂载后台工作线程
        self.worker = MergeWorker(input_dir, output_file)
        self.worker.log_signal.connect(self.append_log)
        self.worker.finished_signal.connect(self.on_merge_finished)
        self.worker.start()

    def on_merge_finished(self, success, msg):
        self.btn_start.setText("🚀 一键提取与拼接")
        self.btn_start.setDisabled(False)
        self.btn_input.setDisabled(False)
        self.btn_output.setDisabled(False)

        if success:
            QMessageBox.information(self, "深度任务简报", msg)
        else:
            QMessageBox.critical(self, "运行异常", msg)


# =================================================================
# 独立调试机制：主程序挂载时会被无视
# =================================================================
if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)

    current_dir = os.path.dirname(os.path.abspath(__file__))

    # 动态加载 ../../tools/zpix.ttf，保证单独运行测试时也是像素风
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
    window.setWindowTitle("纯净数据合并引擎 - 独立沙盒模式")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    window.resize(650, 450)
    window.show()
    sys.exit(app.exec())