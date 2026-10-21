import sys
import os
import json
import re

folder_path = sys.argv[1]

# ======== 动态获取路径 ========
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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

prompt = f"""你是一位资深的心理与情感关系分析师。请阅读以下全部聊天记录及画像。
【已有画像】：
{old_persona if old_persona else "暂无"}
【全部聊天记录】：
{chat_content}
请严格按以下 Markdown 格式输出：
### 💖 当前好感度综合评估
（严格按格式输出：好感度: 0-100的数字%）
### 📊 关系状态多维分析
- **热情度**：（分析）
- **依赖感**：（分析）
- **边界感**：（分析）
### 💡 长期关系破局点
（给出2条建议）"""

messages = [{"role": "user", "content": prompt}]

try:
    if use_api:
        if BASE_DIR not in sys.path: sys.path.append(BASE_DIR)
        from llm_api import call_llm_api

        print("🚀 使用云端 API 推理...", file=sys.stderr)
        result = call_llm_api(messages, settings_path)
    else:
        print("⏳ 使用本地模型推理...", file=sys.stderr)
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

        model_path = r"D:\model\qwen--Qwen2-7B-Instruct\snapshots\master"
        bnb_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_use_double_quant=True, bnb_4bit_quant_type="nf4",
                                        bnb_4bit_compute_dtype=torch.float16)
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.float16, device_map="auto",
                                                     trust_remote_code=True, quantization_config=bnb_config)

        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer([text], return_tensors="pt", truncation=True, max_length=2048).to("cuda")
        torch.cuda.empty_cache()
        outputs = model.generate(**inputs, max_new_tokens=800, temperature=0.7, use_cache=True,
                                 pad_token_id=tokenizer.eos_token_id)
        outputs = outputs[:, inputs["input_ids"].shape[-1]:]
        result = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

    result = re.sub(r'\x1b\[[0-9;]*m', '', result).replace("[0m", "").replace("\x1b", "")

    score = 50
    match = re.search(r'好感度[:：]\s*(\d+)', result)
    if match: score = min(100, int(match.group(1)))

    with open(yc_path, "w", encoding="utf-8") as f:
        f.write(str(score))
    print(f"✅ 好感度 {score}% 已保存", file=sys.stderr)

    print("OK:" + result)
except Exception as e:
    import traceback

    print(f"ERR: {traceback.format_exc()}")