import os
import subprocess
import sys
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTextEdit, QMessageBox, QComboBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path: sys.path.append(BASE_DIR)
from worker_launch import launch_worker


class SubProcessWorker(QThread):
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(str)

    def __init__(self, folder_path, mode):
        super().__init__()
        self.folder_path = folder_path
        self.mode = mode

    def run(self):
        try:
            worker_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "infer_worker.py")
            proc = worker_launch.launch_worker(worker_path, [self.folder_path, self.mode], encoding="utf-8",
                                               errors="replace", bufsize=1)
            chunks = []
            for line in proc.stdout:  # 流式读取，实时回显进度，避免"卡死"的错觉
                chunks.append(line)
                if "[PROGRESS]" in line:
                    self.progress_signal.emit(line.split("[PROGRESS]", 1)[-1].strip())
            proc.stdout.close()
            proc.wait()
            out = "".join(chunks)
            if proc.returncode != 0: self.error_signal.emit(out); return
            if "OK:" in out:
                self.finished_signal.emit(out.split("OK:", 1)[-1].strip())
            elif "ERR:" in out:
                self.error_signal.emit(out.split("ERR:", 1)[-1].strip())
            else:
                self.error_signal.emit("未知返回：\n" + out)
        except Exception as e:
            self.error_signal.emit(str(e))


class TrainPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_user_path = ""
        self.worker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = QWidget()
        top_bar.setFixedHeight(44)
        top_bar.setStyleSheet("border-bottom: 1px solid #eaedf1; background-color: #ffffff;")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(15, 0, 15, 0)

        title = QLabel("📚 历史记录训练中心")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #1a1a1a; border: none;")
        top_bar_layout.addWidget(title)
        top_bar_layout.addStretch()

        self.open_btn = QPushButton("📂 打开聊天记录")
        self.open_btn.setFixedHeight(24)
        self.open_btn.setCursor(Qt.PointingHandCursor)
        self.open_btn.setStyleSheet(
            "QPushButton { background-color: #f8f9fa; color: #4a90e2; border: 1px solid #4a90e2; border-radius: 4px; padding: 0 10px; font-size: 11px; font-weight: bold;} QPushButton:hover { background-color: #e6f0ff; }")
        self.open_btn.clicked.connect(self.open_chat_log)
        top_bar_layout.addWidget(self.open_btn)
        layout.addWidget(top_bar)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(15, 10, 15, 10)
        content_layout.setSpacing(8)

        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("请在此粘贴需要追加的聊天记录...")
        self.input_text.setStyleSheet(
            "QTextEdit { border: 1px solid #eaedf1; border-radius: 6px; padding: 10px; font-size: 12px; background-color: #ffffff; }")
        content_layout.addWidget(self.input_text, 3)

        action_layout = QHBoxLayout()
        action_layout.setSpacing(8)

        self.save_btn = QPushButton("💾 保存记录")
        self.save_btn.setFixedHeight(32)
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet(
            "QPushButton { background-color: #4a90e2; color: white; border-radius: 4px; font-weight: bold; font-size: 12px; } QPushButton:hover { background-color: #357abd; }")
        self.save_btn.clicked.connect(self.save_and_merge)
        action_layout.addWidget(self.save_btn, 2)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("仅分析新记录 (极速)", "new")
        self.mode_combo.addItem("分析全部记录 (较慢)", "all")
        self.mode_combo.setFixedHeight(32)
        self.mode_combo.setStyleSheet(
            "QComboBox { border: 1px solid #eaedf1; border-radius: 4px; padding: 0 10px; font-size: 12px; font-weight: bold; background-color: #ffffff; }")
        action_layout.addWidget(self.mode_combo, 1)
        content_layout.addLayout(action_layout)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(
            "QTextEdit { border: 1px solid #eaedf1; border-radius: 6px; padding: 10px; font-size: 11px; background-color: #fafbfc; color: #555; font-family: 'Consolas'; }")
        content_layout.addWidget(self.log_text, 2)

        self.run_btn = QPushButton("🧠 开始分析并更新画像")
        self.run_btn.setFixedHeight(36)
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.setStyleSheet(
            "QPushButton { background-color: #28a745; color: white; border-radius: 4px; font-weight: bold; font-size: 13px; } QPushButton:hover { background-color: #218838; } QPushButton:disabled { background-color: #a0c4eb; }")
        self.run_btn.clicked.connect(self.start_analysis)
        content_layout.addWidget(self.run_btn)

        layout.addWidget(content_widget, 1)

    def load_train_data(self, user_folder_path):
        self.current_user_path = user_folder_path
        self.input_text.clear()
        self.log_text.clear()
        self.log_text.append(f"✅ 已加载用户文件夹：\n{user_folder_path}\n准备就绪。")

    def open_chat_log(self):
        if not self.current_user_path: return
        ltjl_path = os.path.join(self.current_user_path, "ltjl.txt")
        if not os.path.exists(ltjl_path): open(ltjl_path, 'w').close()
        if sys.platform == "win32": os.startfile(ltjl_path)

    def save_and_merge(self):
        if not self.current_user_path: return
        text = self.input_text.toPlainText().strip()
        if not text: return
        with open(os.path.join(self.current_user_path, "ltjl.txt"), "a", encoding="utf-8") as f:
            f.write("\n" + text + "\n")
        with open(os.path.join(self.current_user_path, "new_ltjl.txt"), "a", encoding="utf-8") as f:
            f.write("\n" + text + "\n")
        self.log_text.append(f"💾 成功保存记录。")
        self.input_text.clear()

    def start_analysis(self):
        if not self.current_user_path: return
        mode = self.mode_combo.currentData()
        self.run_btn.setEnabled(False)
        self.run_btn.setText("⏳ 分析中...")
        self.log_text.append("⏳ 正在启动后台分析进程...")
        self.worker = SubProcessWorker(self.current_user_path, mode)
        self.worker.finished_signal.connect(self.on_analysis_finished)
        self.worker.error_signal.connect(self.on_analysis_error)
        self.worker.progress_signal.connect(self.on_analysis_progress)
        self.worker.start()

    def on_analysis_progress(self, msg):
        self.log_text.append(msg)

    def on_analysis_finished(self, result):
        self.run_btn.setEnabled(True)
        self.run_btn.setText("🧠 开始分析并更新画像")
        self.log_text.append("✅ 分析完成！画像已更新。")
        # 两种模式都要清空：跑过"分析全部"后再切"仅新记录"，必须丢弃已并入全量记录的内容
        open(os.path.join(self.current_user_path, "new_ltjl.txt"), 'w').close()

    def on_analysis_error(self, error_msg):
        self.run_btn.setEnabled(True)
        self.run_btn.setText("🧠 开始分析并更新画像")
        self.log_text.append(f"❌ 错误：\n{error_msg}")