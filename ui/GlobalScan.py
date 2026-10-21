import os
import sys
import re
import random
import subprocess
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QFrame, QProgressBar, QApplication)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QPoint
from PyQt5.QtGui import QPainter, QPen, QColor, QPainterPath


# ==========================================
# 自定义折线图组件 (纯 QPainter 绘制)
# ==========================================
class TrendChart(QFrame):
    def __init__(self, score):
        super().__init__()
        self.setFixedHeight(180)
        self.setStyleSheet("QFrame { background-color: #ffffff; border-radius: 8px; border: 1px solid #eaedf1; }")

        # 模拟历史数据 + 最新分数生成趋势
        self.data = [max(10, min(100, score - random.randint(-20, 20))) for _ in range(5)]
        self.data.append(score)  # 最后一个点是你当前扫描的分数
        self.setMinimumWidth(400)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)  # 抗锯齿，让线条平滑

        width = self.width()
        height = self.height()

        # 内边距
        padding_x = 40
        padding_y = 30

        draw_width = width - padding_x * 2
        draw_height = height - padding_y * 2

        # 1. 画背景网格线
        pen_grid = QPen(QColor("#f4f6f9"))
        pen_grid.setWidth(1)
        painter.setPen(pen_grid)
        for i in range(5):
            y = padding_y + draw_height * (i / 4)
            painter.drawLine(padding_x, int(y), width - padding_x, int(y))

        # 2. 计算坐标点
        points = []
        step_x = draw_width / (len(self.data) - 1)

        for i, val in enumerate(self.data):
            x = padding_x + i * step_x
            # 90分对应顶部，10分对应底部（Y轴反转）
            y = padding_y + draw_height - (val / 100.0) * draw_height
            points.append(QPoint(int(x), int(y)))

        # 3. 画平滑折线
        pen_line = QPen(QColor("#4a90e2"))
        pen_line.setWidth(3)
        painter.setPen(pen_line)

        path = QPainterPath()
        path.moveTo(points[0])
        for i in range(len(points) - 1):
            # 贝塞尔曲线实现平滑连接
            p1 = points[i]
            p2 = points[i + 1]
            mid_x = (p1.x() + p2.x()) / 2
            path.cubicTo(mid_x, p1.y(), mid_x, p2.y(), p2.x(), p2.y())

        painter.drawPath(path)

        # 4. 画数据点和数值
        for i, point in enumerate(points):
            # 渐变圆点
            is_last = (i == len(points) - 1)
            circle_color = QColor("#4a90e2") if not is_last else QColor("#28a745")
            painter.setBrush(circle_color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(point, 6, 6)

            # 画上数值
            painter.setPen(QPen(QColor("#555")))
            painter.drawText(point.x() - 10, point.y() - 12, f"{self.data[i]}%")


# ==========================================
# 子进程 Workers
# ==========================================
class ScanWorker(QThread):
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path

    def run(self):
        try:
            worker_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "global_scan_worker.py")
            proc = subprocess.Popen([sys.executable, worker_path, self.folder_path], stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, encoding="utf-8", errors="replace")
            out, _ = proc.communicate()
            if proc.returncode != 0: self.error_signal.emit(out); return
            if "OK:" in out:
                self.finished_signal.emit(out.split("OK:", 1)[-1].strip())
            elif "ERR:" in out:
                self.error_signal.emit(out.split("ERR:", 1)[-1].strip())
            else:
                self.error_signal.emit("未知错误：\n" + out)
        except Exception as e:
            self.error_signal.emit(str(e))


