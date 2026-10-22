import os
import sys
import re
import json
import subprocess
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QFrame, QProgressBar, QApplication)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QPoint
from PyQt5.QtGui import QPainter, QPen, QColor, QPainterPath

# 评分引擎位于项目根目录，确保可导入
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path: sys.path.append(BASE_DIR)
import likability
import worker_launch


# ==========================================
# 自定义折线图组件 (纯 QPainter 绘制)
# ==========================================
class TrendChart(QFrame):
    """只绘制真实的历史评估数据；不足 2 个点时明确提示，不编造任何点。"""

    def __init__(self, points):
        super().__init__()
        self.setFixedHeight(180)
        self.setStyleSheet("QFrame { background-color: #ffffff; border-radius: 8px; border: 1px solid #eaedf1; }")
        self.points = list(points or [])
        self.setMinimumWidth(400)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)  # 抗锯齿，让线条平滑

        if len(self.points) < 2:  # 无历史可对比，避免画出误导性的"趋势"
            painter.setPen(QPen(QColor("#999")))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "历史数据不足：至少需要 2 次扫描才能形成趋势\n（每次扫描会自动存档一个真实数据点）")
            return

        width = self.width()
        height = self.height()
        padding_x, padding_y = 40, 30
        draw_width = width - padding_x * 2
        draw_height = height - padding_y * 2

        # 1. 背景网格线
        pen_grid = QPen(QColor("#f4f6f9"))
        pen_grid.setWidth(1)
        painter.setPen(pen_grid)
        for i in range(5):
            y = padding_y + draw_height * (i / 4)
            painter.drawLine(padding_x, int(y), width - padding_x, int(y))

        # 2. 坐标点
        pts = []
        step_x = draw_width / (len(self.points) - 1)
        for i, (_, val) in enumerate(self.points):
            x = padding_x + i * step_x
            y = padding_y + draw_height - (val / 100.0) * draw_height
            pts.append(QPoint(int(x), int(y)))

        # 3. 平滑折线
        pen_line = QPen(QColor("#4a90e2"))
        pen_line.setWidth(3)
        painter.setPen(pen_line)
        path = QPainterPath()
        path.moveTo(pts[0])
        for i in range(len(pts) - 1):
            p1, p2 = pts[i], pts[i + 1]
            mid_x = (p1.x() + p2.x()) / 2
            path.cubicTo(mid_x, p1.y(), mid_x, p2.y(), p2.x(), p2.y())
        painter.drawPath(path)

        # 4. 数据点、数值与日期标签
        for i, point in enumerate(pts):
            is_last = (i == len(pts) - 1)
            painter.setBrush(QColor("#28a745") if is_last else QColor("#4a90e2"))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(point, 6, 6)

            painter.setPen(QPen(QColor("#555")))
            painter.drawText(point.x() - 12, point.y() - 12, f"{self.points[i][1]}%")
            painter.setPen(QPen(QColor("#aaa")))
            painter.drawText(point.x() - 16, height - 8, self.points[i][0])


