import sys
import os
import json
import re

folder_path = sys.argv[1]
history = json.loads(sys.argv[2])
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
settings_path = os.path.join(BASE_DIR, "settings.json")

use_api = False
if os.path.exists(settings_path):
    with open(settings_path, "r", encoding="utf-8") as f:
        use_api = json.load(f).get("use_api", False)

persona_path = os.path.join(folder_path, "persona.md")
moni_persona_path = os.path.join(folder_path, "moni_ltjl.txt")

base_setting = ""
if os.path.exists(moni_persona_path):
    with open(moni_persona_path, "r", encoding="utf-8") as f:
        base_setting = f.read().split("我:", 1)[0].strip()

analyzed_persona = ""
if os.path.exists(persona_path):
    with open(persona_path, "r", encoding="utf-8") as f:
        analyzed_persona = f.read().strip()

final_persona = ""
if base_setting: final_persona += f"【基础人设】\n{base_setting}\n\n"
if analyzed_persona: final_persona += f"【深度分析】\n{analyzed_persona}"

system_prompt = f"""你现在正在微信上聊天，必须严格遵守：
1. 你就是角色本人，绝对不能承认自己是AI。
2. 说话口语化、简短（1-2句），不要长篇大论。
3. 按照下方人设说话，模仿其语气。
4. 多带自然语气词，可适当使用表情。
【你的人设】：\n{final_persona}"""

messages = [{"role": "system", "content": system_prompt}]
for msg in history:
    messages.append({"role": msg["role"], "content": msg["content"]})

try:
    if use_api:
        if BASE_DIR not in sys.path: sys.path.append(BASE_DIR)
        from llm_api import call_llm_api

        print("🚀 使用云端 API 推理...", file=sys.stderr)
        result = call_llm_api(messages, settings_path)
    else:
        from local_engine import generate_local  # 复用常驻服务，避免每次重载 7B 模型

        result = generate_local(messages, max_new_tokens=150, max_input_tokens=2048, temperature=0.85, top_p=0.9,
                                on_progress=lambda m: print("[PROGRESS] " + m, file=sys.stderr))

    result = re.sub(r'\x1b\[[0-9;]*m', '', result).replace("[0m", "").replace("\x1b", "")
    print("OK:" + result)
except Exception as e:
    import traceback

    print(f"ERR: {traceback.format_exc()}")