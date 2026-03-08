# services/honeypot/session_manager.py
"""
会话状态管理器

为每个攻击者会话维护独立的状态，包括：
- 当前工作目录
- 环境变量
- 命令历史
- 自定义状态数据
"""

import time
from typing import Dict, List, Any, Optional
from threading import Lock
import structlog

logger = structlog.get_logger(__name__)


class SessionState:
    """单个会话的状态"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.cwd = "/home/user"  # 当前工作目录
        self.env = {
            "USER": "user",
            "HOME": "/home/user",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "SHELL": "/bin/bash",
        }
        self.history: List[str] = []  # 命令历史
        self.created_at = time.time()
        self.last_activity = time.time()
        self.custom_data: Dict[str, Any] = {}  # 自定义数据
        self.threat_tags: List[str] = []  # 威胁情报标签（缓存）
        self.threat_checked: bool = False  # 是否已查询威胁情报

    def add_command(self, command: str):
        """添加命令到历史"""
        self.history.append(command)
        self.last_activity = time.time()

    def get_context(self) -> Dict[str, Any]:
        """获取会话上下文（用于传递给RAG）"""
        return {
            "cwd": self.cwd,
            "user": self.env.get("USER", "user"),
            "recent_commands": self.history[-5:] if len(self.history) > 0 else [],
        }

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "session_id": self.session_id,
            "cwd": self.cwd,
            "env": self.env,
            "history": self.history,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
        }


class SessionManager:
    """会话管理器（单例）"""

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.sessions: Dict[str, SessionState] = {}
        self.lock = Lock()
        self.max_sessions = 1000  # 最大会话数
        self.session_timeout = 3600  # 会话超时时间（秒）
        self._initialized = True
        logger.info("SessionManager initialized")

    def get_or_create(self, session_id: str) -> SessionState:
        """获取或创建会话状态"""
        with self.lock:
            if session_id not in self.sessions:
                # 清理过期会话
                self._cleanup_expired()

                # 创建新会话
                self.sessions[session_id] = SessionState(session_id)
                logger.info("New session created", session_id=session_id)

            return self.sessions[session_id]

    def get(self, session_id: str) -> Optional[SessionState]:
        """获取会话状态（不创建）"""
        return self.sessions.get(session_id)

    def remove(self, session_id: str):
        """删除会话"""
        with self.lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                logger.info("Session removed", session_id=session_id)

    def _cleanup_expired(self):
        """清理过期会话"""
        now = time.time()
        expired = [
            sid for sid, state in self.sessions.items()
            if now - state.last_activity > self.session_timeout
        ]

        for sid in expired:
            del self.sessions[sid]

        if expired:
            logger.info("Expired sessions cleaned", count=len(expired))

        # 如果会话数超过限制，删除最旧的
        if len(self.sessions) > self.max_sessions:
            sorted_sessions = sorted(
                self.sessions.items(),
                key=lambda x: x[1].last_activity
            )
            to_remove = len(self.sessions) - self.max_sessions
            for sid, _ in sorted_sessions[:to_remove]:
                del self.sessions[sid]
            logger.warning("Max sessions exceeded, removed oldest", count=to_remove)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_sessions": len(self.sessions),
            "active_sessions": sum(
                1 for s in self.sessions.values()
                if time.time() - s.last_activity < 300
            ),
        }


# 全局单例
session_manager = SessionManager()
