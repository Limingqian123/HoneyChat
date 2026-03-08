# services/rag-engine/config.py
"""
RAG 引擎配置管理模块。

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
    RAG 引擎配置类。

    配置加载顺序：
        1. 默认值
        2. YAML 配置文件 (config.yaml)
        3. 环境变量 (以 RAG_ENGINE_ 为前缀)
    """

    # 服务基础配置
    service_name: str = Field(
        "honeychat-rag-engine",
        description="服务名称，用于日志和监控标识"
    )
    log_level: str = Field(
        "INFO",
        description="日志级别: DEBUG, INFO, WARNING, ERROR"
    )

    # API 服务配置
    host: str = Field(
        "0.0.0.0",
        description="API 服务监听地址"
    )
    port: int = Field(
        8000,
        description="API 服务监听端口",
        ge=1, le=65535
    )

    # 模型配置
    use_remote_model: bool = Field(
        False,
        description="是否使用远程模型 (如 DeepSeek API)"
    )
    remote_api_key: Optional[str] = Field(
        None,
        description="远程模型 API 密钥"
    )
    remote_api_base: str = Field(
        "https://api.deepseek.com/v1",
        description="远程模型 API 基础 URL"
    )
    remote_model: str = Field(
        "deepseek-chat",
        description="远程模型名称"
    )

    model_path: Path = Field(
        Path("/app/models/model.bin"),
        description="LLM 模型文件路径 (GGUF 格式)"
    )
    model_n_ctx: int = Field(
        2048,
        description="模型上下文窗口大小",
        ge=128
    )
    model_n_threads: Optional[int] = Field(
        None,
        description="模型推理线程数，None 表示自动"
    )
    model_n_batch: int = Field(
        512,
        description="批处理大小",
        ge=1
    )
    model_use_mlock: bool = Field(
        False,
        description="是否锁定模型内存 (避免交换)"
    )
    model_use_mmap: bool = Field(
        True,
        description="是否使用内存映射加载模型"
    )

    # 向量数据库配置
    vector_db_path: Path = Field(
        Path("/app/chroma_db"),
        description="ChromaDB 持久化路径"
    )
    vector_db_collection: str = Field(
        "command_pairs",
        description="ChromaDB 集合名称"
    )
    embedding_model: str = Field(
        "all-MiniLM-L6-v2",
        description="嵌入模型名称 (sentence-transformers)"
    )
    top_k: int = Field(
        3,
        description="检索最相似的 k 条记录",
        ge=1
    )

    # 数据文件配置
    data_file: Optional[Path] = Field(
        Path("/app/data/command_pairs.json"),
        description="初始命令-输出对 JSON 文件路径 (可选，用于构建向量库)"
    )

    # 生成参数
    max_tokens: int = Field(
        256,
        description="最大生成 token 数",
        ge=1
    )
    temperature: float = Field(
        0.7,
        description="生成温度",
        ge=0.0, le=2.0
    )
    top_p: float = Field(
        0.9,
        description="Top-p 采样",
        ge=0.0, le=1.0
    )
    repeat_penalty: float = Field(
        1.1,
        description="重复惩罚",
        ge=1.0
    )

    # 路径配置
    config_file: Path = Field(
        Path("/app/config.yaml"),
        description="YAML 配置文件路径"
    )

    # 内部配置字段 (不通过环境变量直接设置，由 model_post_init 填充)
    config_dict: Dict[str, Any] = Field({}, exclude=True)

    # Pydantic 配置：环境变量前缀、不区分大小写、忽略无效字段
    model_config = SettingsConfigDict(
        env_prefix="RAG_ENGINE_",
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

    @field_validator("model_path")
    @classmethod
    def validate_model_path(cls, v: Path) -> Path:
        """验证模型文件是否存在 (仅当存在时)"""
        if not v.exists():
            logger.warning("Model file not found at path", path=str(v))
        return v

    def model_post_init(self, __context: Any) -> None:
        """
        加载 YAML 配置文件并合并到当前设置。
        环境变量已经通过 BaseSettings 机制自动覆盖默认值，
        此处将 YAML 配置中未被环境变量覆盖的值合并进来。
        """
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    yaml_config = yaml.safe_load(f) or {}
                # 保存原始 yaml_config 供外部使用
                self.config_dict = yaml_config
                logger.info("Loaded configuration from YAML", path=str(self.config_file))
            except Exception as e:
                logger.error("Failed to load YAML config", path=str(self.config_file), error=str(e))
        else:
            logger.info("No YAML config file found, using defaults", path=str(self.config_file))

    def get_model_config(self) -> dict:
        """返回模型配置子集"""
        return {
            "path": str(self.model_path),
            "n_ctx": self.model_n_ctx,
            "n_threads": self.model_n_threads,
            "n_batch": self.model_n_batch,
            "use_mlock": self.model_use_mlock,
            "use_mmap": self.model_use_mmap,
        }

    def get_vector_db_config(self) -> dict:
        """返回向量数据库配置子集"""
        return {
            "path": str(self.vector_db_path),
            "collection": self.vector_db_collection,
            "embedding_model": self.embedding_model,
            "top_k": self.top_k,
        }

    def get_generation_config(self) -> dict:
        """返回生成参数配置子集"""
        return {
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "repeat_penalty": self.repeat_penalty,
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


__all__ = ["settings", "setup_logging"]