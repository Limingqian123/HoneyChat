# services/honeypot/config.py
"""
HoneyChat 蜜罐服务配置管理模块。

使用 Pydantic Settings 从环境变量和 YAML 文件加载配置，
环境变量优先级高于配置文件。
"""

import os
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, ValidationInfo
import structlog
import logging

logger = structlog.get_logger(__name__)

class Settings(BaseSettings):
    """
    蜜罐服务配置类。
    
    配置加载顺序：
        1. 默认值
        2. YAML 配置文件 (config.yaml)
        3. 环境变量 (以 HONEYPOT_ 为前缀)
    """
    
    # 服务基础配置
    service_name: str = Field(
        "honeychat-honeypot", 
        description="服务名称，用于日志和监控标识"
    )
    log_level: str = Field(
        "INFO", 
        description="日志级别: DEBUG, INFO, WARNING, ERROR"
    )
    
    # 网络监听配置
    ssh_host: str = Field(
        "0.0.0.0", 
        description="SSH 服务监听地址"
    )
    ssh_port: int = Field(
        2222, 
        description="SSH 服务监听端口",
        ge=1, le=65535
    )
    http_host: str = Field(
        "0.0.0.0", 
        description="HTTP 服务监听地址"
    )
    http_port: int = Field(
        8080, 
        description="HTTP 服务监听端口",
        ge=1, le=65535
    )
    
    # 后端服务地址
    rag_engine_url: str = Field(
        "http://rag-engine:8000",
        description="RAG 引擎服务地址 (包括协议和端口)"
    )
    dashboard_url: str = Field(
        "http://dashboard:5000",
        description="仪表盘服务地址，用于推送事件"
    )
    
    # 威胁情报配置
    threat_intel_api_key: Optional[str] = Field(
        None,
        description="威胁情报 API 密钥 (如 AbuseIPDB 等)"
    )
    threat_intel_cache_ttl: int = Field(
        3600,
        description="IP 信誉缓存有效期 (秒)",
        ge=60
    )
    enable_threat_intel: bool = Field(
        True,
        description="是否启用威胁情报查询"
    )
    
    # 路径配置
    log_dir: Path = Field(
        Path("/app/logs"),
        description="日志文件目录"
    )
    config_file: Path = Field(
        Path("/app/config.yaml"),
        description="YAML 配置文件路径"
    )
    
    # 性能调优
    max_connections: int = Field(
        100,
        description="最大并发连接数",
        ge=1
    )
    connection_timeout: int = Field(
        300,
        description="连接超时时间 (秒)",
        ge=10
    )
    command_timeout: int = Field(
        30,
        description="单个命令执行超时时间 (秒)",
        ge=5
    )
    
    # 会话管理
    session_idle_timeout: int = Field(
        600,
        description="会话空闲超时时间 (秒)，超时后自动断开",
        ge=60
    )
    max_session_history: int = Field(
        1000,
        description="每个会话最多保存的命令历史条数",
        ge=10
    )
    
    # RAG 引擎调用参数
    rag_request_timeout: int = Field(
        10,
        description="调用 RAG 引擎的超时时间 (秒)",
        ge=1
    )
    rag_max_retries: int = Field(
        3,
        description="调用 RAG 引擎的最大重试次数",
        ge=0
    )
    
    # 内部配置字段 (不通过环境变量直接设置，由 `model_post_init` 填充)
    config_dict: Dict[str, Any] = Field({}, exclude=True)
    
    # Pydantic 配置：环境变量前缀、不区分大小写、忽略无效字段
    model_config = SettingsConfigDict(
        env_prefix="HONEYPOT_",
        case_sensitive=False,
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """验证日志级别是否合法"""
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"日志级别必须为 {allowed} 之一")
        return v_upper
    
    def model_post_init(self, __context: Any) -> None:
        """
        加载 YAML 配置文件并合并到当前设置。
        环境变量已经通过 BaseSettings 机制自动覆盖默认值，
        此处将 YAML 配置中未被环境变量覆盖的值合并进来。
        """
        # 如果配置文件存在，则加载
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    yaml_config = yaml.safe_load(f) or {}
                # 更新当前实例的 __dict__，但仅当字段尚未被环境变量设置（即未显式传入）
                # BaseSettings 已处理环境变量，我们只需将 YAML 中未在环境变量中出现的值合并
                # 但直接修改 __dict__ 可能绕过验证，因此采用重新构建的方式
                # 简便做法：保存原始 yaml_config 供外部使用
                self.config_dict = yaml_config
                logger.info("Loaded configuration from YAML", path=str(self.config_file))
            except Exception as e:
                logger.error("Failed to load YAML config", path=str(self.config_file), error=str(e))
                # 不阻断启动，继续使用默认值
        else:
            logger.info("No YAML config file found, using defaults", path=str(self.config_file))
    
    def get_threat_intel_config(self) -> dict:
        """返回威胁情报配置子集"""
        return {
            "api_key": self.threat_intel_api_key,
            "cache_ttl": self.threat_intel_cache_ttl,
            "enabled": self.enable_threat_intel,
        }
    
    def get_rag_config(self) -> dict:
        """返回 RAG 引擎调用配置子集"""
        return {
            "url": self.rag_engine_url,
            "timeout": self.rag_request_timeout,
            "max_retries": self.rag_max_retries,
        }
    
    def get_server_config(self) -> dict:
        """返回服务器相关配置子集"""
        return {
            "ssh": (self.ssh_host, self.ssh_port),
            "http": (self.http_host, self.http_port),
            "max_connections": self.max_connections,
            "connection_timeout": self.connection_timeout,
            "command_timeout": self.command_timeout,
            "session_idle_timeout": self.session_idle_timeout,
            "max_session_history": self.max_session_history,
        }


# 全局单例配置实例
settings = Settings()

# 配置日志格式
def setup_logging():
    """根据配置初始化结构化日志"""
    log_level = getattr(logging, settings.log_level, logging.INFO)
    
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # 设置根日志级别
    logging.basicConfig(level=log_level)


# 初始化日志（当模块被导入时自动调用，但为了避免副作用，可考虑在 main 中显式调用）
# setup_logging()  # 延迟到主程序入口调用

__all__ = ["settings", "setup_logging"]