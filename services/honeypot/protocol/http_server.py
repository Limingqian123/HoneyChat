# services/honeypot/protocol/http_server.py
"""
HTTP 协议模拟模块。

基于 Flask 实现 HTTP 蜜罐，捕获所有请求（包括任意路径和方法），
将请求信息转换为命令字符串，通过 handler.process_command 处理，
并返回伪造的 HTTP 响应。
"""

import threading
import time
from typing import Dict, Any, Optional, List
import asyncio
from flask import Flask, request, Response, jsonify, abort
import structlog
from werkzeug.serving import make_server
from werkzeug.exceptions import NotFound

import handler
from config import settings
from utils.ip_utils import extract_client_ip, ThreatIntelChecker

logger = structlog.get_logger(__name__)

# 全局 Flask 应用
app = Flask(__name__)

# 威胁情报检查器实例（将在初始化时设置）
_threat_checker: Optional[ThreatIntelChecker] = None


def init_threat_checker(checker: ThreatIntelChecker) -> None:
    """设置威胁情报检查器（由主程序传入）"""
    global _threat_checker
    _threat_checker = checker


def _get_client_ip() -> str:
    """
    从 Flask 请求中提取客户端真实 IP。
    """
    # 信任代理列表（可从配置加载，此处简化，信任所有内网代理）
    # 实际生产环境应根据网络拓扑设置
    trusted_proxies = ["127.0.0.1", "::1", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
    return extract_client_ip(
        headers=dict(request.headers),
        remote_addr=request.remote_addr,
        trusted_proxies=trusted_proxies,
    ) or request.remote_addr or "0.0.0.0"


def _get_threat_tags(ip: str) -> List[str]:
    """
    获取 IP 的威胁标签（异步，但这里简单同步等待，因为查询可能很快）。
    实际生产环境可考虑缓存或后台预取。
    """
    if not _threat_checker:
        return []
    try:
        result = asyncio.run(_threat_checker.check_ip(ip))
        tags = []
        if result.is_malicious:
            tags.append("malicious")
        if result.abuse_confidence:
            tags.append(f"confidence:{result.abuse_confidence}")
        if result.country_code:
            tags.append(f"country:{result.country_code}")
        if result.usage_type:
            tags.append(f"usage:{result.usage_type}")
        return tags
    except Exception as e:
        logger.debug("Failed to get threat tags", ip=ip, error=str(e))
        return []


@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
def catch_all(path: str) -> Response:
    """
    捕获所有 HTTP 请求。
    构造命令字符串，调用 handler.process_command，并返回伪造的响应。
    """
    client_ip = _get_client_ip()
    session_id = handler.generate_session_id()
    protocol = "http"
    method = request.method
    full_path = "/" + path if path else "/"
    query_string = request.query_string.decode("utf-8") if request.query_string else ""

    # 构造命令字符串，格式示例: "GET /api/user?id=123"
    if query_string:
        command = f"{method} {full_path}?{query_string}"
    else:
        command = f"{method} {full_path}"

    # 获取请求头和部分 body 作为上下文（可选）
    headers_dict = dict(request.headers)
    # 限制 body 长度避免过大
    try:
        body_preview = request.get_data(as_text=True)[:200]
    except:
        body_preview = ""

    # 添加额外信息到日志（但不作为命令主要部分）
    extra_context = {
        "headers": {k: v for k, v in headers_dict.items() if k.lower() not in ("authorization", "cookie")},
        "body_preview": body_preview,
    }

    # 获取威胁标签
    threat_tags = _get_threat_tags(client_ip)

    logger.info(
        "HTTP request",
        session_id=session_id,
        client_ip=client_ip,
        method=method,
        path=full_path,
        threat_tags=threat_tags,
    )

    # 调用 handler 处理命令
    # handler.process_command 返回文本响应，我们将它作为 HTTP 响应体
    # 注意：handler.process_command 可能会返回带换行符的文本，我们将直接使用
    response_text = handler.process_command(
        session_id=session_id,
        command=command,
        client_ip=client_ip,
        protocol=protocol,
        threat_tags=threat_tags,
    )

    # 构造 HTTP 响应
    # 尝试智能识别内容类型：如果响应以 < 开头，可能是 HTML，否则作为纯文本
    content_type = "text/html; charset=utf-8" if response_text.strip().startswith("<") else "text/plain; charset=utf-8"
    # 为了增加逼真度，可随机返回不同的状态码，但这里统一返回 200 OK
    return Response(response_text, status=200, content_type=content_type)


@app.errorhandler(NotFound)
def handle_404(e):
    """
    对于未匹配的路由，由 catch_all 处理，所以不会走到这里，但保留以防万一。
    """
    return catch_all("")


class HTTPServerThread(threading.Thread):
    """
    在后台线程中运行 Flask 服务器的线程类。
    """

    def __init__(self, host: str, port: int, debug: bool = False):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.debug = debug
        self.server = make_server(host, port, app, threaded=True)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        logger.info("Starting HTTP server", host=self.host, port=self.port)
        self.server.serve_forever()

    def shutdown(self):
        logger.info("Shutting down HTTP server")
        self.server.shutdown()


def start_http_server(
    host: str = "0.0.0.0",
    port: int = 8080,
    threat_checker: Optional[ThreatIntelChecker] = None,
) -> HTTPServerThread:
    """
    启动 HTTP 蜜罐服务器（非阻塞，返回线程对象）。

    :param host: 监听地址
    :param port: 监听端口
    :param threat_checker: 威胁情报检查器实例（可选）
    :return: 后台线程对象，可通过调用 shutdown() 停止
    """
    if threat_checker:
        init_threat_checker(threat_checker)

    thread = HTTPServerThread(host, port)
    thread.start()
    return thread


# 如果直接运行此模块，启动 HTTP 服务器（用于测试）
if __name__ == "__main__":
    import sys
    sys.path.insert(0, "..")
    from config import settings
    from services.honeypot.utils.ip_utils import ThreatIntelChecker

    # 创建简单的威胁检查器（无 API 密钥，仅测试）
    checker = ThreatIntelChecker(enabled=False)
    thread = start_http_server(host=settings.http_host, port=settings.http_port, threat_checker=checker)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        thread.shutdown()