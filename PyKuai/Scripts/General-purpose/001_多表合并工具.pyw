# -*- coding: utf-8 -*-
import os
import pandas as pd
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QFileDialog, QMessageBox, QApplication)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QFont


class PluginWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setSpacing(15)

        title_lbl = QLabel("Excel 同表头多表无损合并引擎")
        title_lbl.setStyleSheet("color: #00FFFF; font-size: 22px; font-weight: bold; font-family: 'Microsoft YaHei';")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        desc_lbl = QLabel("✅ 智能对齐消除表头空格 | ✅ 强制锁定长数字(防手机号丢失)")
        desc_lbl.setStyleSheet("color: #AAAAAA; font-size: 13px;")
        desc_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_lbl)

        layout.addSpacing(10)

        folder_layout = QHBoxLayout()
        self.lbl_folder = QLabel("待合并文件夹:")
        self.lbl_folder.setStyleSheet("color: #E0E0E0; font-size: 14px; font-weight: bold;")

        self.entry_folder = QLineEdit()
        self.entry_folder.setPlaceholderText("请选择存放待合并 Excel 的文件夹路径...")
        self.entry_folder.setStyleSheet("""
            QLineEdit { background-color: rgba(0, 0, 0, 100); color: #00FF00; border: 1px solid #555; border-radius: 5px; padding: 8px; font-family: Consolas; }
            QLineEdit:focus { border: 1px solid #00FF00; }
        """)

        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        self.btn_browse.setStyleSheet(
            "QPushButton { background-color: #444; color: white; border-radius: 5px; padding: 8px 15px; font-weight: bold; } QPushButton:hover { background-color: #666; }")
        self.btn_browse.clicked.connect(self.select_folder)

        folder_layout.addWidget(self.lbl_folder)
        folder_layout.addWidget(self.entry_folder)
        folder_layout.addWidget(self.btn_browse)
        layout.addLayout(folder_layout)

        self.btn_start = QPushButton("🚀 开始一键合并")
        self.btn_start.setFixedSize(220, 45)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: #111; font-weight: bold; font-size: 15px; border-radius: 6px; } QPushButton:hover { background-color: #45a049; } QPushButton:disabled { background-color: #2e6030; color: #888; }")
        self.btn_start.clicked.connect(self.start_merge)

        layout.addWidget(self.btn_start, 0, Qt.AlignCenter)
        layout.addStretch()

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "请选择存放待合并Excel的文件夹")
        if folder_path:
            self.entry_folder.setText(folder_path)

    def start_merge(self):
        folder_path = self.entry_folder.text().strip()

        if not folder_path:
            QMessageBox.warning(self, "操作提示", "请先选择存放待合并Excel的文件夹！")
            return

        self.btn_start.setText("正在拼命合并中...")
        self.btn_start.setDisabled(True)
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
                    except Exception as e:
                        # 【防御性编程核心】：绝不静默吞并异常，将真实报错信息强制入列
                        error_files.append((file, str(e)))

            if all_data:
                merged_df = pd.concat(all_data, ignore_index=True)
                merged_df.fillna("", inplace=True)
                output_file_path = os.path.join(folder_path, "汇总表_合并结果.xlsx")
                merged_df.to_excel(output_file_path, index=False)

                msg = f"✅ 合并圆满完成！\n\n共读取了 {file_count} 个文件，总计合并 {len(merged_df)} 行数据。\n专家的专长、联系电话等长数字均已安全锁定格式防丢失。\n\n汇总表已安全保存至该文件夹下。"
                if error_files:
                    msg += f"\n\n⚠️ 另有 {len(error_files)} 个文件因异常被跳过。\n典型的报错如: {error_files[0][1]}"
                QMessageBox.information(self, "合并成功", msg)
            else:
                err_msg = "任务结束：没有提取到任何有效数据。\n请检查该文件夹下是否有合法的 Excel 文件，或者表格是否全为空。"
                # 如果真的是因为缺少包导致的崩溃，这里会直接弹窗展示具体死因
                if error_files:
                    err_msg += f"\n\n🚨 发现底层致命崩溃！\n后台尝试读取时发生了 {len(error_files)} 次异常。\n首个报错文件: {error_files[0][0]}\n报错详情: {error_files[0][1]}"
                QMessageBox.warning(self, "合并失败", err_msg)

        except Exception as e:
            QMessageBox.critical(self, "运行异常",
                                 f"保存失败！\n提示：请检查目标文件夹是否有写入权限，或者“汇总表_合并结果.xlsx”是否正被 Excel 软件占用。\n\n报错详情: {e}")

        finally:
            self.btn_start.setText("🚀 开始一键合并")
            self.btn_start.setDisabled(False)


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.abspath(os.path.join(current_dir, "../..", "imgs", "script.ico"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = PluginWidget()
    window.setWindowTitle("Excel 多表一键合并工具 - 独立调试模式")
    window.setStyleSheet("background-color: rgba(20, 20, 20, 245);")
    window.resize(600, 250)
    window.show()
    sys.exit(app.exec())