"""本地推理客户端。

对上层 worker 只暴露一个 generate_local()：
  - 优先复用常驻服务 local_server.py（模型已加载，省去每次 20s+ 的加载开销）
  - 服务不存在时自动拉起并等待就绪
  - 服务不可用（CUDA/显存/依赖问题）时自动回退为"本进程内单次加载"，保证功能不中断
"""
import os
import sys
import json
import time
import subprocess
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT_FILE = os.path.join(BASE_DIR, ".local_server.json")
SERVER_PATH = os.path.join(BASE_DIR, "local_server.py")

STARTUP_TIMEOUT = 900  # 等待服务加载完成的超时（秒）
MODEL_PATH = r"D:\model\qwen--Qwen2-7B-Instruct\snapshots\master"


def _read_port_file():
    try:
        with open(PORT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _health(port, token):
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/health", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("token") != token:
            return None
        return data
    except Exception:
        return None


def _start_server():
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([sys.executable, SERVER_PATH], cwd=BASE_DIR, creationflags=flags,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _ensure_server(on_progress=None):
    """返回 (port, token)；必要时拉起服务并等待模型就绪。"""
    info = _read_port_file()
    if info:
        st = _health(info.get("port"), info.get("token"))
        if st is not None:
            if st.get("status") == "ready":
                return info["port"], info["token"]
            if st.get("status") == "error":
                raise RuntimeError("本地推理服务加载模型失败：" + str(st.get("error")))
        else:
            try:  # 陈旧端口文件
                os.remove(PORT_FILE)
            except Exception:
                pass

    if on_progress:
        on_progress("正在启动本地推理服务（首次使用需加载模型，之后自动复用）...")
    _start_server()

    deadline = time.time() + STARTUP_TIMEOUT
    notified_loading = False
    while time.time() < deadline:
        time.sleep(1)
        info = _read_port_file()
        if not info:
            continue
        st = _health(info.get("port"), info.get("token"))
        if st is None:
            continue
        status = st.get("status")
        if status == "ready":
            if on_progress:
                on_progress("本地推理服务已就绪，开始生成...")
            return info["port"], info["token"]
        if status == "error":
            raise RuntimeError("本地推理服务加载模型失败：" + str(st.get("error")))
        if status == "loading" and not notified_loading and on_progress:
            on_progress("模型加载中（约 20-60 秒，仅首次）...")
            notified_loading = True
    raise RuntimeError("本地推理服务启动超时")


def _generate_inprocess(messages, max_new_tokens, max_input_tokens, temperature, top_p, do_sample):
    """回退方案：在当前进程内加载模型并生成。"""
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

    bnb_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_use_double_quant=True, bnb_4bit_quant_type="nf4",
                                    bnb_4bit_compute_dtype=torch.float16)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(MODEL_PATH, torch_dtype=torch.float16, device_map="auto",
                                                 trust_remote_code=True, quantization_config=bnb_config)
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer([text], return_tensors="pt", truncation=True, max_length=max_input_tokens).to(model.device)
    outputs = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=do_sample, temperature=temperature,
                             top_p=top_p, use_cache=True, pad_token_id=tokenizer.eos_token_id)
    outputs = outputs[:, inputs["input_ids"].shape[-1]:]
    import re
    return re.sub(r'\x1b\[[0-9;]*m', '', tokenizer.decode(outputs[0], skip_special_tokens=True)).replace("[0m", "") \
        .replace("\x1b", "").strip()


def generate_local(messages, max_new_tokens=1024, max_input_tokens=2048, temperature=0.7, top_p=0.9,
                   do_sample=True, on_progress=None, timeout=900):
    try:
        port, token = _ensure_server(on_progress)
    except Exception as e:
        if on_progress:
            on_progress(f"常驻服务不可用（{e}），改为单次加载模型（较慢）...")
        return _generate_inprocess(messages, max_new_tokens, max_input_tokens, temperature, top_p, do_sample)

    payload = {"token": token, "messages": messages, "max_new_tokens": max_new_tokens,
               "max_input_tokens": max_input_tokens, "temperature": temperature, "top_p": top_p,
               "do_sample": do_sample}
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/generate",
                                     data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        if on_progress:
            on_progress(f"调用本地服务失败（{e}），改为单次加载模型（较慢）...")
        return _generate_inprocess(messages, max_new_tokens, max_input_tokens, temperature, top_p, do_sample)

    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("result", "")


def stop_server():
    """请求常驻服务退出（best-effort，失败不影响主程序关闭）。"""
    info = _read_port_file()
    if not info:
        return
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{info['port']}/shutdown", timeout=2).read()
    except Exception:
        pass


if __name__ == "__main__":
    # 自检：python local_engine.py
    t0 = time.time()
    print(generate_local([{"role": "user", "content": "用一句话回复：你好"}], max_new_tokens=32,
                         on_progress=lambda m: print("[PROGRESS]", m)))
    print(f"耗时 {time.time() - t0:.1f}s")
