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
        return text[start:end + 1]

    return text