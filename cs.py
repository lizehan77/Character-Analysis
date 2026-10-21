import torch
import time
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig


def test_environment():
    print("=" * 50)
    print("1. 基础环境检测")
    print("=" * 50)
    print(f"PyTorch 版本: {torch.__version__}")
    print(f"CUDA 是否可用: {torch.cuda.is_available()}")

    if torch.cuda.is_available():
        print(f"GPU 设备名称: {torch.cuda.get_device_name(0)}")
        vram_total = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
        print(f"GPU 显存总量: {vram_total:.2f} GB")
    else:
        print("⚠️ 未检测到 CUDA，模型将跑在 CPU 上（会非常慢）！")
        return

    print("\n" + "=" * 50)
    print("2. 模型加载测试")
    print("=" * 50)

    model_path = r"D:\model\qwen--Qwen2-7B-Instruct\snapshots\master"

    try:
        print("⏳ 正在加载 Tokenizer...")
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

        print("⏳ 正在加载模型 (4-bit 量化)...")
        start_time = time.time()

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16
        )

        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True,
            quantization_config=bnb_config
        )

        load_time = time.time() - start_time
        print(f"✅ 模型加载成功！耗时: {load_time:.2f} 秒")

        vram_used = torch.cuda.memory_allocated() / 1024 ** 3
        print(f"📊 模型加载后显存占用: {vram_used:.2f} GB")

    except Exception as e:
        print(f"❌ 模型加载失败！错误信息:\n{e}")
        return

    print("\n" + "=" * 50)
    print("3. 简单推理测试")
    print("=" * 50)

    try:
        prompt = "你好，请用一句话介绍一下你自己。"
        print(f"输入: {prompt}")

        messages = [{"role": "user", "content": prompt}]
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer([text], return_tensors="pt").to("cuda")

        print("⏳ 正在推理...")
        start_time = time.time()

        outputs = model.generate(
            **inputs,
            max_new_tokens=50,
            temperature=0.7,
            use_cache=True,
            pad_token_id=tokenizer.eos_token_id
        )

        outputs = outputs[:, inputs["input_ids"].shape[-1]:]
        result = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

        infer_time = time.time() - start_time
        print(f"✅ 推理成功！耗时: {infer_time:.2f} 秒")
        print(f"模型回复: {result}")

    except Exception as e:
        print(f"❌ 推理失败！错误信息:\n{e}")


if __name__ == "__main__":
    test_environment()
    print("\n" + "=" * 50)
    print("测试结束。如果以上全部通过，说明你的环境完美！")
    print("=" * 50)