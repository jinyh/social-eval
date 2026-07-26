import logging
import json
import sys

from src.core.time import utc_now


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": utc_now().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """安装一次结构化日志处理器，避免测试或应用工厂重复挂载。"""

    root_logger = logging.getLogger()
    if any(
        getattr(handler, "_socialeval_handler", False)
        for handler in root_logger.handlers
    ):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler._socialeval_handler = True  # type: ignore[attr-defined]
    handler.setFormatter(JSONFormatter())
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.addHandler(handler)


logger = logging.getLogger("socialeval")
