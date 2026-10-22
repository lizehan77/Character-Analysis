import sys
import os
import json
import re

BASE_DIR_TOP = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR_TOP not in sys.path: sys.path.append(BASE_DIR_TOP)
from worker_launch import force_utf8_stdio

force_utf8_stdio()  # Windows 下默认 GBK 输出会让中文在调用方变成乱码

folder_path = sys.argv[1]

# ======== 动态获取路径 ========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
settings_path = os.path.join(BASE_DIR, "settings.json")

use_api = False
if os.path.exists(settings_path):
    with open(settings_path, "r", encoding="utf-8") as f:
        use_api = json.load(f).get("use_api", False)

ltjl_path = os.path.join(folder_path, "ltjl.txt")
persona_path = os.path.join(folder_path, "persona.md")
yc_path = os.path.join(folder_path, "yc.txt")

if not os.path.exists(ltjl_path): print("ERR: 找不到 ltjl.txt"); sys.exit(1)
with open(ltjl_path, "r", encoding="utf-8") as f: chat_content = f.read()
if not chat_content.strip(): print("ERR: 聊天记录为空"); sys.exit(1)

old_persona = ""
if os.path.exists(persona_path):
    with open(persona_path, "r", encoding="utf-8") as f:
        old_persona = f.read().strip()

import likability

# 按尾部裁剪：聊天记录越靠后越新，保证喂给模型的是最近的对话
MAX_CHARS = 6000
if len(chat_content) > MAX_CHARS:
    chat_content = chat_content[-MAX_CHARS:]

prompt = f"""你是一位资深的心理与情感关系分析师。请阅读以下全部聊天记录及画像。
【已有画像】：
{old_persona if old_persona else "暂无"}
【全部聊天记录】：
{chat_content}
{likability.prompt_block()}"""

messages = [{"role": "user", "content": prompt}]

try:
    if use_api:
        if BASE_DIR not in sys.path: sys.path.append(BASE_DIR)
        from llm_api import call_llm_api

        print("🚀 使用云端 API 推理...", file=sys.stderr)
        result = call_llm_api(messages, settings_path)
    else:
        from local_engine import generate_local  # 复用常驻服务，避免每次重载 7B 模型

        # 评分任务要求稳定可复现，温度取低值；文本分析灵活性损失可接受
        result = generate_local(messages, max_new_tokens=1200, max_input_tokens=2048, temperature=0.3, top_p=0.9,
                                on_progress=lambda m: print("[PROGRESS] " + m, file=sys.stderr))

    result = re.sub(r'\x1b\[[0-9;]*m', '', result).replace("[0m", "").replace("\x1b", "")

    # 结构化评估：多维度加权，解析不出维度即判定失败，不用默认值冒充
    assessment = likability.evaluate(result, open(ltjl_path, "r", encoding="utf-8-sig").read())
    likability.save_result(folder_path, assessment)

    if assessment.get("ok"):
        dims = assessment.get("dims") or {}
        msg = (f"✅ 加权好感度 {assessment.get('score')}%（置信度 {assessment.get('confidence')}，"
               f"样本 {assessment.get('sample_count')} 条，识别 {len(dims)}/6 维度）")
        print(msg, file=sys.stderr)
    else:
        print(f"⚠️ 评分失败：{assessment.get('reason')}（未覆盖上次结果）", file=sys.stderr)

    # 评估结果随正文一起回传，界面据此渲染（避免二次解析不一致）
    # 注意顺序：META 必须在 OK 之前输出，否则会被 OK 之后的多行正文吞掉
    meta = json.dumps({k: assessment.get(k) for k in
                       ("ok", "score", "dims", "dims_evidence", "model_score", "confidence", "sample_count",
                        "warnings", "reason")}, ensure_ascii=False)
    print("META:" + meta)
    print("OK:" + result)
except Exception as e:
    import traceback

    print(f"ERR: {traceback.format_exc()}")