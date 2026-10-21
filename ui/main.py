import sys
import os
import json
from openai import OpenAI
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                             QVBoxLayout, QPushButton, QLabel, QStackedWidget,
                             QListWidget, QListWidgetItem, QInputDialog, QMessageBox, QComboBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from Character_Analysis import CharacterAnalysisPage
from Simulation import SimulationPage
from Train import TrainPage
from Advisor import AdvisorPage
from GlobalScan import GlobalScanPage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Character Analysis - AI 军师系统")
        self.resize(1180, 720)
        self.setStyleSheet("QMainWindow { background-color: #f4f6f9; }")

        # ======== 动态获取根目录 ========
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.users_root_dir = os.path.join(self.base_dir, "Users")
        self.settings_path = os.path.join(self.base_dir, "settings.json")
        self.current_user_name = ""

        self.init_settings_file()

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ================= 左侧导航栏 =================
        nav = QWidget()
        nav.setFixedWidth(210)
        nav.setStyleSheet("QWidget { background-color: #ffffff; border-right: 1px solid #eaedf1; }")
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(12, 15, 12, 15)
        nav_layout.setSpacing(10)

        self.user_label = QLabel("👤 当前用户: 未选择")
        self.user_label.setStyleSheet("font-size: 13px; color: #1a1a1a; font-weight: bold; border: none;")
        nav_layout.addWidget(self.user_label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self.add_user_btn = QPushButton("添加")
        self.add_user_btn.setFixedHeight(28)
        self.add_user_btn.setCursor(Qt.PointingHandCursor)
        self.add_user_btn.setStyleSheet(
            "QPushButton { background-color: #4a90e2; color: white; border: none; border-radius: 4px; font-size: 12px; font-weight: bold; } QPushButton:hover { background-color: #357abd; }")
        self.add_user_btn.clicked.connect(self.add_user)

        self.select_user_btn = QPushButton("切换")
        self.select_user_btn.setFixedHeight(28)
        self.select_user_btn.setCursor(Qt.PointingHandCursor)
        self.select_user_btn.setStyleSheet(
            "QPushButton { background-color: #f8f9fa; color: #333; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; font-weight: bold; } QPushButton:hover { background-color: #e2e6ea; }")
        self.select_user_btn.clicked.connect(self.select_user)

        self.settings_btn = QPushButton("⚙️")
        self.settings_btn.setFixedSize(28, 28)
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setStyleSheet(
            "QPushButton { background-color: #f8f9fa; color: #333; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; } QPushButton:hover { background-color: #e2e6ea; }")
        self.settings_btn.clicked.connect(self.open_settings)

        btn_layout.addWidget(self.add_user_btn)
        btn_layout.addWidget(self.select_user_btn)
        btn_layout.addWidget(self.settings_btn)
        nav_layout.addLayout(btn_layout)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget { background-color: transparent; color: #333; border: none; font-size: 12px; }
            QListWidget::item { padding: 10px 12px; border-radius: 6px; margin-bottom: 4px; }
            QListWidget::item:hover { background-color: #f4f6f9; }
            QListWidget::item:selected { background-color: #e6f0ff; color: #4a90e2; font-weight: bold; }
        """)
        self.list_widget.currentRowChanged.connect(self.switch_content)
        nav_layout.addWidget(self.list_widget, 1)

        main_layout.addWidget(nav)

        # ================= 右侧主体内容区 =================
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        top_disclaimer_bar = QWidget()
        top_disclaimer_bar.setFixedHeight(32)
        top_disclaimer_bar.setStyleSheet("background-color: #fff8e1; border-bottom: 1px solid #ffe082;")
        d_layout = QHBoxLayout(top_disclaimer_bar)
        d_layout.setContentsMargins(15, 0, 15, 0)

        d_label = QLabel("⚠️ 提示：本软件内所有分析均由 AI 生成，仅供参考与娱乐。")
        d_label.setStyleSheet("color: #b78103; font-size: 11px; font-weight: bold;")
        d_layout.addWidget(d_label)
        d_layout.addStretch()

        mode_label = QLabel("运行模式:")
        mode_label.setStyleSheet("color: #b78103; font-size: 11px; font-weight: bold;")
        d_layout.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("💻 本地显卡 (Local)", False)
        self.mode_combo.addItem("☁️ 云端 API (Cloud)", True)
        self.mode_combo.setFixedWidth(160)
        self.mode_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #ccc; border-radius: 4px; padding: 2px 8px;
                font-size: 11px; font-weight: bold; background-color: #fff; color: #333;
            }
        """)
        self.mode_combo.currentIndexChanged.connect(self.toggle_mode)
        d_layout.addWidget(self.mode_combo)

        right_layout.addWidget(top_disclaimer_bar)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("QStackedWidget { background-color: #f4f6f9; }")
        right_layout.addWidget(self.stack, 1)

        main_layout.addWidget(right_container, 1)

        self.user_list = []

        self.page_train = TrainPage()
        self.page_analysis = CharacterAnalysisPage(self)
        self.page_simulation = SimulationPage()
        self.page_advisor = AdvisorPage()
        self.page_global_scan = GlobalScanPage()

        self.add_page("💬 对话训练", self.page_train)
        self.add_page("🎭 人物画像", self.page_analysis)
        self.add_page("🗣️ 模拟对话", self.page_simulation)
        self.add_page("🕵️ 军师分析", self.page_advisor)
        self.add_page("📈 关系扫描", self.page_global_scan)

        self.sync_mode_ui()
        self.load_existing_users()

    def init_settings_file(self):
        if not os.path.exists(self.settings_path):
            default = {
                "use_api": False,
                "api_key": "sk-填入你的API_KEY",
                "base_url": "https://api.deepseek.com",
                "model_name": "deepseek-chat"
            }
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=4, ensure_ascii=False)

    def sync_mode_ui(self):
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            is_api = config.get("use_api", False)
            self.mode_combo.blockSignals(True)
            self.mode_combo.setCurrentIndex(1 if is_api else 0)
            self.mode_combo.blockSignals(False)
        except:
            pass

    def toggle_mode(self, index):
        is_api = self.mode_combo.itemData(index)
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            config["use_api"] = is_api
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法保存配置文件: {e}")
            return

        if is_api:
            self.check_api_environment(config)

    def check_api_environment(self, config):
        api_key = config.get("api_key", "")
        base_url = config.get("base_url", "")

        if not api_key or "填入" in api_key:
            QMessageBox.warning(self, "API 配置缺失", "检测到 API Key 为空！\n请点击左侧【⚙️】按钮填写真实的 API Key。")
            self.mode_combo.setCurrentIndex(0)
            return

        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            client.chat.completions.create(
                model=config.get("model_name", "deepseek-chat"),
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=5
            )
            QMessageBox.information(self, "环境检测通过", "✅ 云端 API 连接成功！\n接下来所有分析将走云端，响应极快。")
        except Exception as e:
            QMessageBox.critical(self, "API 连接失败",
                                 f"❌ 无法连接云端 API，请检查网络或 Key 是否正确。\n错误: {e}\n\n系统已自动退回本地模式。")
            self.mode_combo.setCurrentIndex(0)

    def open_settings(self):
        self.init_settings_file()
        if sys.platform == "win32":
            os.startfile(self.settings_path)

    def add_page(self, list_name, page_widget):
        item = QListWidgetItem(list_name)
        self.list_widget.addItem(item)
        self.stack.addWidget(page_widget)
        if self.list_widget.count() == 1:
            self.list_widget.setCurrentRow(0)

    def switch_content(self, row):
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    def switch_to_simulation(self):
        self.list_widget.setCurrentRow(2)

    def load_existing_users(self):
        if os.path.exists(self.users_root_dir):
            for item in os.listdir(self.users_root_dir):
                item_path = os.path.join(self.users_root_dir, item)
                if os.path.isdir(item_path) and item not in self.user_list:
                    self.user_list.append(item)

            if self.user_list:
                self.current_user_name = self.user_list[0]
                self.user_label.setText(f"👤 当前用户: {self.current_user_name}")
                self.update_pages_data(self.current_user_name)

    def update_pages_data(self, user_name):
        user_folder = os.path.join(self.users_root_dir, user_name)
        self.page_analysis.load_persona(user_folder)
        self.page_train.load_train_data(user_folder)
        self.page_simulation.load_simulation_data(user_folder)
        self.page_advisor.load_advisor_data(user_folder)
        self.page_global_scan.load_scan_data(user_folder)

    def add_user(self):
        nickname, ok1 = QInputDialog.getText(self, "添加用户", "请输入对方昵称:")
        if not (ok1 and nickname.strip()): return
        nickname = nickname.strip()

        if any(c in '\\/:*?"<>|' for c in nickname):
            QMessageBox.warning(self, "错误", "昵称包含非法字符！")
            return
        if nickname in self.user_list:
            QMessageBox.warning(self, "错误", "用户已存在！")
            return

        initial_persona, ok2 = QInputDialog.getMultiLineText(self, "初始人设", "请输入TA的初始人设/背景（可留空）：", "")
        if not ok2: return

        user_folder = os.path.join(self.users_root_dir, nickname)
        try:
            os.makedirs(user_folder, exist_ok=True)
            for filename in ["ltjl.txt", "moni_ltjl.txt", "new_ltjl.txt", "persona.md"]:
                with open(os.path.join(user_folder, filename), 'a', encoding='utf-8') as f: pass

            if initial_persona.strip():
                with open(os.path.join(user_folder, "moni_ltjl.txt"), 'w', encoding='utf-8') as f:
                    f.write(initial_persona.strip())

            self.user_list.append(nickname)
            QMessageBox.information(self, "成功", f"用户【{nickname}】创建成功！")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"创建失败：\n{str(e)}")

    def select_user(self):
        if not self.user_list:
            QMessageBox.information(self, "提示", "暂无用户。")
            return
        user, ok = QInputDialog.getItem(self, "选择用户", "请选择:", self.user_list, 0, False)
        if ok and user:
            self.current_user_name = user
            self.user_label.setText(f"👤 当前用户: {user}")
            self.update_pages_data(user)


if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    font = QFont("Microsoft YaHei", 9)
    app.setFont(font)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())