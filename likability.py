"""好感度评分引擎。

设计要点（对应原实现的主要问题）：
1. 不再采信模型给出的单一数字，改为【多维度打分 + 固定权重加权】，总分可解释、可复现。
2. 解析失败时返回 None（评估失败），绝不用 50 之类的默认值冒充真实结果。
3. 引入置信度：结合成功解析的维度数与聊天样本量，样本不足时明确降级并提示。
4. 保留模型自评总分用于交叉校验，与加权分偏差过大时给出告警。
5. 每次评估落盘为历史记录，趋势图只能基于真实数据绘制。
"""

import os
import re
import json
import time

# ===== 评分维度与权重（权重之和为 1.0）=====
# 全部为正向维度：分数越高代表好感越高。
DIMENSIONS = [
    ("回应积极性", 0.20, "回复的速度、篇幅，是否敷衍或已读不回"),
    ("主动分享度", 0.20, "是否主动发起话题、分享日常生活与情绪"),
    ("情绪支持度", 0.20, "是否关心你、共情、安慰、为你提供情绪价值"),
    ("边界开放度", 0.15, "是否愿意聊私人话题、深夜闲聊、透露脆弱面"),
    ("话题延续度", 0.15, "是否接话、反问、延展话题，而非终结对话"),
    ("邀约接受度", 0.10, "是否接受或主动提出见面、共同活动的邀约"),
]

WEIGHTS = {name: w for name, w, _ in DIMENSIONS}
DIM_NAMES = [name for name, _, _ in DIMENSIONS]

RESULT_FILE = "yc.json"  # 最近一次完整评估
HISTORY_FILE = "yc_history.json"  # 历次评估，用于绘制真实趋势
LEGACY_FILE = "yc.txt"  # 旧版本遗留（仅存一个数字），读取时兼容
MAX_HISTORY = 60


def _dim_pattern(name):
    """兼容 `**回应积极性**：72`、`回应积极性: 72分`、`回应积极性：约 70` 等写法。"""
    return re.compile(r'\*{0,2}' + re.escape(name) + r'\*{0,2}\s*[：:]\s*\*{0,2}(\d{1,3})')


def _extract_evidence(line, name):
    """提取该维度行括号内的依据文本；没有括号则取数字之后的剩余内容。"""
    tail = re.split(r'\*{0,2}' + re.escape(name) + r'\*{0,2}\s*[：:]\s*\*{0,2}\d{1,3}', line, maxsplit=1)
    tail = tail[1] if len(tail) > 1 else ""
    m = re.search(r'[（(]([^）)]{4,})[）)]', tail)
    if m:
        return m.group(1).strip()
    return re.sub(r'^[\s，,、。.分]*', '', tail).strip()


def count_samples(chat_content):
    """统计聊天样本量：非空行即视为一条消息。"""
    return sum(1 for line in (chat_content or "").splitlines() if line.strip())


def parse_dimensions(text):
    """从模型输出中解析各维度分数与依据，返回 {维度: (分数, 依据)}。"""
    dims = {}
    for name in DIM_NAMES:
        pat = _dim_pattern(name)
        match = None
        for line in (text or "").splitlines():
            match = pat.search(line)
            if match:
                score = int(match.group(1))
                if 0 <= score <= 100:
                    dims[name] = (score, _extract_evidence(line, name))
                break
    return dims


def parse_model_score(text):
    """解析模型自评的综合好感度，用于与加权分交叉校验。"""
    m = re.search(r'(?:综合好感度|综合|总体好感度|好感度)\s*[：:]\s*\*{0,2}(\d{1,3})', text or "")
    if m:
        v = int(m.group(1))
        if 0 <= v <= 100:
            return v
    return None


def weighted_score(dims):
    """按权重加权；缺失维度不参与，权重重新归一化。"""
    total_w = sum(WEIGHTS[n] for n in dims)
    if total_w <= 0:
        return None
    raw = sum(dims[n][0] * WEIGHTS[n] for n in dims)
    return int(round(raw / total_w))


def confidence_level(valid_count, sample_count):
    """置信度：先看维度覆盖度，再用样本量降级。"""
    if valid_count >= 6:
        level = 2
    elif valid_count >= 4:
        level = 1
    else:
        level = 0
    if sample_count < 20:  # 样本过少，一律不可信
        level = 0
    elif sample_count < 60 and level > 0:
        level -= 1
    return ["低", "中", "高"][level]


