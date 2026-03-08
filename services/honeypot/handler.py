# services/honeypot/handler.py
"""
蜜罐核心业务逻辑处理模块。

提供命令处理、RAG 引擎调用、事件推送等功能。
"""

import uuid
import json
import time
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor
import httpx
import structlog
from pydantic import BaseModel, Field

# from .config import settings
from config import settings
from session_manager import session_manager
from virtual_fs import VirtualFileSystem, FSCommandHandler
from scenario_engine import ScenarioEngine
from attack_analyzer import AttackAnalyzer
from utils.threat_intel_sync import SyncThreatIntelChecker

logger = structlog.get_logger(__name__)

# 线程池用于异步推送事件，避免阻塞主线程
_event_executor = ThreadPoolExecutor(max_workers=10)

# HTTP 客户端（全局复用，但需注意线程安全）
_http_client = httpx.Client(
    timeout=httpx.Timeout(settings.rag_request_timeout),
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
)

# 初始化新组件
# 注意：VFS不再是全局单例，每个session有独立实例
_scenario_engine = ScenarioEngine()
_attack_analyzer = AttackAnalyzer()

# 初始化威胁情报检查器
_threat_intel = SyncThreatIntelChecker(
    api_key=settings.threat_intel_api_key,
    cache_ttl=settings.threat_intel_cache_ttl,
    enabled=settings.enable_threat_intel,
)


class CommandRequest(BaseModel):
    """发送到 RAG 引擎的请求结构"""
    command: str
    session_id: str
    threat_tags: Optional[List[str]] = Field(default_factory=list)
    protocol: str  # "ssh" 或 "http"
    client_ip: Optional[str] = None


class CommandResponse(BaseModel):
    """RAG 引擎返回的响应结构"""
    response: str
    session_id: str
    confidence: Optional[float] = None
    error: Optional[str] = None


def generate_session_id() -> str:
    """生成唯一的会话 ID"""
    return str(uuid.uuid4())


def get_threat_tags(client_ip: Optional[str]) -> List[str]:
    """
    查询IP威胁情报并返回标签

    :param client_ip: 客户端IP地址
    :return: 威胁标签列表
    """
    if not client_ip or not settings.enable_threat_intel:
        return []

    try:
        result = _threat_intel.check_ip(client_ip)
        tags = _threat_intel.get_threat_tags(result)

        if result.is_malicious:
            logger.warning(
                "Malicious IP detected",
                ip=client_ip,
                confidence=result.confidence,
                tags=tags,
            )

        return tags
    except Exception as e:
        logger.error("Failed to get threat tags", ip=client_ip, error=str(e))
        return []


def process_command(
    session_id: str,
    command: str,
    client_ip: Optional[str] = None,
    protocol: str = "ssh",
    threat_tags: Optional[List[str]] = None,
) -> str:
    """
    核心命令处理函数（增强版）。

    1. 查询IP威胁情报（首次，会话级缓存）
    2. 获取会话状态和独立VFS
    3. 尝试用虚拟文件系统处理命令
    4. 如果无法处理，调用 RAG 引擎
    5. 检查并部署攻击场景诱饵
    6. 更新会话状态并分析攻击
    7. 异步推送事件到仪表盘

    :param session_id: 会话唯一标识
    :param command: 攻击者输入的命令
    :param client_ip: 客户端 IP
    :param protocol: 协议类型 ("ssh" 或 "http")
    :param threat_tags: 威胁情报标签列表（可选，如未提供则自动查询）
    :return: 返回给攻击者的响应字符串
    """
    # 1. 获取或创建会话状态
    session = session_manager.get_or_create(session_id)
    session.add_command(command)

    # 2. 查询威胁情报（会话级缓存，只查询一次）
    if threat_tags is None:
        if not session.threat_checked and client_ip:
            session.threat_tags = get_threat_tags(client_ip)
            session.threat_checked = True
        threat_tags = session.threat_tags
    else:
        session.threat_tags = threat_tags

    # 3. 获取或创建会话专属的VFS
    if 'vfs' not in session.custom_data:
        session.custom_data['vfs'] = VirtualFileSystem()
    vfs = session.custom_data['vfs']
    fs_handler = FSCommandHandler(vfs)

    # 4. 尝试用虚拟文件系统处理

    # 4. 尝试用虚拟文件系统处理
    fs_response, new_cwd = fs_handler.handle(command, session.cwd)

    if fs_response is not None:
        # 文件系统命令已处理
        if new_cwd:
            session.cwd = new_cwd
        resp_text = fs_response
        error = None
    else:
        # 5. 调用 RAG 引擎
        req = CommandRequest(
            command=command,
            session_id=session_id,
            threat_tags=threat_tags,
            protocol=protocol,
            client_ip=client_ip,
        )
        resp_text, error = _call_rag_engine(req)

    # 6. 检查并部署攻击场景
    _scenario_engine.check_and_deploy(session_id, command, vfs)

    # 7. 分析攻击阶段
    attack_phase = _attack_analyzer.analyze_command(command)
    risk_score = _attack_analyzer.get_risk_score(session.history)

    # 6. 异步推送事件到仪表盘
    _push_event_async(
        session_id=session_id,
        command=command,
        response=resp_text,
        client_ip=client_ip,
        protocol=protocol,
        threat_tags=threat_tags,
        error=error,
        attack_phase=attack_phase,
        risk_score=risk_score,
    )

    return resp_text


