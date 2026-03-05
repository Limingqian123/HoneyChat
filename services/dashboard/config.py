# services/dashboard/config.py
"""
Dashboard 服务配置管理模块。

使用 Pydantic Settings 从环境变量和 YAML 文件加载配置，
环境变量优先级高于配置文件。
"""

import yaml
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
import structlog
import logging
logger = structlog.get_logger(__name__)


class Settings(BaseSettings):
    """
    Dashboard 服务配置类。

    配置加载顺序：
        1. 默认值
        2. YAML 配置文件 (config.yaml)
        3. 环境变量 (以 DASHBOARD_ 为前缀)
    """

    # 服务基础配置
    service_name: str = Field(
        "honeychat-dashboard",
        description="服务名称，用于日志和监控标识"
    )
    log_level: str = Field(
        "INFO",
        description="日志级别: DEBUG, INFO, WARNING, ERROR"
    )

    # Web 服务配置
    host: str = Field(
        "0.0.0.0",
        description="监听地址"
    )
    port: int = Field(
        5000,
        description="监听端口",
        ge=1, le=65535
    )
    debug: bool = Field(
        False,
        description="是否开启调试模式 (生产环境应关闭)"
    )

    # 数据库配置
    database_url: str = Field(
        "sqlite:///data/events.db",
        description="数据库连接字符串"
    )
    database_pool_size: int = Field(
        20,
        description="数据库连接池大小",
        ge=1
    )
    database_max_overflow: int = Field(
        10,
        description="数据库连接池最大溢出",
        ge=0
    )

    # 安全配置 (可选)
    secret_key: str = Field(
        "dev-secret-key-change-in-production",
        description="Flask 密钥，用于会话安全"
    )
    session_lifetime: int = Field(
        86400,  # 24小时
        description="会话生命周期 (秒)",
        ge=60
    )

    # CORS 配置
    cors_origins: str = Field(
        "*",
        description="允许的 CORS 来源，多个用逗号分隔"
    )

    # 路径配置
    config_file: Path = Field(
        Path("/app/config.yaml"),
        description="YAML 配置文件路径"
    )
    data_dir: Path = Field(
        Path("/app/data"),
        description="数据目录 (存放 SQLite 数据库等)"
    )

    # 内部配置字段
    config_dict: Dict[str, Any] = Field({}, exclude=True)

    # Pydantic 配置：环境变量前缀、不区分大小写、忽略无效字段
    model_config = SettingsConfigDict(
        env_prefix="DASHBOARD_",
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

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, v: str) -> str:
        """验证 CORS 来源格式，不执行严格验证，但可确保非空"""
        if not v.strip():
            return "*"
        return v

    def model_post_init(self, __context: Any) -> None:
        """加载 YAML 配置文件"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    yaml_config = yaml.safe_load(f) or {}
                self.config_dict = yaml_config
                logger.info("Loaded configuration from YAML", path=str(self.config_file))
            except Exception as e:
                logger.error("Failed to load YAML config", path=str(self.config_file), error=str(e))
        else:
            logger.info("No YAML config file found, using defaults", path=str(self.config_file))

    def get_database_config(self) -> dict:
        """返回数据库配置子集"""
        return {
            "url": self.database_url,
            "pool_size": self.database_pool_size,
            "max_overflow": self.database_max_overflow,
        }

    def get_cors_origins_list(self) -> list:
        """将逗号分隔的 CORS 来源转换为列表"""
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if not origins:
            origins = ["*"]
        return origins


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


__all__ = ["settings", "setup_logging"]