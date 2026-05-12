#!/usr/bin/env python3
"""显示当前 .env 中的 SSS 配置"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.config import settings

print("=" * 60)
print("当前 SSS Provider 配置")
print("=" * 60)

print(f"\nSSS_API_KEY: {settings.sss_api_key[:20]}..." if settings.sss_api_key else "未配置")
print(f"SSS_BASE_URL: {settings.sss_base_url}")

print("\n" + "=" * 60)
print("建议检查的配置")
print("=" * 60)

print("\n如果在 codex 环境中可以使用，请确认:")
print("1. codex 中使用的 Base URL 是否与上面显示的一致？")
print("2. codex 中使用的模型名称是什么？")
print("3. codex 中是否有其他特殊配置？")

print("\n可能的 Base URL 选项:")
print("  - https://codex1.sssaicode.com/api/v1  (当前配置)")
print("  - https://api.sss.ai/v1  (默认值)")
print("  - https://codex1.sssaicode.com")
print("  - 其他？")
