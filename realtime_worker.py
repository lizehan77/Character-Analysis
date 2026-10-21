import sys
import os
import json
import re

folder_path = sys.argv[1]
chat_history = json.loads(sys.argv[2])
settings_path = r"D:\PyCharm 2026.2.1\wj\speak\settings.json"

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
        root_dir = r"D:\PyCharm 2026.2.1\wj\speak"
        if root_dir not in sys.path: sys.path.append(root_dir)
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
        outputs = model.generate(**inputs, max_new_tokens=600, temperature=0.75, top_p=0.9, use_cache=True,
                                 pad_token_id=tokenizer.eos_token_id)
        outputs = outputs[:, inputs["input_ids"].shape[-1]:]
        result = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

    result = re.sub(r'\x1b\[[0-9;]*m', '', result).replace("[0m", "").replace("\x1b", "")
    print("OK:" + result)
except Exception as e:
    import traceback

    print(f"ERR: {traceback.format_exc()}")