from __future__ import annotations

import argparse
import smtplib
from email.message import EmailMessage
from pathlib import Path


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description="发送 SocialEval 运维告警")
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--unit", required=True)
    args = parser.parse_args()
    env = read_env(args.env_file)
    recipients = [
        item.strip()
        for item in env.get("OPERATIONS_ALERT_RECIPIENTS", "").split(",")
        if item.strip()
    ]
    if not recipients:
        raise SystemExit("未配置 OPERATIONS_ALERT_RECIPIENTS")

    message = EmailMessage()
    message["Subject"] = f"【SocialEval 运维告警】{args.unit}"
    message["From"] = env["SMTP_FROM"]
    message["To"] = ", ".join(recipients)
    message.set_content(
        f"生产环境运维单元 {args.unit} 执行失败，请登录交大云主机检查 systemd 和容器日志。"
    )
    host = env["SMTP_HOST"]
    port = int(env.get("SMTP_PORT", "587"))
    if env.get("SMTP_SSL", "false").lower() == "true":
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=15)
    else:
        smtp = smtplib.SMTP(host, port, timeout=15)
    with smtp:
        if env.get("SMTP_STARTTLS", "true").lower() == "true":
            smtp.starttls()
        if env.get("SMTP_USER"):
            smtp.login(env["SMTP_USER"], env.get("SMTP_PASSWORD", ""))
        smtp.send_message(message)


if __name__ == "__main__":
    main()
