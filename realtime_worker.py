import sys
import os
import json
import re

folder_path = sys.argv[1]
chat_history = json.loads(sys.argv[2])
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
if base_setting: final_persona += f"【基础人设】\n{base_setting}\n"
if analyzed_persona: final_persona += f"【深度性格分析】\n{analyzed_persona}\n"

system_prompt = f"""你现在是顶级的情感沟通专家和军师。请仔细分析对方目前的情绪状态，并结合性格推演回复。
【对方的人物画像】：
{final_persona if final_persona else "暂无画像"}
请严格按以下格式输出（不要废话）：
### 🔍 对方当前情绪分析
（分析情绪状态）
### 💡 军师回复策略
（采取什么策略）
### 🎭 她的内心潜台词
（用符合她人设的语气写一句）
### 💬 推荐回复
1. **【稳妥型】**：直接写回复内容
2. **【幽默型】**：直接写回复内容
3. **【情绪价值型】**：直接写回复内容"""

chat_text = "".join([f"{'我' if msg['role'] == 'user' else '对方'}: {msg['content']}\n" for msg in chat_history])
messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"【聊天记录】：\n{chat_text}"}]

try:
    if use_api:
        if BASE_DIR not in sys.path: sys.path.append(BASE_DIR)
        from llm_api import call_llm_api

        print("🚀 使用云端 API 推理...", file=sys.stderr)
        result = call_llm_api(messages, settings_path)
    else:
        from local_engine import generate_local  # 复用常驻服务，避免每次重载 7B 模型

        result = generate_local(messages, max_new_tokens=600, max_input_tokens=2048, temperature=0.75, top_p=0.9,
                                on_progress=lambda m: print("[PROGRESS] " + m, file=sys.stderr))

    result = re.sub(r'\x1b\[[0-9;]*m', '', result).replace("[0m", "").replace("\x1b", "")
    print("OK:" + result)
except Exception as e:
    import traceback

    print(f"ERR: {traceback.format_exc()}")