def _call_rag_engine(req: CommandRequest) -> (str, Optional[str]):
    """
    实际调用 RAG 引擎 HTTP API。
    返回 (响应文本, 错误信息) 元组。
    """
    url = f"{settings.rag_engine_url}/generate"
    payload = req.model_dump()

    # 重试逻辑
    for attempt in range(settings.rag_max_retries + 1):
        try:
            response = _http_client.post(url, json=payload)
            if response.status_code == 200:
                data = response.json()
                # 期望格式: {"response": "...", "session_id": "..."}
                resp_text = data.get("response", "")
                if not resp_text:
                    logger.error("RAG engine returned empty response", data=data)
                    return _fallback_response(), "Empty response from RAG engine"
                return resp_text, None
            else:
                logger.warning(
                    "RAG engine returned non-200",
                    status=response.status_code,
                    body=response.text[:200],
                    attempt=attempt,
                )
                if attempt < settings.rag_max_retries:
                    time.sleep(0.5 * (2 ** attempt))  # 指数退避
                    continue
                else:
                    return _fallback_response(), f"HTTP {response.status_code}"
        except httpx.TimeoutException:
            logger.warning("RAG engine timeout", attempt=attempt)
            if attempt < settings.rag_max_retries:
                time.sleep(0.5 * (2 ** attempt))
                continue
            else:
                return _fallback_response(), "Timeout"
        except httpx.RequestError as e:
            logger.warning("RAG engine request error", error=str(e), attempt=attempt)
            if attempt < settings.rag_max_retries:
                time.sleep(0.5 * (2 ** attempt))
                continue
            else:
                return _fallback_response(), f"Request error: {str(e)}"
        except Exception as e:
            logger.exception("Unexpected error calling RAG engine", error=str(e))
            return _fallback_response(), f"Unexpected error: {str(e)}"

    # 不应该到达
    return _fallback_response(), "Unknown error"


def _fallback_response() -> str:
    """
    当 RAG 引擎不可用时的降级响应。
    """
    return "Command not found or an error occurred.\n"


def _push_event_async(
    session_id: str,
    command: str,
    response: str,
    client_ip: Optional[str],
    protocol: str,
    threat_tags: Optional[List[str]],
    error: Optional[str],
    attack_phase: str = "unknown",
    risk_score: int = 0,
) -> None:
    """
    异步推送事件到仪表盘（使用线程池，不阻塞）。
    """
    _event_executor.submit(
        _send_event_to_dashboard,
        session_id=session_id,
        command=command,
        response=response,
        client_ip=client_ip,
        protocol=protocol,
        threat_tags=threat_tags,
        error=error,
        attack_phase=attack_phase,
        risk_score=risk_score,
    )


def _send_event_to_dashboard(
    session_id: str,
    command: str,
    response: str,
    client_ip: Optional[str],
    protocol: str,
    threat_tags: Optional[List[str]],
    error: Optional[str],
    attack_phase: str = "unknown",
    risk_score: int = 0,
) -> None:
    """
    实际向仪表盘 API 发送事件。
    """
    url = f"{settings.dashboard_url}/api/events"
    payload = {
        "session_id": session_id,
        "command": command,
        "response": response,
        "client_ip": client_ip,
        "protocol": protocol,
        "threat_tags": threat_tags or [],
        "error": error,
        "timestamp": time.time(),
        "attack_phase": attack_phase,
        "risk_score": risk_score,
    }

    try:
        # 使用独立的客户端避免与主客户端争用
        with httpx.Client(timeout=2.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code not in (200, 201):
                logger.warning(
                    "Dashboard event push failed",
                    status=resp.status_code,
                    body=resp.text[:100],
                )
    except Exception as e:
        logger.debug("Failed to push event to dashboard", error=str(e))
        # 忽略错误，不影响主流程


def cleanup() -> None:
    """
    应用关闭时释放资源。
    """
    _http_client.close()
    _event_executor.shutdown(wait=True)
    logger.info("Handler resources cleaned up")


# 可选：暴露给外部使用的工具函数
__all__ = ["process_command", "generate_session_id", "cleanup"]