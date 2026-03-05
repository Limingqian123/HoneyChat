# services/honeypot/scripts/healthcheck.py
#!/usr/bin/env python3
"""
HoneyChat 蜜罐服务健康检查脚本。

检查 SSH (2222) 和 HTTP (8080) 端口是否处于监听状态。
如果两个端口都正常，返回 0 (健康)，否则返回 1 (不健康)。
"""

import socket
import sys
import os

# 从环境变量获取端口，如果没有则使用默认值
SSH_PORT = int(os.environ.get("HONEYPOT_SSH_PORT", "2222"))
HTTP_PORT = int(os.environ.get("HONEYPOT_HTTP_PORT", "8080"))
HOST = "127.0.0.1"


def check_port(port: int) -> bool:
    """
    尝试连接指定端口，判断是否可连接。

    Args:
        port: 要检查的端口号

    Returns:
        如果端口开放且可连接返回 True，否则返回 False
    """
    try:
        with socket.create_connection((HOST, port), timeout=2):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def main() -> None:
    """主函数，执行健康检查并退出。"""
    ssh_ok = check_port(SSH_PORT)
    http_ok = check_port(HTTP_PORT)

    if ssh_ok and http_ok:
        print(f"Health check OK: SSH={SSH_PORT} OK, HTTP={HTTP_PORT} OK")
        sys.exit(0)
    else:
        print(
            f"Health check FAIL: SSH={SSH_PORT} {'OK' if ssh_ok else 'FAIL'}, "
            f"HTTP={HTTP_PORT} {'OK' if http_ok else 'FAIL'}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()