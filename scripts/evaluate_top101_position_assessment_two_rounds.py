#!/usr/bin/env python3
"""Top101 五轴两轮评估兼容入口。

共用实现已迁移到 ``src.evaluation.position.workflow``；保留本文件以兼容既有命令、
测试和外部自动化。
"""

from src.evaluation.position.workflow import *  # noqa: F403


if __name__ == "__main__":
    main()  # noqa: F405
