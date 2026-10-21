import os
import re
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QFrame, QGridLayout,
                             QProgressBar, QFileDialog, QApplication, QMessageBox)
from PyQt5.QtCore import Qt, QTimer


class CharacterAnalysisPage(QWidget):
    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self.current_user_path = ""
        self.raw_markdown = ""
        self.main_window = main_window

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = QWidget()
        top_bar.setFixedHeight(44)
        top_bar.setStyleSheet("border-bottom: 1px solid #eaedf1; background-color: #ffffff;")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(15, 0, 15, 0)

        title = QLabel("🎭 人物深度画像")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #1a1a1a; border: none;")
        top_bar_layout.addWidget(title)
        top_bar_layout.addStretch()

        self.copy_btn = QPushButton("📋 复制")
        self.export_btn = QPushButton("💾 导出")
        self.sim_btn = QPushButton("💬 去对话")
        self.refresh_btn = QPushButton("🔄 刷新")

        for btn in [self.copy_btn, self.export_btn, self.sim_btn, self.refresh_btn]:
            btn.setFixedHeight(24)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background-color: #f8f9fa; color: #333; border: 1px solid #ddd; border-radius: 4px; padding: 0 8px; font-size: 11px; font-weight: bold;} QPushButton:hover { background-color: #e2e6ea; }")
            top_bar_layout.addWidget(btn)

        self.copy_btn.clicked.connect(self.copy_all)
        self.export_btn.clicked.connect(self.export_md)
        self.sim_btn.clicked.connect(self.go_to_simulation)
        self.refresh_btn.clicked.connect(self.refresh_data)

        top_bar_layout.setSpacing(6)
        layout.addWidget(top_bar)

        self.summary_frame = QFrame()
        self.summary_frame.setStyleSheet("background-color: #fff3e0; border-radius: 4px; margin: 10px 15px 0 15px;")
        summary_layout = QHBoxLayout(self.summary_frame)
        summary_layout.setContentsMargins(12, 8, 12, 8)

        self.summary_icon = QLabel("✨ 核心画像：")
        self.summary_icon.setStyleSheet("font-size: 12px; font-weight: bold; color: #e65100; border: none;")
        self.summary_text = QLabel("暂无摘要")
        self.summary_text.setWordWrap(True)
        self.summary_text.setStyleSheet("font-size: 12px; color: #333; border: none; font-weight: bold;")

        summary_layout.addWidget(self.summary_icon)
        summary_layout.addWidget(self.summary_text, 1)
        layout.addWidget(self.summary_frame)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: #f4f6f9; }")

        self.content_container = QWidget()
        self.content_container.setStyleSheet("background-color: #f4f6f9;")
        self.grid_layout = QGridLayout(self.content_container)
        self.grid_layout.setContentsMargins(15, 10, 15, 15)
        self.grid_layout.setSpacing(10)

        self.scroll_area.setWidget(self.content_container)
        layout.addWidget(self.scroll_area, 1)

    def load_persona(self, user_folder_path):
        self.current_user_path = user_folder_path
        self.refresh_data()

    def refresh_data(self):
        if not self.current_user_path: return
        file_path = os.path.join(self.current_user_path, "persona.md")
        if not os.path.exists(file_path): return

        with open(file_path, "r", encoding="utf-8") as f:
            self.raw_markdown = f.read()

        # 清洗底层的颜色乱码
        self.raw_markdown = re.sub(r'\x1b\[[0-9;]*m', '', self.raw_markdown).replace("[0m", "").replace("\x1b", "")

        # 强制替换真实昵称
        current_nickname = os.path.basename(self.current_user_path)
        if current_nickname:
            self.raw_markdown = self.raw_markdown.replace(current_nickname, "对方").replace("【对方】", "对方")
        self.raw_markdown = self.raw_markdown.replace("胡萝贝", "对方").replace("Let me say", "对方")

        self.render_dashboard()

    def render_dashboard(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        if not self.raw_markdown.strip(): return

        first_paragraph = self.raw_markdown.replace("###", "").replace("#", "").split("\n\n")[0]
        clean_summary = re.sub(r'[#*`-]', '', first_paragraph).strip()
        if len(clean_summary) > 50: clean_summary = clean_summary[:50] + "..."
        self.summary_text.setText(clean_summary)

        sections = re.split(r'###\s*', self.raw_markdown)
        row, col = 0, 0

        for sec in sections:
            sec = sec.strip()
            if not sec: continue
            lines = sec.split("\n")
            title = lines[0].strip()
            content = "\n".join(lines[1:]).strip()

            if not content: continue
            content = self.highlight_keywords(content)

            card = self.create_card(title, content)
            self.grid_layout.addWidget(card, row, col)

            col += 1
            if col > 1:
                col = 0
                row += 1

    def highlight_keywords(self, text):
        text = text.replace("**", "")
        keywords = ["直接", "幽默", "敏感", "焦虑", "温柔", "独立", "依赖", "讨厌", "喜欢", "反感", "开心", "逃避",
                    "生气", "吃软不吃硬"]
        for kw in keywords:
            text = text.replace(kw, f"<span style='color:#d32f2f; font-weight:bold;'>{kw}</span>")
        return text.replace("\n", "<br>")

    def create_card(self, title, content):
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background-color: #ffffff; border-radius: 6px; border-left: 3px solid #4a90e2; border-top: 1px solid #eaedf1; border-right: 1px solid #eaedf1; border-bottom: 1px solid #eaedf1; }")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #1565c0; border: none;")
        layout.addWidget(lbl_title)

        score = min(95, max(40, len(content) + 30))
        bar = QProgressBar()
        bar.setValue(score)
        bar.setTextVisible(False)
        bar.setFixedHeight(4)
        bar.setStyleSheet(
            "QProgressBar { border: none; background-color: #f4f6f9; border-radius: 2px; } QProgressBar::chunk { background-color: #4a90e2; border-radius: 2px; }")
        layout.addWidget(bar)

        lbl_content = QLabel(content)
        lbl_content.setWordWrap(True)
        lbl_content.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl_content.setStyleSheet("font-size: 12px; color: #444; line-height: 1.4; border: none;")
        layout.addWidget(lbl_content)
        return card

    def copy_all(self):
        if not self.raw_markdown: return
        clipboard = QApplication.clipboard()
        clipboard.setText(self.raw_markdown)
        self.copy_btn.setText("✅ 已复制")
        QTimer.singleShot(1500, lambda: self.copy_btn.setText("📋 复制"))

    def export_md(self):
        if not self.raw_markdown or not self.current_user_path: return
        file_path, _ = QFileDialog.getSaveFileName(self, "导出画像",
                                                   f"{os.path.basename(self.current_user_path)}_persona.md",
                                                   "Markdown Files (*.md)")
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f: f.write(self.raw_markdown)
            QMessageBox.information(self, "成功", "导出成功！")

    def go_to_simulation(self):
        if self.main_window and hasattr(self.main_window, 'switch_to_simulation'):
            self.main_window.switch_to_simulation()