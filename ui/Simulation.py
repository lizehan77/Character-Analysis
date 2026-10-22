import os
import sys
import json
import re
import subprocess
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton, QLineEdit)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path: sys.path.append(BASE_DIR)
from worker_launch import launch_worker


class ChatWorker(QThread):
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(str)

    def __init__(self, folder_path, history_list):
        super().__init__()
        self.folder_path = folder_path
        self.history_json = json.dumps(history_list, ensure_ascii=False)

    def run(self):
        try:
            worker_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "simulate_worker.py")
            proc = worker_launch.launch_worker(worker_path, [self.folder_path, self.history_json],
                                               encoding="utf-8", errors="replace", bufsize=1)
            chunks = []
            for line in proc.stdout:  # 流式读取，实时回显进度
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
                self.error_signal.emit("未知错误：\n" + out)
        except Exception as e:
            self.error_signal.emit(str(e))


class SimulationPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_user_path = ""
        self.worker = None
        self.chat_history = []
        self.moni_file = ""
        self.typing_label = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = QWidget()
        top_bar.setFixedHeight(44)
        top_bar.setStyleSheet("border-bottom: 1px solid #eaedf1; background-color: #ffffff;")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(15, 0, 15, 0)

        self.path_label = QLabel("🗣️ 模拟微信对话")
        self.path_label.setStyleSheet("font-size: 14px; color: #1a1a1a; border: none; font-weight: bold;")
        top_bar_layout.addWidget(self.path_label)
        top_bar_layout.addStretch()

        self.clear_btn = QPushButton("🗑 清空上下文")
        self.clear_btn.setFixedHeight(24)
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setStyleSheet(
            "QPushButton { background-color: #fff; color: #dc3545; border: 1px solid #dc3545; border-radius: 4px; padding: 0 10px; font-size: 11px; font-weight: bold;} QPushButton:hover { background-color: #ffe6e6; }")
        self.clear_btn.clicked.connect(self.clear_chat)
        top_bar_layout.addWidget(self.clear_btn)
        layout.addWidget(top_bar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: #f4f6f9; }")

        self.chat_container = QWidget()
        self.chat_container.setStyleSheet("background-color: #f4f6f9;")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(20, 15, 20, 15)
        self.chat_layout.setSpacing(12)
        self.chat_layout.addStretch()

        self.scroll_area.setWidget(self.chat_container)
        layout.addWidget(self.scroll_area, 1)

        bottom_bar = QWidget()
        bottom_bar.setFixedHeight(50)
        bottom_bar.setStyleSheet("background-color: #ffffff; border-top: 1px solid #eaedf1;")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(20, 8, 20, 8)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("输入你想对TA说的话...")
        self.input_field.setStyleSheet(
            "QLineEdit { border: 1px solid #ddd; border-radius: 14px; padding: 6px 12px; font-size: 12px; background-color: #f8f9fa; }")
        self.input_field.returnPressed.connect(self.send_message)

        self.send_btn = QPushButton("发送")
        self.send_btn.setFixedSize(60, 28)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setStyleSheet(
            "QPushButton { background-color: #07c160; color: white; border: none; border-radius: 4px; font-weight: bold; font-size: 12px; } QPushButton:hover { background-color: #06ad56; } QPushButton:disabled { background-color: #9be3b6; }")
        self.send_btn.clicked.connect(self.send_message)

        bottom_layout.addWidget(self.input_field)
        bottom_layout.addWidget(self.send_btn)
        layout.addWidget(bottom_bar)

    def load_simulation_data(self, user_folder_path):
        self.current_user_path = user_folder_path
        self.moni_file = os.path.join(self.current_user_path, "moni_ltjl.txt")
        self.chat_history = []

        if os.path.exists(self.moni_file):
            with open(self.moni_file, "r", encoding="utf-8") as f:
                for line in f.readlines():
                    line = line.strip()
                    if line.startswith("我: "):
                        self.chat_history.append({"role": "user", "content": line[3:]})
                    elif line.startswith("TA: "):
                        self.chat_history.append({"role": "assistant", "content": line[4:]})
        self.render_history()

    def render_history(self):
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        if not self.chat_history:
            self.append_system_message("系统已读取设定，开始聊天吧。")
        else:
            for msg in self.chat_history:
                self.append_bubble(msg["content"], msg["role"] == "user")

    def save_to_moni(self, role, text):
        if not self.moni_file: return
        prefix = "我: " if role == "user" else "TA: "
        with open(self.moni_file, "a", encoding="utf-8") as f: f.write(f"\n{prefix}{text}\n")

    def clear_chat(self):
        self.chat_history = []
        self.render_history()
        if self.moni_file and os.path.exists(self.moni_file):
            with open(self.moni_file, "r", encoding="utf-8") as f:
                base_setting = f.read().split("我:", 1)[0].strip()
            with open(self.moni_file, "w", encoding="utf-8") as f:
                if base_setting: f.write(base_setting + "\n\n")
        self.append_system_message("上下文已清空，重头再来。")

    def append_system_message(self, text):
        msg_label = QLabel(text)
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setStyleSheet("color: #888; font-size: 11px; margin: 5px 0;")
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, msg_label)

    def append_bubble(self, text, is_user):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bubble.setMaximumWidth(500)

        avatar = QLabel("我" if is_user else "TA")
        avatar.setFixedSize(30, 30)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(
            f"background-color: {'#95ec69' if is_user else '#ffffff'}; border-radius: 6px; border: {'none' if is_user else '1px solid #ddd'}; color: {'#000' if is_user else '#333'}; font-weight: bold; font-size: 11px;")

        if is_user:
            bubble.setStyleSheet(
                "background-color: #95ec69; padding: 10px; border-radius: 8px; font-size: 12px; color: #000; line-height: 1.4;")
            row_layout.addStretch()
            row_layout.addWidget(bubble)
            row_layout.addWidget(avatar, alignment=Qt.AlignTop)
        else:
            bubble.setStyleSheet(
                "background-color: #ffffff; padding: 10px; border-radius: 8px; font-size: 12px; color: #000; border: 1px solid #eaedf1; line-height: 1.4;")
            row_layout.addWidget(avatar, alignment=Qt.AlignTop)
            row_layout.addWidget(bubble)
            row_layout.addStretch()

        self.chat_layout.insertWidget(self.chat_layout.count() - 1, row_widget)
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()))

    def send_message(self):
        if not self.current_user_path: return
        text = self.input_field.text().strip()
        if not text: return

        self.input_field.clear()
        self.append_bubble(text, is_user=True)
        self.chat_history.append({"role": "user", "content": text})
        self.save_to_moni("user", text)

        self.send_btn.setEnabled(False)
        self.input_field.setEnabled(False)
        self.send_btn.setText("...")

        typing_label = QLabel("TA 正在输入...")
        typing_label.setAlignment(Qt.AlignCenter)
        typing_label.setStyleSheet("color: #888; font-size: 11px;")
        typing_label.setObjectName("typing_indicator")
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, typing_label)
        self.typing_label = typing_label
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()))

        self.worker = ChatWorker(self.current_user_path, self.chat_history)
        self.worker.finished_signal.connect(self.on_chat_finished)
        self.worker.error_signal.connect(self.on_chat_error)
        self.worker.progress_signal.connect(self.on_progress)
        self.worker.start()

    def on_progress(self, msg):
        if self.typing_label is not None:
            self.typing_label.setText(msg)

    def on_chat_finished(self, reply):
        self.send_btn.setEnabled(True)
        self.input_field.setEnabled(True)
        self.send_btn.setText("发送")
        self.input_field.setFocus()

        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if item.widget() and item.widget().objectName() == "typing_indicator":
                item.widget().deleteLater()
                break
        self.typing_label = None  # 标签已销毁，避免后续 on_progress 访问悬空引用

        reply = re.sub(r'\x1b\[[0-9;]*m', '', reply).replace("[0m", "").replace("\x1b", "")

        current_nickname = os.path.basename(self.current_user_path)
        if current_nickname:
            reply = reply.replace(current_nickname, "对方").replace("【对方】", "对方")
        reply = reply.replace("胡萝贝", "对方").replace("Let me say", "对方")

        self.append_bubble(reply, is_user=False)
        self.chat_history.append({"role": "assistant", "content": reply})
        self.save_to_moni("assistant", reply)

    def on_chat_error(self, error_msg):
        self.send_btn.setEnabled(True)
        self.input_field.setEnabled(True)
        self.send_btn.setText("发送")
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if item.widget() and item.widget().objectName() == "typing_indicator":
                item.widget().deleteLater()
                break
        self.append_system_message(f"❌ 错误: {error_msg}")