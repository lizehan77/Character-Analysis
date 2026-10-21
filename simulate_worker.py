import sys
import os
import json
import re

folder_path = sys.argv[1]
history = json.loads(sys.argv[2])
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
        outputs = model.generate(**inputs, max_new_tokens=150, temperature=0.85, top_p=0.9, use_cache=True,
                                 pad_token_id=tokenizer.eos_token_id)
        outputs = outputs[:, inputs["input_ids"].shape[-1]:]
        result = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

    result = re.sub(r'\x1b\[[0-9;]*m', '', result).replace("[0m", "").replace("\x1b", "")
    print("OK:" + result)
except Exception as e:
    import traceback

    print(f"ERR: {traceback.format_exc()}")