# ==========================================
# 界面
# ==========================================
class GlobalScanPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_user_path = ""
        self.worker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶栏
        top_bar = QWidget()
        top_bar.setFixedHeight(44)
        top_bar.setStyleSheet("border-bottom: 1px solid #eaedf1; background-color: #ffffff;")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(15, 0, 15, 0)

        title = QLabel("📈 全局关系深度扫描")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #1a1a1a; border: none;")
        top_bar_layout.addWidget(title)
        top_bar_layout.addStretch()

        self.scan_btn = QPushButton("🚀 读取全量记录并扫描")
        self.scan_btn.setFixedHeight(24)
        self.scan_btn.setCursor(Qt.PointingHandCursor)
        self.scan_btn.setStyleSheet(
            "QPushButton { background-color: #f8f9fa; color: #4a90e2; border: 1px solid #4a90e2; border-radius: 4px; padding: 0 10px; font-size: 11px; font-weight: bold;} QPushButton:hover { background-color: #e6f0ff; }")
        self.scan_btn.clicked.connect(self.start_scan)
        top_bar_layout.addWidget(self.scan_btn)
        layout.addWidget(top_bar)

        # 结果区
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: #f4f6f9; }")

        self.result_container = QWidget()
        self.result_container.setStyleSheet("background-color: #f4f6f9;")
        self.result_layout = QVBoxLayout(self.result_container)
        self.result_layout.setContentsMargins(20, 20, 20, 20)
        self.result_layout.setSpacing(15)
        self.result_layout.addStretch()

        self.scroll_area.setWidget(self.result_container)
        layout.addWidget(self.scroll_area, 1)

    def load_scan_data(self, user_folder_path):
        self.current_user_path = user_folder_path
        self.clear_results()

        # 尝试从缓存读取
        yc_path = os.path.join(self.current_user_path, "yc.txt")
        if os.path.exists(yc_path):
            with open(yc_path, "r", encoding="utf-8") as f:
                try:
                    score = int(f.read().strip())
                    self.show_dashboard(score, "从历史缓存读取（点击右上角可重新扫描全量记录）")
                except:
                    self.append_hint("点击右上角【读取全量记录并扫描】，AI 将生成最新好感度评估。")
        else:
            self.append_hint("点击右上角【读取全量记录并扫描】，AI 将生成最新好感度评估。")

    def clear_results(self):
        while self.result_layout.count() > 1:
            item = self.result_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def append_hint(self, text):
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #888; font-size: 13px; margin-top: 30px;")
        self.result_layout.insertWidget(self.result_layout.count() - 1, label)

    def start_scan(self):
        if not self.current_user_path: return
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("⏳ 正在扫描全量记录...")
        self.clear_results()
        self.append_hint("AI 正在阅读全部聊天记录，评估关系深度 (约需 10-20 秒)...")

        self.worker = ScanWorker(self.current_user_path)
        self.worker.finished_signal.connect(self.on_scan_finished)
        self.worker.error_signal.connect(self.on_scan_error)
        self.worker.start()

    def on_scan_finished(self, result):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("🚀 读取全量记录并扫描")
        self.clear_results()
        self.render_scan_result(result)

    def on_scan_error(self, error_msg):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("🚀 读取全量记录并扫描")
        self.clear_results()
        self.append_hint(f"❌ 发生错误: {error_msg}")

    # ==========================================
    # 渲染 UI
    # ==========================================
    def render_scan_result(self, raw_text):
        sections = re.split(r'###\s*', raw_text)

        score = 50
        analysis_cards = []

        for sec in sections:
            sec = sec.strip()
            if not sec: continue
            lines = sec.split("\n")
            title = lines[0].strip()
            content = "\n".join([l.strip() for l in lines[1:] if l.strip()])

            if "好感度" in title:
                match = re.search(r'好感度[:：]\s*(\d+)', content)
                if match: score = min(100, int(match.group(1)))
            elif "多维" in title:
                analysis_cards.append(("📊 关系状态多维分析", content, "#e3f2fd", "#1565c0"))
            elif "破局" in title or "建议" in title:
                analysis_cards.append(("💡 长期关系破局点", content, "#fff3e0", "#e65100"))

        # 1. 渲染大看板（进度条 + 折线图）
        self.show_dashboard(score, "")

        # 2. 渲染文本卡片
        for title, content, bg, color in analysis_cards:
            self.add_text_card(title, content, bg, color)

    def show_dashboard(self, score, hint_text):
        # --- 进度条卡片 ---
        card = QFrame()
        color = "#28a745" if score >= 70 else ("#ffc107" if score >= 40 else "#dc3545")
        card.setStyleSheet(
            f"QFrame {{ background-color: #ffffff; border-radius: 10px; border-left: 5px solid {color}; border-top: 1px solid #eaedf1; border-right: 1px solid #eaedf1; border-bottom: 1px solid #eaedf1; }}")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)

        header = QHBoxLayout()
        t_lbl = QLabel("💖 综合好感度评估")
        t_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #333; border: none;")
        s_lbl = QLabel(f"{score}%")
        s_lbl.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {color}; border: none;")
        header.addWidget(t_lbl)
        header.addStretch()
        header.addWidget(s_lbl)
        card_layout.addLayout(header)

        bar = QProgressBar()
        bar.setValue(score)
        bar.setTextVisible(False)
        bar.setFixedHeight(12)
        bar.setStyleSheet(
            f"QProgressBar {{ border: none; background-color: #f4f6f9; border-radius: 6px; }} QProgressBar::chunk {{ background-color: {color}; border-radius: 6px; }}")
        card_layout.addWidget(bar)

        if hint_text:
            hint = QLabel(hint_text)
            hint.setStyleSheet("color: #888; font-size: 12px; margin-top: 5px; border: none;")
            card_layout.addWidget(hint)

        self.result_layout.insertWidget(self.result_layout.count() - 1, card)

        # --- 折线趋势图 ---
        chart_card = QFrame()
        chart_card.setStyleSheet(
            "QFrame { background-color: #ffffff; border-radius: 10px; border: 1px solid #eaedf1; }")
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(20, 15, 20, 10)

        c_title = QLabel("📈 好感度历史趋势评估 (模拟)")
        c_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #333; border: none;")
        chart_layout.addWidget(c_title)

        chart = TrendChart(score)
        chart_layout.addWidget(chart)

        self.result_layout.insertWidget(self.result_layout.count() - 1, chart_card)

    def add_text_card(self, title, content, bg_color, title_color):
        if not content: return
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background-color: {bg_color}; border-radius: 10px; border: 1px solid {title_color}33; }}")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 15, 20, 15)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {title_color}; border: none;")
        layout.addWidget(lbl_title)

        lbl_content = QLabel(content)
        lbl_content.setWordWrap(True)
        lbl_content.setStyleSheet("font-size: 14px; color: #333; line-height: 1.6; border: none;")
        layout.addWidget(lbl_content)

        self.result_layout.insertWidget(self.result_layout.count() - 1, card)