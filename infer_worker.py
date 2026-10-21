import sys
import os
import json
import re

folder_path = sys.argv[1]
mode = sys.argv[2]
settings_path = r"D:\PyCharm 2026.2.1\wj\speak\settings.json"

use_api = False
if os.path.exists(settings_path):
    with open(settings_path, "r", encoding="utf-8") as f:
        use_api = json.load(f).get("use_api", False)


def run_analysis():
    ltjl_path = os.path.join(folder_path, "ltjl.txt")
    new_ltjl_path = os.path.join(folder_path, "new_ltjl.txt")
    persona_path = os.path.join(folder_path, "persona.md")

    target_file = new_ltjl_path if mode == "new" else ltjl_path
    try:
        with open(target_file, "r", encoding="utf-8") as f:
            chat_content = f.read()
        if not chat_content.strip(): return "聊天记录为空！"
    except Exception as e:
        return f"读取文件失败：{e}"

    old_persona = ""
    if os.path.exists(persona_path):
        with open(persona_path, "r", encoding="utf-8") as f:
            old_persona = f.read().strip()

    if mode == "new":
        prompt = f"""你是专业的人物画像分析师。你的任务是将【新增聊天记录】中的发现，**增量合并**到【已有的人物画像】中。
【称呼要求】：请一律使用“对方”来代指被分析的人。
【合并规则】：1. 绝不允许丢失旧信息；2. 只有明确推翻时才删除；3. 补充新特征。
【已有画像】：{old_persona if old_persona else "（暂无）"}
【新增记录】：{chat_content}
# 输出要求（严格按以下结构输出）
## 一、人物分析
### 沟通风格
### 情绪模式
### 表达习惯
### 人际内心需求
### 相处/沟通原则
### 喜好偏好
### 饮食口味偏好
## 二、沟通策略
### 应该多做什么
### 需要避开哪些雷区"""
    else:
        prompt = f"""你是对话沟通分析师。下面是我方与对方的微信聊天记录，请**只分析对方**。
【称呼要求】：请一律使用“对方”来代指。
# 分析维度
1. 沟通风格 2. 情绪模式 3. 表达习惯 4. 人际内心需求 5. 相处/沟通原则 6. 喜好偏好 7. 饮食口味偏好
# 输出模块
## 一、人物分析
遵守：1.不复述原文；2.有聊天内容支撑；3.使用Markdown；4.仅做沟通分析；5.不分析我方。
### 沟通风格
### 情绪模式
### 表达习惯
### 人际内心需求
### 相处/沟通原则
### 喜好偏好
### 饮食口味偏好
## 二、沟通策略
### 应该多做什么
### 需要避开哪些雷区
聊天记录：
{chat_content}"""

    messages = [{"role": "user", "content": prompt}]

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
        MAX_INPUT_TOKENS = 2048 if mode == "new" else 1024
        inputs = tokenizer([text], return_tensors="pt", truncation=True, max_length=MAX_INPUT_TOKENS).to("cuda")
        torch.cuda.empty_cache()
        outputs = model.generate(**inputs, max_new_tokens=1024, temperature=0.7, use_cache=(mode == "new"),
                                 pad_token_id=tokenizer.eos_token_id)
        outputs = outputs[:, inputs["input_ids"].shape[-1]:]
        result = tokenizer.decode(outputs[0], skip_special_tokens=True)

    with open(persona_path, "w", encoding="utf-8") as f:
        f.write(result)
    return result


if __name__ == "__main__":
    try:
        res = run_analysis()
        print("OK:" + res)
    except Exception as e:
        import traceback

        print(f"ERR: {traceback.format_exc()}")
        sys.exit(1)