def evaluate(model_text, chat_content) -> dict:
    """把模型输出转换为结构化的评估结果。

    返回 dict：ok / score / dims / model_score / confidence / sample_count / warnings / reason
    评估不成功时 ok=False 且 score=None —— 调用方应据此提示，而不是展示默认分。
    """
    sample_count = count_samples(chat_content)
    dims = parse_dimensions(model_text)
    score = weighted_score(dims)
    model_score = parse_model_score(model_text)
    confidence = confidence_level(len(dims), sample_count)

    warnings = []
    if not dims:
        return {
            "ok": False, "score": None, "dims": {}, "model_score": model_score,
            "confidence": "低", "sample_count": sample_count, "warnings": warnings,
            "reason": "未能从模型输出中解析出任何维度评分（输出格式不符合约定）",
        }

    missing = [n for n in DIM_NAMES if n not in dims]
    if missing:
        warnings.append(f"缺失 {len(missing)} 个维度（{'、'.join(missing)}），总分仅基于已识别维度加权")
    if sample_count < 20:
        warnings.append(f"聊天样本仅 {sample_count} 条，结论可靠性低，建议积累更多记录后再评估")
    if model_score is not None and abs(model_score - score) > 15:
        warnings.append(f"模型自评 {model_score} 分与维度加权 {score} 分偏差较大，已采用加权结果")

    return {
        "ok": True, "score": score, "dims": {n: dims[n][0] for n in DIM_NAMES if n in dims},
        "dims_evidence": {n: dims[n][1] for n in DIM_NAMES if n in dims},
        "model_score": model_score, "confidence": confidence, "sample_count": sample_count,
        "warnings": warnings, "reason": "",
    }


# ==========================================
# 落盘与读取
# ==========================================
def _now():
    return time.strftime("%Y-%m-%d %H:%M")


def load_latest(folder):
    """读取最近一次评估。兼容旧版 yc.txt（只有一个数字，无维度明细）。"""
    path = os.path.join(folder, RESULT_FILE)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("score") is not None:
                data.setdefault("ok", True)
                data.setdefault("dims", {})
                data.setdefault("confidence", "低")
                data.setdefault("warnings", [])
                data.setdefault("sample_count", 0)
                data.setdefault("time", "")
                return data
        except Exception:
            pass

    legacy = os.path.join(folder, LEGACY_FILE)
    if os.path.exists(legacy):
        try:
            with open(legacy, "r", encoding="utf-8-sig") as f:
                raw = f.read().strip()
            if raw:
                return {"ok": True, "score": int(raw), "dims": {}, "confidence": "低",
                        "sample_count": 0, "warnings": ["旧格式缓存，无维度明细"], "time": "", "legacy": True}
        except Exception:
            pass
    return None


def load_history(folder):
    path = os.path.join(folder, HISTORY_FILE)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_result(folder, result):
    """写入最新结果并追加到历史。评估失败（ok=False）不会覆盖已有结果。"""
    if not result.get("ok"):
        return
    result = dict(result)
    result["time"] = _now()
    result.pop("dims_evidence", None)  # 历史里只留分数，避免文件膨胀

    with open(os.path.join(folder, RESULT_FILE), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    history = load_history(folder)
    history.append({"t": result["time"], "score": result["score"], "confidence": result.get("confidence", "低"),
                    "sample_count": result.get("sample_count", 0), "dims": result.get("dims", {})})
    with open(os.path.join(folder, HISTORY_FILE), "w", encoding="utf-8") as f:
        json.dump(history[-MAX_HISTORY:], f, ensure_ascii=False, indent=2)


def prompt_block():
    """生成要求模型输出维度评分的提示片段。"""
    lines = "\n".join([f"- {name}：0-100的数字（依据：{desc}）" for name, _, desc in DIMENSIONS])
    return f"""请严格按以下 Markdown 格式输出，不要增减章节：
### 💖 好感度维度评分
{lines}
- 综合好感度：0-100的数字（你对整体好感的主观判断，用于与维度加权结果交叉校验）

### 📊 关系状态多维分析
- **热情度**：（分析）
- **依赖感**：（分析）
- **边界感**：（分析）

### 💡 长期关系破局点
（给出2条具体建议）

【评分要求】
1. 每个维度必须给出 0-100 的整数，格式严格为「维度名：数字（依据：...）」。
2. 依据必须引用聊天记录中的具体表现，不要写空话。
3. 若聊天记录极少或某维度无任何线索，如实给低分并在依据中写明「线索不足」。
4. 不要为了讨好而给高分，分数必须能被聊天记录中的事实支撑。"""
