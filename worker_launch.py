"""启动 worker 子进程的统一入口。

Windows 中文环境下，Python 子进程的 stdout/stderr 默认使用系统 locale（GBK/cp936）编码，
而调用方按 UTF-8 解码会得到乱码，中文维度名、正文、报错信息全部变成不可识别字符。
这里统一强制子进程使用 UTF-8 输出，与调用方的 encoding="utf-8" 保持一致。
"""
import os
import sys
import subprocess


def utf8_env():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def launch_worker(worker_path, args, **kwargs):
    """以 UTF-8 输出启动 worker，返回 Popen。其余参数同 subprocess.Popen。"""
    kwargs.setdefault("stdout", subprocess.PIPE)
    kwargs.setdefault("stderr", subprocess.STDOUT)
    kwargs.setdefault("env", utf8_env())
    return subprocess.Popen([sys.executable, worker_path, *args], **kwargs)


def force_utf8_stdio():
    """在 worker 进程内部调用：把自身 stdout/stderr 切到 UTF-8（命令行直接运行时同样生效）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
