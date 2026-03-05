# services/rag-engine/rag/__init__.py
"""
RAG 引擎核心模块包。

提供向量数据库封装、LLM 封装和提示词模板管理。
"""

__version__ = "1.0.0"

# 当具体模块实现后，将在下面导入并添加到 __all__
from .vector_store import VectorStore
from .llm_wrapper import LLMWrapper
from .prompt_templates import PromptManager

__all__ = ["VectorStore", "LLMWrapper", "PromptManager"]