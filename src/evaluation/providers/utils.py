import re


def extract_json(text: str) -> str:
    """从模型输出中提取 JSON，处理 markdown 包裹和前缀后缀"""
    # 尝试提取 ```json ... ``` 块
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1)

    # 尝试提取 ``` ... ``` 块
    match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        candidate = match.group(1)
        if candidate.startswith("{"):
            return candidate

    # 尝试找到最外层 { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    return text


def normalize_json_keys(data):
    """递归去除 dict 键名开头的逗号与空白。

    个别模型（如开启思考模式的 qwen）偶发把分隔逗号写进下一个键的引号内，
    例如本该输出 `"summary": "...", "score_rationale": ...`，实际输出
    `"summary": "...", ",score_rationale": ...`，解析后键名以逗号开头，
    导致必填字段校验失败。契约键名不会以逗号开头，去除前导逗号是安全的。
    """
    if isinstance(data, dict):
        return {
            (key.lstrip(", \t\r\n") if isinstance(key, str) else key): (
                normalize_json_keys(value)
            )
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [normalize_json_keys(item) for item in data]
    return data
