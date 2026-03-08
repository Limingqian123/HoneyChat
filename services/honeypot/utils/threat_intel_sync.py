# services/honeypot/utils/threat_intel_sync.py
"""
威胁情报同步包装器

提供同步接口调用异步的威胁情报API
"""

import asyncio
from typing import Optional, List
import structlog

from .ip_utils import ThreatIntelChecker, ThreatIntelResult

logger = structlog.get_logger(__name__)


class SyncThreatIntelChecker:
    """威胁情报检查器的同步包装"""

    def __init__(self, api_key: Optional[str] = None, cache_ttl: int = 3600, enabled: bool = True):
        self.api_key = api_key
        self.cache_ttl = cache_ttl
        self.enabled = enabled
        self._checker: Optional[ThreatIntelChecker] = None

    def check_ip(self, ip: str) -> ThreatIntelResult:
        """
        同步方式查询IP威胁情报

        :param ip: IP地址
        :return: 威胁情报结果
        """
        if not self.enabled or not self.api_key:
            return ThreatIntelResult(
                ip=ip,
                is_malicious=False,
                confidence=0,
                source="disabled",
            )

        try:
            # 在新的事件循环中运行异步代码
            return asyncio.run(self._async_check(ip))
        except Exception as e:
            logger.error("Failed to check IP threat intel", ip=ip, error=str(e))
            return ThreatIntelResult(
                ip=ip,
                is_malicious=False,
                confidence=0,
                error=str(e),
            )

    async def _async_check(self, ip: str) -> ThreatIntelResult:
        """异步查询IP"""
        async with ThreatIntelChecker(
            api_key=self.api_key,
            cache_ttl=self.cache_ttl,
            enabled=self.enabled,
        ) as checker:
            return await checker.check_ip(ip)

    def get_threat_tags(self, result: ThreatIntelResult) -> List[str]:
        """
        根据威胁情报结果生成标签

        :param result: 威胁情报结果
        :return: 标签列表
        """
        tags = []

        if result.error:
            tags.append("threat_intel_error")
            return tags

        if result.is_malicious:
            tags.append("malicious")
            if result.confidence >= 80:
                tags.append("high_confidence")
            elif result.confidence >= 50:
                tags.append("medium_confidence")
            else:
                tags.append("low_confidence")

        if result.country_code:
            tags.append(f"country_{result.country_code.lower()}")

        if result.total_reports > 0:
            tags.append(f"reports_{result.total_reports}")

        return tags
