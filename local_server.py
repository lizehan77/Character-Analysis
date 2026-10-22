"""常驻本地推理服务。

模型只加载一次，之后所有 worker（画像分析 / 实时对话 / 模拟 / 全局扫描）
通过 127.0.0.1 上的 HTTP 接口复用同一份模型，避免每次点击都重新加载 7B 权重。

启动方式（通常由 local_engine 自动拉起，也可手动）：
    python local_server.py
"""
import os
import sys
import json
import time
import uuid
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT_FILE = os.path.join(BASE_DIR, ".local_server.json")
LOG_FILE = os.path.join(BASE_DIR, ".local_server.log")
MODEL_PATH = r"D:\model\qwen--Qwen2-7B-Instruct\snapshots\master"

# 空闲多久后自动退出，避免关掉界面后仍长期占用显存（秒）
IDLE_TIMEOUT = int(os.environ.get("LOCAL_SERVER_IDLE_TIMEOUT", "900"))

TOKEN = uuid.uuid4().hex  # 防止误连到占用同一端口的其它程序

_state = {"status": "loading", "error": None}
_lock = threading.Lock()  # 模型不支持并发 generate，串行化
_last_used = time.time()
_model = None
_tokenizer = None


def log(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def load_model():
    global _model, _tokenizer
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

    log("开始加载模型：" + MODEL_PATH)
    bnb_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_use_double_quant=True, bnb_4bit_quant_type="nf4",
                                    bnb_4bit_compute_dtype=torch.float16)
    _tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    _model = AutoModelForCausalLM.from_pretrained(MODEL_PATH, torch_dtype=torch.float16, device_map="auto",
                                                  trust_remote_code=True, quantization_config=bnb_config)
    log("模型加载完成，device=" + str(_model.device))


def do_generate(payload):
    messages = payload["messages"]
    text = _tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    max_input = int(payload.get("max_input_tokens", 2048))
    inputs = _tokenizer([text], return_tensors="pt", truncation=True, max_length=max_input).to(_model.device)
    outputs = _model.generate(**inputs,
                              max_new_tokens=int(payload.get("max_new_tokens", 1024)),
                              do_sample=bool(payload.get("do_sample", True)),
                              temperature=float(payload.get("temperature", 0.7)),
                              top_p=float(payload.get("top_p", 0.9)),
                              use_cache=True,
                              pad_token_id=_tokenizer.eos_token_id)
    outputs = outputs[:, inputs["input_ids"].shape[-1]:]
    text = _tokenizer.decode(outputs[0], skip_special_tokens=True)
    # 清除模型偶发的 ANSI 转义序列
    import re
    return re.sub(r'\x1b\[[0-9;]*m', '', text).replace("[0m", "").replace("\x1b", "").strip()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 静音默认访问日志
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        global _last_used
        if self.path == "/health":
            _last_used = time.time()  # 探测也视为活跃，避免加载期间被空闲超时误杀
            self._json({"status": _state["status"], "error": _state["error"], "token": TOKEN})
        elif self.path == "/shutdown":
            self._json({"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        global _last_used
        if self.path != "/generate":
            self._json({"error": "not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as e:
            self._json({"error": f"bad request: {e}"}, 400)
            return
        if payload.get("token") != TOKEN:
            self._json({"error": "forbidden"}, 403)
            return
        if _state["status"] != "ready":
            self._json({"error": f"model not ready: {_state['status']}"}, 503)
            return

        _last_used = time.time()
        try:
            with _lock:
                result = do_generate(payload)
            _last_used = time.time()
            self._json({"result": result})
        except Exception as e:
            log("生成失败：" + traceback.format_exc())
            self._json({"error": str(e)}, 500)


def main():
    global _last_used
    log("=" * 20 + " 服务启动 " + "=" * 20)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)  # 端口由系统分配，避免冲突
    port = server.server_address[1]
    with open(PORT_FILE, "w", encoding="utf-8") as f:
        json.dump({"port": port, "token": TOKEN, "pid": os.getpid()}, f)
    log(f"监听 127.0.0.1:{port}（空闲 {IDLE_TIMEOUT}s 后自动退出）")

    def idle_watch():
        while True:
            time.sleep(10)
            if time.time() - _last_used > IDLE_TIMEOUT:
                log("空闲超时，自动退出")
                threading.Thread(target=server.shutdown, daemon=True).start()
                return

    threading.Thread(target=idle_watch, daemon=True).start()

    try:
        load_model()
        _state["status"] = "ready"
        _last_used = time.time()
        log("状态：ready")
    except Exception:
        _state["status"] = "error"
        _state["error"] = traceback.format_exc()
        log("模型加载失败：\n" + traceback.format_exc())

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        log("服务已退出")
        try:
            os.remove(PORT_FILE)
        except Exception:
            pass


if __name__ == "__main__":
    main()
