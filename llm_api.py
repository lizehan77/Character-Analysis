# llm_api.py
import json
import os
from openai import OpenAI


def call_llm_api(messages, config_path="settings.json"):
    if not os.path.exists(config_path):
        raise Exception("未找到配置文件 settings.json")

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    api_key = config.get("api_key", "")
    base_url = config.get("base_url", "https://api.deepseek.com")  # 默认用 DeepSeek
    model_name = config.get("model_name", "deepseek-chat")

    if not api_key:
        raise Exception("API Key 为空，请先在 settings.json 中配置")

    # 初始化客户端
    client = OpenAI(api_key=api_key, base_url=base_url)

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.7,
            max_tokens=1024
        )
        return response.choices[0].message.content
    except Exception as e:
        raise Exception(f"API 请求失败: {str(e)}")