# services/honeypot/utils/ip_utils.py
"""
IP 地址处理工具模块（使用 VirusTotal 威胁情报 API）。

功能：
- 从请求上下文中提取真实客户端 IP（考虑代理头）
- IP 地址格式验证
- 威胁情报查询（支持 VirusTotal API）与缓存
"""

import ipaddress
import asyncio
import time
from typing import Optional, Dict, Any, Union, List, Tuple
from dataclasses import dataclass, field

import aiohttp
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ThreatIntelResult:
    """威胁情报查询结果"""
    ip: str
    is_malicious: bool
    confidence: float  # 0-100 置信度
    country_code: Optional[str] = None
    isp: Optional[str] = None
    total_reports: int = 0
    source: str = "unknown"  # 数据来源, e.g., "virustotal", "cache"
    cached: bool = False
    error: Optional[str] = None
    # 额外字段可保留
    reputation: Optional[int] = None  # VirusTotal 特有，-100 到 100


class ThreatIntelChecker:
    """
    威胁情报查询器，支持缓存和异步 HTTP 请求。
    使用 VirusTotal API v3。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_ttl: int = 3600,
        enabled: bool = True,
        session: Optional[aiohttp.ClientSession] = None,
        max_retries: int = 2,
        timeout: int = 5,
    ):
        """
        初始化威胁情报检查器。

        :param api_key: VirusTotal API 密钥
        :param cache_ttl: 缓存有效期 (秒)
        :param enabled: 是否启用真实查询 (禁用时返回空结果)
        :param session: 可选的 aiohttp session，若不提供则内部创建
        :param max_retries: 查询失败重试次数
        :param timeout: 请求超时时间
        """
        self.api_key = api_key
        self.cache_ttl = cache_ttl
        self.enabled = enabled
        self.max_retries = max_retries
        self.timeout = timeout
        self._session = session
        self._own_session = session is None
        self._cache: Dict[str, Tuple[float, ThreatIntelResult]] = {}  # ip -> (expire_time, result)

        # VirusTotal API 端点 (v3)
        self.vt_base_url = "https://www.virustotal.com/api/v3/ip_addresses"

    async def __aenter__(self):
        if self._own_session:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._own_session and self._session:
            await self._session.close()

    def _is_valid_ip(self, ip: str) -> bool:
        """检查 IP 地址格式是否合法 (IPv4 或 IPv6)"""
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False

    async def check_ip(self, ip: str) -> ThreatIntelResult:
        """
        查询 IP 威胁情报 (带缓存)。
        """
        if not self._is_valid_ip(ip):
            return ThreatIntelResult(
                ip=ip,
                is_malicious=False,
                confidence=0,
                error="Invalid IP format"
            )

        # 检查缓存
        now = time.time()
        if ip in self._cache:
            expire_time, result = self._cache[ip]
            if expire_time > now:
                result.cached = True
                logger.debug("Cache hit for IP", ip=ip, result=result)
                return result
            else:
                # 过期删除
                del self._cache[ip]

        # 缓存未命中，查询 VirusTotal
        result = await self._query_virustotal(ip)

        # 存入缓存（仅当无错误时）
        if result.error is None:
            self._cache[ip] = (now + self.cache_ttl, result)

        return result

    async def _query_virustotal(self, ip: str) -> ThreatIntelResult:
        """
        调用 VirusTotal API v3 查询 IP。
        """
        if not self.enabled or not self.api_key:
            logger.info("Threat intel disabled or no API key", ip=ip, enabled=self.enabled)
            return ThreatIntelResult(
                ip=ip,
                is_malicious=False,
                confidence=0,
                source="disabled",
            )

        if not self._session:
            self._session = aiohttp.ClientSession()
            self._own_session = True

        url = f"{self.vt_base_url}/{ip}"
        headers = {
            "x-apikey": self.api_key,
            "Accept": "application/json",
        }

        for attempt in range(self.max_retries + 1):
            try:
                async with self._session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return self._parse_virustotal_response(ip, data)
                    elif resp.status == 429:
                        logger.warning("Rate limited by VirusTotal", ip=ip, attempt=attempt)
                        if attempt < self.max_retries:
                            wait = 2 ** attempt  # 指数退避
                            await asyncio.sleep(wait)
                            continue
                        else:
                            return ThreatIntelResult(
                                ip=ip,
                                is_malicious=False,
                                confidence=0,
                                source="virustotal",
                                error=f"Rate limited after {self.max_retries} retries"
                            )
                    else:
                        error_text = await resp.text()
                        logger.error(
                            "VirusTotal API error",
                            ip=ip,
                            status=resp.status,
                            error=error_text[:200]
                        )
                        return ThreatIntelResult(
                            ip=ip,
                            is_malicious=False,
                            confidence=0,
                            source="virustotal",
                            error=f"HTTP {resp.status}: {error_text[:100]}"
                        )
            except asyncio.TimeoutError:
                logger.warning("Timeout querying VirusTotal", ip=ip, attempt=attempt)
                if attempt < self.max_retries:
                    await asyncio.sleep(1)
                    continue
                return ThreatIntelResult(
                    ip=ip,
                    is_malicious=False,
                    confidence=0,
                    source="virustotal",
                    error="Timeout after retries"
                )
            except aiohttp.ClientError as e:
                logger.warning("Client error querying VirusTotal", ip=ip, error=str(e), attempt=attempt)
                if attempt < self.max_retries:
                    await asyncio.sleep(1)
                    continue
                return ThreatIntelResult(
                    ip=ip,
                    is_malicious=False,
                    confidence=0,
                    source="virustotal",
                    error=f"Client error: {str(e)}"
                )
        # 不应到达这里
        return ThreatIntelResult(
            ip=ip,
            is_malicious=False,
            confidence=0,
            source="virustotal",
            error="Unknown error"
        )

    def _parse_virustotal_response(self, ip: str, data: Dict[str, Any]) -> ThreatIntelResult:
        """
        解析 VirusTotal API v3 响应。
        """
        try:
            attributes = data.get("data", {}).get("attributes", {})
            stats = attributes.get("last_analysis_stats", {})
            malicious = stats.get("malicious", 0)
            suspicious = stats.get("suspicious", 0)
            harmless = stats.get("harmless", 0)
            undetected = stats.get("undetected", 0)

            # 判断是否为恶意（可自定义阈值）
            total_engines = malicious + suspicious + harmless + undetected
            if total_engines == 0:
                is_malicious = False
                confidence = 0
            else:
                # 简单置信度：恶意引擎占比 * 100
                is_malicious = malicious > 0 or suspicious > 0
                confidence = int((malicious + suspicious) / total_engines * 100)

            # 获取其他信息
            country = attributes.get("country")
            as_owner = attributes.get("as_owner")
            reputation = attributes.get("reputation", 0)  # -100 到 100

            # 可选：如果信誉分很低，也可标记为恶意
            if not is_malicious and reputation < -50:
                is_malicious = True
                confidence = max(confidence, 50)

            return ThreatIntelResult(
                ip=ip,
                is_malicious=is_malicious,
                confidence=confidence,
                country_code=country,
                isp=as_owner,
                total_reports=malicious + suspicious,
                source="virustotal",
                reputation=reputation,
            )
        except Exception as e:
            logger.error("Failed to parse VirusTotal response", ip=ip, error=str(e), data=data)
            return ThreatIntelResult(
                ip=ip,
                is_malicious=False,
                confidence=0,
                source="virustotal",
                error=f"Parse error: {str(e)}"
            )

    async def start_cleanup_task(self):
        """启动后台缓存清理任务（可选）"""
        if not hasattr(self, "_cleanup_task") or self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        """定期清理过期缓存条目"""
        while True:
            await asyncio.sleep(300)  # 每5分钟检查一次
            now = time.time()
            expired = [ip for ip, (exp, _) in self._cache.items() if exp <= now]
            for ip in expired:
                del self._cache[ip]
            if expired:
                logger.debug("Cleaned expired threat intel cache", count=len(expired))

    async def stop_cleanup_task(self):
        """停止清理任务"""
        if hasattr(self, "_cleanup_task") and self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None


# ---------- IP 提取辅助函数 ----------

def extract_client_ip(
    headers: Dict[str, str],
    remote_addr: Optional[str] = None,
    trusted_proxies: Optional[List[Union[str, ipaddress.IPv4Network]]] = None
) -> Optional[str]:
    """
    从请求头中提取真实的客户端 IP。

    规则：
    1. 检查 X-Forwarded-For 头部，取第一个非信任代理的 IP（如果提供了信任代理列表）
    2. 否则取 X-Real-IP
    3. 最后回退到 remote_addr

    :param headers: 请求头字典 (键不区分大小写)
    :param remote_addr: 直接连接的对端地址
    :param trusted_proxies: 信任的代理 IP 列表（可以是字符串或 ip_network）
    :return: 客户端 IP 字符串，或 None
    """
    # 将头转换为小写以不区分大小写
    headers_lower = {k.lower(): v for k, v in headers.items()}

    # 1. X-Forwarded-For
    xff = headers_lower.get("x-forwarded-for")
    if xff:
        # 格式: client, proxy1, proxy2
        ips = [ip.strip() for ip in xff.split(",")]
        if trusted_proxies:
            # 从右向左跳过信任代理
            for ip in reversed(ips):
                if not _is_trusted_proxy(ip, trusted_proxies):
                    return ip
        else:
            # 没有信任代理列表，直接返回最左边的（原始客户端）
            return ips[0]

    # 2. X-Real-IP
    x_real_ip = headers_lower.get("x-real-ip")
    if x_real_ip:
        return x_real_ip

    # 3. remote_addr
    return remote_addr


def _is_trusted_proxy(ip: str, trusted_proxies: List[Union[str, ipaddress.IPv4Network]]) -> bool:
    """检查 IP 是否在信任代理列表中（支持 CIDR）"""
    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        return False

    for proxy in trusted_proxies:
        if isinstance(proxy, str):
            try:
                if "/" in proxy:
                    net = ipaddress.ip_network(proxy, strict=False)
                    if ip_obj in net:
                        return True
                else:
                    if ip_obj == ipaddress.ip_address(proxy):
                        return True
            except ValueError:
                continue
        elif isinstance(proxy, ipaddress.IPv4Network) or isinstance(proxy, ipaddress.IPv6Network):
            if ip_obj in proxy:
                return True
    return False


def is_private_ip(ip: str) -> bool:
    """判断是否为私有/保留 IP 地址"""
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local
    except ValueError:
        return False