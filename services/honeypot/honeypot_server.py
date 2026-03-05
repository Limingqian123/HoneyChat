# services/honeypot/honeypot_server.py
"""
HoneyChat 蜜罐服务主入口。

启动 SSH 和 HTTP 蜜罐服务器，初始化威胁情报模块，处理信号优雅关闭。
"""

import signal
import sys
import threading
import time
from typing import NoReturn, Optional
import asyncio
import structlog

from config import settings, setup_logging
from utils.ip_utils import ThreatIntelChecker
from protocol import ssh_server, http_server
import handler

logger = structlog.get_logger(__name__)


class HoneyPotServer:
    """蜜罐服务器管理器，负责启动/停止所有服务"""

    def __init__(self):
        self.shutdown_event = threading.Event()
        self.ssh_thread: Optional[threading.Thread] = None
        self.http_thread: Optional[http_server.HTTPServerThread] = None
        self.threat_checker: Optional[ThreatIntelChecker] = None

    def init_threat_checker(self) -> None:
        """初始化威胁情报检查器"""
        if not settings.enable_threat_intel:
            logger.info("Threat intelligence is disabled")
            return

        try:
            self.threat_checker = ThreatIntelChecker(
                api_key=settings.threat_intel_api_key,
                cache_ttl=settings.threat_intel_cache_ttl,
                enabled=settings.enable_threat_intel,
                max_retries=2,
                timeout=5,
            )
            # 启动后台缓存清理任务
            # asyncio.run_coroutine_threadsafe(
            #     self.threat_checker.start_cleanup_task(),
            #     asyncio.new_event_loop()
            # )  # 简化：在单独的线程中运行协程？更简单的方式是忽略，因为缓存不会无限增长
            # 或者使用 threading 定时清理，但为了简化，这里不启动清理任务，缓存过期条目自然会在下次查询时删除
            logger.info("Threat intelligence checker initialized")
        except Exception as e:
            logger.error("Failed to initialize threat checker", error=str(e))
            self.threat_checker = None

    def start_ssh_server(self) -> None:
        """在后台线程中启动 SSH 服务器"""
        def ssh_runner():
            try:
                ssh_server.start_ssh_server(
                    host=settings.ssh_host,
                    port=settings.ssh_port,
                )
            except Exception as e:
                logger.exception("SSH server crashed", error=str(e))
                # 如果 SSH 崩溃，考虑整个服务退出？但这里保持其他服务运行
        self.ssh_thread = threading.Thread(target=ssh_runner, daemon=True)
        self.ssh_thread.start()
        logger.info("SSH server thread started", host=settings.ssh_host, port=settings.ssh_port)

    def start_http_server(self) -> None:
        """启动 HTTP 服务器（返回线程对象）"""
        try:
            self.http_thread = http_server.start_http_server(
                host=settings.http_host,
                port=settings.http_port,
                threat_checker=self.threat_checker,
            )
            logger.info("HTTP server started", host=settings.http_host, port=settings.http_port)
        except Exception as e:
            logger.exception("Failed to start HTTP server", error=str(e))

    def run(self) -> NoReturn:
        """启动所有服务并等待停止信号"""
        # 配置日志
        setup_logging()
        logger.info("Starting HoneyChat Honeypot", version="1.0.0", service=settings.service_name)

        # 初始化威胁情报
        self.init_threat_checker()

        # 启动 SSH 和 HTTP 服务
        self.start_ssh_server()
        self.start_http_server()

        # 设置信号处理
        def signal_handler(signum, frame):
            logger.info("Received signal, initiating shutdown", signal=signum)
            self.shutdown_event.set()

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        # 主线程等待关闭事件
        try:
            while not self.shutdown_event.is_set():
                # 每秒检查一次，同时可处理其他周期性任务
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received, shutting down")
        finally:
            self.shutdown()

        logger.info("Honeypot server stopped")

    def shutdown(self) -> None:
        """优雅关闭所有服务"""
        logger.info("Shutting down honeypot services...")

        # 停止 HTTP 服务器
        if self.http_thread:
            try:
                self.http_thread.shutdown()
                logger.info("HTTP server stopped")
            except Exception as e:
                logger.error("Error stopping HTTP server", error=str(e))

        # SSH 服务器是阻塞的，没有直接的停止方法，由于是 daemon 线程，主线程退出时会自动终止
        # 但为了干净关闭，可以尝试关闭监听 socket，但简化处理，直接退出

        # 清理 handler 资源
        try:
            handler.cleanup()
            logger.info("Handler resources cleaned up")
        except Exception as e:
            logger.error("Error cleaning up handler", error=str(e))

        # 停止威胁情报检查器（如果实现了）
        if self.threat_checker:
            try:
                # 如果有后台任务，需要停止
                # 由于未启动清理任务，直接忽略
                logger.info("Threat checker stopped")
            except Exception as e:
                logger.error("Error stopping threat checker", error=str(e))

        logger.info("Shutdown complete")


def main():
    server = HoneyPotServer()
    server.run()


if __name__ == "__main__":
    main()