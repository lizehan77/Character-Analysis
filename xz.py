from modelscope import snapshot_download

if __name__ == "__main__":
    # cache_dir 指定保存到 D:\model
    model_dir = snapshot_download('qwen/Qwen2-7B-Instruct', cache_dir='D:/model')
    print("✅ 模型下载完成，本地路径：", model_dir)
