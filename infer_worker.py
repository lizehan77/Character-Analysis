import sys
import os
import json
import re

folder_path = sys.argv[1]
mode = sys.argv[2]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
settings_path = os.path.join(BASE_DIR, "settings.json")

use_api = False
if os.path.exists(settings_path):
    with open(settings_path, "r", encoding="utf-8") as f:
        use_api = json.load(f).get("use_api", False)

MODEL_PATH = r"D:\model\qwen--Qwen2-7B-Instruct\snapshots\master"
MAX_INPUT_TOKENS = 2048  # 输入窗口，all / new 两种模式统一
RESERVE_TOKENS = 700  # 预留给模板与已有画像
MAX_NEW_TOKENS = 2048  # 画像共 9 个小节，1024 极易被截断


def clip_tail(text, max_tokens):
    """按 token 预算保留文本【尾部】：聊天记录越靠后越新，绝不能被整体右截断。

    本地模型现在跑在常驻服务进程里，worker 拿不到 tokenizer，故统一按字符估算
    （Qwen2 中文约 1.2~1.5 字/token，取保守值 1.2，宁可少留一点）。
    """
    if max_tokens <= 0 or not text: return ""
    max_chars = int(max_tokens * 1.2)
    return text[-max_chars:] if len(text) > max_chars else text


def run_analysis():
    ltjl_path = os.path.join(folder_path, "ltjl.txt")
    new_ltjl_path = os.path.join(folder_path, "new_ltjl.txt")
    persona_path = os.path.join(folder_path, "persona.md")

    target_file = new_ltjl_path if mode == "new" else ltjl_path
    try:  # utf-8-sig：用户用记事本编辑后会带 BOM，否则空文件会被当成有内容，模型凭空编造画像
        with open(target_file, "r", encoding="utf-8-sig") as f:
            chat_content = f.read()
    except Exception as e:
        raise Exception(f"读取文件失败：{e}")
    if not chat_content.strip():
        raise Exception("聊天记录为空！")

    old_persona = ""
    if os.path.exists(persona_path):
        with open(persona_path, "r", encoding="utf-8-sig") as f:
            old_persona = f.read().strip()

    # 聊天记录位于 prompt 末尾，必须先按预算裁剪，否则会被 truncation 从右侧砍掉最新内容
    chat_content = clip_tail(chat_content, MAX_INPUT_TOKENS - RESERVE_TOKENS)
    if mode == "new":
        old_persona = clip_tail(old_persona, RESERVE_TOKENS // 2)

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
        if BASE_DIR not in sys.path: sys.path.append(BASE_DIR)
        from llm_api import call_llm_api
        print("[PROGRESS] 使用云端 API 推理...", file=sys.stderr)
        result = call_llm_api(messages, settings_path)
    else:
        from local_engine import generate_local  # 复用常驻服务，避免每次重载 7B 模型

        result = generate_local(messages, max_new_tokens=MAX_NEW_TOKENS, max_input_tokens=MAX_INPUT_TOKENS,
                                temperature=0.7, top_p=0.8,
                                on_progress=lambda m: print("[PROGRESS] " + m, file=sys.stderr))
        print("[PROGRESS] 生成完成，正在写入画像...", file=sys.stderr)

    result = (result or "").strip()
    if not result:
        raise Exception("模型返回为空，已保留原画像。")
    if "## 二、沟通策略" not in result and old_persona:
        raise Exception("输出疑似被截断（缺少「## 二、沟通策略」章节），已保留原画像，请调大 MAX_NEW_TOKENS 后重试。")

    with open(persona_path, "w", encoding="utf-8") as f:
        f.write(result)
    return result


if __name__ == "__main__":
    try:
        res = run_analysis()
        print("OK:" + res)
    except Exception as e:
        import traceback

        print(f"ERR: {e}\n{traceback.format_exc()}")
        sys.exit(1)