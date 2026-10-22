import os
import sys
import json
import re
import subprocess
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QMessageBox,
                             QScrollArea, QApplication, QFrame, QProgressBar)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path: sys.path.append(BASE_DIR)
from worker_launch import launch_worker


class AdvisorWorker(QThread):
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(str)

    def __init__(self, folder_path, chat_history):
        super().__init__()
        self.folder_path = folder_path
        self.chat_json = json.dumps(chat_history, ensure_ascii=False)

    def run(self):
        try:
            worker_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "realtime_worker.py")
            proc = worker_launch.launch_worker(worker_path, [self.folder_path, self.chat_json],
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


class AdvisorPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_user_path = ""
        self.worker = None
        self.loading_label = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = QWidget()
        top_bar.setFixedHeight(44)
        top_bar.setStyleSheet("border-bottom: 1px solid #eaedf1; background-color: #ffffff;")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(15, 0, 15, 0)
        self.path_label = QLabel("🕵️ 实时聊天军师")
        self.path_label.setStyleSheet("font-size: 14px; color: #1a1a1a; border: none; font-weight: bold;")
        top_bar_layout.addWidget(self.path_label)
        layout.addWidget(top_bar)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(15, 10, 15, 10)
        content_layout.setSpacing(8)

        hint = QLabel("请粘贴刚发生的聊天记录（格式：我: xxx / 对方: xxx），结合画像帮你支招：")
        hint.setStyleSheet("color: #666; font-size: 12px;")
        content_layout.addWidget(hint)

        self.rt_input = QTextEdit()
        self.rt_input.setPlaceholderText("例如：\n对方: 今天上班好累啊\n我: 怎么啦？")
        self.rt_input.setStyleSheet(
            "QTextEdit { border: 1px solid #eaedf1; border-radius: 4px; padding: 10px; font-size: 12px; background-color: #ffffff; font-family: 'Microsoft YaHei'; }")
        self.rt_input.setMinimumHeight(80)
        self.rt_input.setMaximumHeight(120)
        content_layout.addWidget(self.rt_input)

        self.rt_btn = QPushButton("🔮 分析情绪并生成回复")
        self.rt_btn.setFixedHeight(32)
        self.rt_btn.setCursor(Qt.PointingHandCursor)
        self.rt_btn.setStyleSheet(
            "QPushButton { background-color: #6f42c1; color: white; border-radius: 4px; font-weight: bold; font-size: 12px; } QPushButton:hover { background-color: #59359a; } QPushButton:disabled { background-color: #b39ddb; }")
        self.rt_btn.clicked.connect(self.start_realtime_analysis)
        content_layout.addWidget(self.rt_btn)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")

        self.result_container = QWidget()
        self.result_container.setStyleSheet("background-color: transparent;")
        self.result_layout = QVBoxLayout(self.result_container)
        self.result_layout.setContentsMargins(0, 0, 0, 0)
        self.result_layout.setSpacing(8)
        self.result_layout.addStretch()

        self.scroll_area.setWidget(self.result_container)
        content_layout.addWidget(self.scroll_area, 1)

        layout.addWidget(content_widget, 1)

    def load_advisor_data(self, user_folder_path):
        self.current_user_path = user_folder_path
        self.rt_input.clear()
        self.clear_results()

    def clear_results(self):
        while self.result_layout.count() > 1:
            item = self.result_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def start_realtime_analysis(self):
        if not self.current_user_path: return
        raw_text = self.rt_input.toPlainText().strip()
        if not raw_text: return

        chat_history = []
        for line in raw_text.split("\n"):
            line = line.strip()
            if not line: continue
            if line.startswith("我:") or line.startswith("我："):
                chat_history.append({"role": "user", "content": line[2:].strip()})
            elif line.startswith("对方:") or line.startswith("对方："):
                chat_history.append({"role": "assistant", "content": line[3:].strip()})
            else:
                chat_history.append({"role": "assistant", "content": line})

        self.rt_btn.setEnabled(False)
        self.rt_btn.setText("⏳ 军师正在读心...")
        self.clear_results()

        loading_label = QLabel("正在结合人物画像深度分析，请稍候 (约 10-20 秒)...")
        loading_label.setAlignment(Qt.AlignCenter)
        loading_label.setStyleSheet("color: #888; font-size: 12px; margin-top: 20px;")
        self.result_layout.insertWidget(self.result_layout.count() - 1, loading_label)
        self.loading_label = loading_label

        self.worker = AdvisorWorker(self.current_user_path, chat_history)
        self.worker.finished_signal.connect(self.on_realtime_finished)
        self.worker.error_signal.connect(self.on_realtime_error)
        self.worker.progress_signal.connect(self.on_progress)
        self.worker.start()

    def on_progress(self, msg):
        if self.loading_label is not None:
            self.loading_label.setText(msg)

    def on_realtime_finished(self, result):
        self.rt_btn.setEnabled(True)
        self.rt_btn.setText("🔮 分析情绪并生成回复")
        self.clear_results()

        result = re.sub(r'\x1b\[[0-9;]*m', '', result).replace("[0m", "").replace("\x1b", "")
        current_nickname = os.path.basename(self.current_user_path)
        if current_nickname:
            result = result.replace(current_nickname, "对方").replace("【对方】", "对方")
        result = result.replace("胡萝贝", "对方").replace("Let me say", "对方")

        self.render_rich_result(result)

    def on_realtime_error(self, error_msg):
        self.rt_btn.setEnabled(True)
        self.rt_btn.setText("🔮 分析情绪并生成回复")
        self.clear_results()
        self.add_card("❌ 分析失败", error_msg, "#ffebee", "#c62828")

    def render_rich_result(self, raw_text):
        sections = re.split(r'###\s*', raw_text)
        for sec in sections:
            sec = sec.strip()
            if not sec: continue
            lines = sec.split("\n")
            title = lines[0].strip()
            content_lines = [l.strip() for l in lines[1:] if l.strip()]
            content = "\n".join(content_lines)

            content = content.replace("胡萝贝", "对方").replace("Let me say", "对方")

            if "好感度" in title:
                # 必须匹配「好感度: 数字」；抓不到就不展示，避免误取正文里的任意数字当成分数
                match = re.search(r'好感度\s*[：:]\s*\*{0,2}(\d{1,3})', content)
                if match:
                    self.add_score_card("💖 当前好感度", max(0, min(100, int(match.group(1)))))
            elif "情绪分析" in title:
                self.add_card("🔍 对方当前情绪分析", content, "#e3f2fd", "#1565c0")
            elif "策略" in title:
                self.add_card("💡 军师回复策略", content, "#fff3e0", "#e65100")
            elif "潜台词" in title:
                self.add_card("🎭 她的内心潜台词", content, "#f3e5f5", "#6a1b9a")
            elif "推荐回复" in title:
                self.render_reply_cards(content_lines)

    def add_score_card(self, title, score):
        card = QFrame()
        color = "#28a745" if score >= 70 else ("#ffc107" if score >= 40 else "#dc3545")
        card.setStyleSheet(
            f"QFrame {{ background-color: #ffffff; border-radius: 8px; border: 1px solid #eaedf1; border-left: 4px solid {color}; }}")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 12, 15, 15)

        header = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333; border: none;")
        score_label = QLabel(f"{score}%")
        score_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {color}; border: none;")
        header.addWidget(title_label)
        header.addStretch()
        header.addWidget(score_label)
        layout.addLayout(header)

        bar = QProgressBar()
        bar.setValue(score)
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        bar.setStyleSheet(
            f"QProgressBar {{ border: none; background-color: #f4f6f9; border-radius: 4px; }} QProgressBar::chunk {{ background-color: {color}; border-radius: 4px; }}")
        layout.addWidget(bar)
        self.result_layout.insertWidget(self.result_layout.count() - 1, card)

    def add_card(self, title, content, bg_color, title_color):
        if not content: return
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background-color: {bg_color}; border-radius: 6px; border: 1px solid {title_color}33; }}")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {title_color}; border: none; background: transparent;")
        card_layout.addWidget(title_label)

        text_label = QLabel(content)
        text_label.setWordWrap(True)
        text_label.setStyleSheet(
            "font-size: 12px; color: #333; line-height: 1.4; border: none; background: transparent;")
        card_layout.addWidget(text_label)

        self.result_layout.insertWidget(self.result_layout.count() - 1, card)

    def render_reply_cards(self, lines):
        header = QLabel("💬 军师推荐回复")
        header.setStyleSheet("font-size: 13px; font-weight: bold; color: #333; margin-top: 5px; margin-bottom: 5px;")
        self.result_layout.insertWidget(self.result_layout.count() - 1, header)

        current_type, current_content = "", ""

        def flush_reply():
            nonlocal current_type, current_content
            if not current_content.strip(): return
            current_type = current_type.replace("*", "").strip("【】[]:： ")
            current_content = current_content.replace("*", "").strip("- ").strip()
            if not current_content: return

            reply_frame = QFrame()
            reply_frame.setStyleSheet(
                "QFrame { background-color: #ffffff; border-radius: 6px; border: 1px solid #eaedf1; }")
            frame_layout = QHBoxLayout(reply_frame)
            frame_layout.setContentsMargins(12, 10, 12, 10)

            text_layout = QVBoxLayout()
            text_layout.setSpacing(4)
            prefix_label = QLabel(current_type if current_type else "推荐回复")
            prefix_label.setStyleSheet(
                "color: #4a90e2; font-size: 12px; font-weight: bold; border: none; background: transparent;")
            text_layout.addWidget(prefix_label)

            content_label = QLabel(current_content)
            content_label.setWordWrap(True)
            content_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            content_label.setStyleSheet("font-size: 12px; color: #222; border: none; background: transparent;")
            text_layout.addWidget(content_label)
            frame_layout.addLayout(text_layout, 1)

            copy_btn = QPushButton("📋 复制")
            copy_btn.setFixedSize(55, 24)
            copy_btn.setCursor(Qt.PointingHandCursor)
            copy_btn.setStyleSheet(
                "QPushButton { background-color: #f5f5f5; color: #333; border: 1px solid #ddd; border-radius: 4px; font-size: 11px; } QPushButton:hover { background-color: #e8e8e8; }")
            copy_btn.clicked.connect(
                lambda checked, text=current_content, btn=copy_btn: self.copy_to_clipboard(text, btn))
            frame_layout.addWidget(copy_btn, alignment=Qt.AlignTop)

            self.result_layout.insertWidget(self.result_layout.count() - 1, reply_frame)

        for line in lines:
            line = line.strip()
            if not line: continue
            is_new = False
            if re.match(r'^\d+\.', line):
                is_new = True
            elif "【" in line and "】" in line:
                is_new = True
            elif line.startswith("稳妥") or line.startswith("幽默") or line.startswith("情绪"):
                is_new = True

            if is_new:
                flush_reply()
                current_type = line
                if "：" in line:
                    parts = line.split("：", 1)
                    current_type, current_content = parts[0], parts[1]
                elif ":" in line:
                    parts = line.split(":", 1)
                    current_type, current_content = parts[0], parts[1]
                else:
                    current_content = ""
            else:
                current_content += " " + line
        flush_reply()

    def copy_to_clipboard(self, text, btn):
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        btn.setText("✅ 已复制")
        btn.setStyleSheet(
            "QPushButton { background-color: #d4edda; color: #28a745; border: 1px solid #c3e6cb; border-radius: 4px; font-size: 11px; font-weight: bold;}")
        QTimer.singleShot(1500, lambda: self.reset_copy_btn(btn))

    def reset_copy_btn(self, btn):
        btn.setText("📋 复制")
        btn.setStyleSheet(
            "QPushButton { background-color: #f5f5f5; color: #333; border: 1px solid #ddd; border-radius: 4px; font-size: 11px; } QPushButton:hover { background-color: #e8e8e8; }")