# ==========================================
# 子进程 Workers
# ==========================================
class ScanWorker(QThread):
    # finished_signal 携带 (正文, 结构化评估结果 dict 或 None)
    finished_signal = pyqtSignal(str, object)
    error_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(str)

    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path

    def run(self):
        try:
            worker_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "global_scan_worker.py")
            proc = worker_launch.launch_worker(worker_path, [self.folder_path], encoding="utf-8",
                                               errors="replace", bufsize=1)
            lines = []
            for line in proc.stdout:  # 流式读取，实时回显进度
                lines.append(line)
                if "[PROGRESS]" in line:
                    self.progress_signal.emit(line.split("[PROGRESS]", 1)[-1].strip())
            proc.stdout.close()
            proc.wait()
            if proc.returncode != 0:
                self.error_signal.emit("".join(lines))
                return

            # OK: 之后可能有多行正文，按行首前缀分别提取，避免互相干扰
            body, meta = None, None
            for line in lines:
                if line.startswith("META:") and meta is None:
                    try:
                        meta = json.loads(line[len("META:"):].strip())
                    except Exception:
                        meta = None
                elif line.startswith("OK:") and body is None:
                    body = line[len("OK:"):]
            if body is not None:
                self.finished_signal.emit(body.strip(), meta)
            elif "ERR:" in "".join(lines):
                self.error_signal.emit("".join(lines).split("ERR:", 1)[-1].strip())
            else:
                self.error_signal.emit("未知错误：\n" + "".join(lines))
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

        latest = likability.load_latest(self.current_user_path)
        if latest and latest.get("score") is not None:
            latest["cached"] = True
            self.show_dashboard(latest, "从本地存档读取（点击右上角可重新扫描全量记录）")
        else:
            self.append_hint("点击右上角【读取全量记录并扫描】，AI 将基于多维度加权生成好感度评估。")

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
        self.worker.progress_signal.connect(self.on_progress)
        self.worker.start()

    def on_progress(self, msg):
        self.clear_results()
        self.append_hint(msg)

    def on_scan_finished(self, result, meta):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("🚀 读取全量记录并扫描")
        self.clear_results()
        self.render_scan_result(result, meta)

    def on_scan_error(self, error_msg):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("🚀 读取全量记录并扫描")
        self.clear_results()
        self.append_hint(f"❌ 发生错误: {error_msg}")

    # ==========================================
    # 渲染 UI
    # ==========================================
    def render_scan_result(self, raw_text, meta=None):
        sections = re.split(r'###\s*', raw_text)

        analysis_cards = []
        for sec in sections:
            sec = sec.strip()
            if not sec: continue
            lines = sec.split("\n")
            title = lines[0].strip()
            content = "\n".join([l.strip() for l in lines[1:] if l.strip()])

            # 维度评分已由后端结构化解析，此处只取文字分析部分，不再二次解析分数
            if "多维" in title:
                analysis_cards.append(("📊 关系状态多维分析", content, "#e3f2fd", "#1565c0"))
            elif "破局" in title or "建议" in title:
                analysis_cards.append(("💡 长期关系破局点", content, "#fff3e0", "#e65100"))

        # 1. 渲染大看板（分数 + 置信度 + 折线图）
        if meta and meta.get("ok"):
            self.show_dashboard(meta, "")
        else:
            reason = (meta or {}).get("reason") or "模型输出未包含可识别的维度评分"
            self.add_text_card("⚠️ 本次评分未生成",
                               f"{reason}\n\n已保留上一次的评估结果，未写入新数据。可重新扫描；"
                               f"若反复失败，建议切换到云端 API 模型（本地 7B 对格式遵循较弱）。",
                               "#ffebee", "#c62828")
            latest = likability.load_latest(self.current_user_path)
            if latest and latest.get("score") is not None:
                latest["cached"] = True
                self.show_dashboard(latest, "以下为上一次的有效评估（本次未覆盖）")

        # 2. 渲染维度明细
        if meta and meta.get("dims"):
            self.add_dimension_card(meta)

        # 3. 渲染文本卡片
        for title, content, bg, color in analysis_cards:
            self.add_text_card(title, content, bg, color)

    def show_dashboard(self, assessment, hint_text):
        score = assessment.get("score")
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

        # 置信度与样本量：让分数带上可靠性说明，避免被当作绝对结论
        conf = assessment.get("confidence", "低")
        conf_color = {"高": "#28a745", "中": "#ffc107"}.get(conf, "#dc3545")
        meta_row = QHBoxLayout()
        conf_lbl = QLabel(f"置信度：<b style='color:{conf_color}'>{conf}</b>")
        conf_lbl.setStyleSheet("font-size: 12px; color: #666; border: none;")
        meta_row.addWidget(conf_lbl)
        if assessment.get("sample_count"):
            sample_lbl = QLabel(f"样本：{assessment['sample_count']} 条")
            sample_lbl.setStyleSheet("font-size: 12px; color: #666; border: none;")
            meta_row.addWidget(sample_lbl)
        if assessment.get("time"):
            time_lbl = QLabel(f"评估时间：{assessment['time']}")
            time_lbl.setStyleSheet("font-size: 12px; color: #666; border: none;")
            meta_row.addWidget(time_lbl)
        meta_row.addStretch()
        card_layout.addLayout(meta_row)

        if hint_text:
            hint = QLabel(hint_text)
            hint.setStyleSheet("color: #888; font-size: 12px; margin-top: 5px; border: none;")
            card_layout.addWidget(hint)

        self.result_layout.insertWidget(self.result_layout.count() - 1, card)

        # 展示告警（维度缺失、样本不足、与模型自评偏差大等）
        for w in assessment.get("warnings", []) or []:
            warn = QLabel("⚠️ " + w)
            warn.setWordWrap(True)
            warn.setStyleSheet(
                "color: #8a6d3b; background-color: #fff8e1; font-size: 12px; border: 1px solid #ffe082; "
                "border-radius: 6px; padding: 8px 10px;")
            self.result_layout.insertWidget(self.result_layout.count() - 1, warn)

        # --- 折线趋势图（仅使用真实历史数据）---
        history = likability.load_history(self.current_user_path)
        points = [(h.get("t", "")[5:10] or "?", int(h["score"])) for h in history if h.get("score") is not None]
        if not points and score is not None:  # 兼容旧存档：至少显示当前点
            points = [(assessment.get("time", "")[5:10] or "本次", int(score))]

        chart_card = QFrame()
        chart_card.setStyleSheet(
            "QFrame { background-color: #ffffff; border-radius: 10px; border: 1px solid #eaedf1; }")
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(20, 15, 20, 10)

        c_title = QLabel(f"📈 好感度历史趋势（真实数据 {len(points)} 次评估）")
        c_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #333; border: none;")
        chart_layout.addWidget(c_title)

        chart_layout.addWidget(TrendChart(points))
        self.result_layout.insertWidget(self.result_layout.count() - 1, chart_card)

    def add_dimension_card(self, meta):
        """展示各维度得分与依据，让总分可追溯。"""
        dims = meta.get("dims", {}) or {}
        evidence = meta.get("dims_evidence", {}) or {}
        if not dims: return

        card = QFrame()
        card.setStyleSheet(
            "QFrame { background-color: #ffffff; border-radius: 10px; border: 1px solid #eaedf1; }")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(8)

        title = QLabel("🧮 维度评分明细（按固定权重加权得出总分）")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #1565c0; border: none;")
        layout.addWidget(title)

        for name, weight, _desc in likability.DIMENSIONS:
            if name not in dims: continue
            val = dims[name]
            row = QHBoxLayout()
            name_lbl = QLabel(f"{name} <span style='color:#999;font-size:11px'>权重 {int(weight * 100)}%</span>")
            name_lbl.setFixedWidth(150)
            name_lbl.setStyleSheet("font-size: 13px; color: #333; border: none;")
            row.addWidget(name_lbl)

            bar = QProgressBar()
            bar.setValue(int(val))
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            color = "#28a745" if val >= 70 else ("#ffc107" if val >= 40 else "#dc3545")
            bar.setStyleSheet(
                f"QProgressBar {{ border: none; background-color: #f4f6f9; border-radius: 4px; }} "
                f"QProgressBar::chunk {{ background-color: {color}; border-radius: 4px; }}")
            row.addWidget(bar, 1)

            val_lbl = QLabel(f"{val}")
            val_lbl.setFixedWidth(32)
            val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val_lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {color}; border: none;")
            row.addWidget(val_lbl)
            layout.addLayout(row)

            ev = evidence.get(name, "")
            if ev:
                ev_lbl = QLabel(f"　依据：{ev}")
                ev_lbl.setWordWrap(True)
                ev_lbl.setStyleSheet("font-size: 12px; color: #777; border: none; margin-bottom: 4px;")
                layout.addWidget(ev_lbl)

        if meta.get("model_score") is not None:
            cmp_lbl = QLabel(
                f"模型自评综合好感度：{meta['model_score']}　|　维度加权结果：{meta.get('score')}")
            cmp_lbl.setStyleSheet("font-size: 12px; color: #666; border: none; margin-top: 6px;")
            layout.addWidget(cmp_lbl)

        # 如实说明 LLM 评分的固有不确定性，而不是假装结果精确
        note = QLabel("注：评分由大模型基于聊天记录推断，非客观测量；同一份记录重复扫描通常有 ±10 分波动，"
                      "请重点参考维度明细与依据，而非绝对分值。")
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 11px; color: #999; border: none; margin-top: 4px;")
        layout.addWidget(note)

        self.result_layout.insertWidget(self.result_layout.count() - 1, card)

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