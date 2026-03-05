# services/rag-engine/app.py
"""
RAG 引擎 FastAPI 应用。

提供 /generate 端点用于生成命令响应，以及 /health 端点用于健康检查。
"""

import time
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import structlog

from config import settings, setup_logging
from rag.vector_store import VectorStore
from rag.llm_wrapper import LLMWrapper
from rag.prompt_templates import PromptManager, get_prompt_manager
# 配置结构化日志
setup_logging()
logger = structlog.get_logger(__name__)


# ---------- 请求/响应模型 ----------
class GenerateRequest(BaseModel):
    """生成请求模型"""
    command: str = Field(..., description="攻击者输入的命令")
    session_id: str = Field(..., description="会话唯一标识")
    threat_tags: List[str] = Field(default_factory=list, description="威胁情报标签")
    protocol: str = Field("ssh", description="协议类型: ssh 或 http")
    client_ip: Optional[str] = Field(None, description="客户端 IP 地址")


class GenerateResponse(BaseModel):
    """生成响应模型"""
    response: str = Field(..., description="生成的响应文本")
    session_id: str = Field(..., description="会话 ID")
    confidence: Optional[float] = Field(None, description="置信度（预留）")
    error: Optional[str] = Field(None, description="错误信息（如果有）")


# ---------- 全局资源 ----------
vector_store: Optional[VectorStore] = None
llm_wrapper: Optional[LLMWrapper] = None
prompt_manager: Optional[PromptManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理：启动时初始化资源，关闭时清理。
    """
    global vector_store, llm_wrapper, prompt_manager

    logger.info("Starting RAG engine service", version="1.0.0")

    # 初始化向量存储
    try:
        vector_store = VectorStore(
            persist_directory=settings.vector_db_path,
            collection_name=settings.vector_db_collection,
            embedding_model=settings.embedding_model,
            top_k=settings.top_k,
        )
        logger.info("Vector store initialized", count=vector_store.count())

        # 如果配置了数据文件且向量库为空，则加载初始数据
        if settings.data_file and settings.data_file.exists() and vector_store.count() == 0:
            added = vector_store.load_from_json(settings.data_file)
            logger.info("Loaded initial data from JSON", path=str(settings.data_file), count=added)
    except Exception as e:
        logger.exception("Failed to initialize vector store", error=str(e))
        raise

    # 初始化 LLM
    try:
        llm_wrapper = LLMWrapper(
            model_path=settings.model_path,
            n_ctx=settings.model_n_ctx,
            n_threads=settings.model_n_threads,
            n_batch=settings.model_n_batch,
            use_mlock=settings.model_use_mlock,
            use_mmap=settings.model_use_mmap,
        )
        logger.info("LLM initialized", info=llm_wrapper.get_model_info())
    except Exception as e:
        logger.exception("Failed to initialize LLM", error=str(e))
        # 如果 LLM 初始化失败，服务仍可运行但无法生成响应，需要标记为不健康
        # 这里不抛出异常，但后续 /health 会反映
        llm_wrapper = None

    # 初始化提示词管理器（使用默认模板，可根据 protocol 调整）
    prompt_manager = get_prompt_manager("default")  # 可根据 protocol 扩展

    yield

    # 清理资源
    logger.info("Shutting down RAG engine service")
    if llm_wrapper:
        llm_wrapper.close()
    # vector_store 无需显式关闭
    logger.info("Shutdown complete")


# ---------- 创建 FastAPI 应用 ----------
app = FastAPI(
    title="HoneyChat RAG Engine",
    description="RAG-based command response generator for honeypot",
    version="1.0.0",
    lifespan=lifespan,
)

# 添加 CORS 中间件（允许蜜罐服务跨域调用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- 健康检查 ----------
@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """健康检查端点，返回服务状态和关键组件状态。"""
    status_data = {
        "status": "healthy",
        "vector_store": "ok" if vector_store else "unavailable",
        "llm": "ok" if llm_wrapper and llm_wrapper.is_loaded() else "unavailable",
    }
    if vector_store:
        status_data["vector_store_count"] = vector_store.count()

    # 如果 LLM 不可用，标记为不健康
    if not llm_wrapper or not llm_wrapper.is_loaded():
        status_data["status"] = "degraded"
        # 仍然返回 200，但服务降级

    return status_data


# ---------- 生成端点 ----------
@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest, raw_request: Request):
    """
    接收命令，检索上下文，生成响应。
    """
    req_id = f"{request.session_id}_{int(time.time())}"
    logger.info(
        "Generate request received",
        req_id=req_id,
        session_id=request.session_id,
        command=request.command[:100],
        protocol=request.protocol,
        threat_tags=request.threat_tags,
        client_ip=request.client_ip,
    )

    # 验证必要组件
    if not vector_store:
        logger.error("Vector store not available", req_id=req_id)
        raise HTTPException(status_code=503, detail="Vector store unavailable")
    if not llm_wrapper or not llm_wrapper.is_loaded():
        logger.error("LLM not available", req_id=req_id)
        raise HTTPException(status_code=503, detail="LLM unavailable")

    try:
        # 1. 向量检索
        context_pairs = vector_store.search(request.command, top_k=settings.top_k)
        logger.debug(
            "Vector search results",
            req_id=req_id,
            count=len(context_pairs),
            distances=[round(d, 4) for _, _, d in context_pairs],
        )

        # 2. 构建提示词
        # 根据协议选择不同的提示风格（可选）
        if request.protocol == "http":
            pm = get_prompt_manager("http")
        else:
            pm = prompt_manager  # 默认

        prompt = pm.build_prompt(
            command=request.command,
            context_pairs=context_pairs,
            threat_tags=request.threat_tags,
            session_id=request.session_id,
        )

        logger.debug("Generated prompt", req_id=req_id, prompt_preview=prompt[:200])

        # 3. 调用 LLM 生成
        response_text = llm_wrapper.generate(
            prompt=prompt,
            max_tokens=settings.max_tokens,
            temperature=settings.temperature,
            top_p=settings.top_p,
            repeat_penalty=settings.repeat_penalty,
            stop=["\n$ ", "\n# ", "\n> "],  # 常见提示符停止
        )

        # 清理响应：去除可能的提示符残留
        response_text = response_text.strip()
        logger.info(
            "Generation completed",
            req_id=req_id,
            response_preview=response_text[:100],
            response_length=len(response_text),
        )

        return GenerateResponse(
            response=response_text,
            session_id=request.session_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Generate request failed", req_id=req_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ---------- 可选：调试端点，返回服务信息 ----------
@app.get("/info")
async def info():
    """返回服务配置信息（不包含敏感数据）。"""
    return {
        "service": "RAG Engine",
        "version": "1.0.0",
        "vector_store_collection": settings.vector_db_collection,
        "embedding_model": settings.embedding_model,
        "top_k": settings.top_k,
        "model_loaded": llm_wrapper.is_loaded() if llm_wrapper else False,
        "model_info": llm_wrapper.get_model_info() if llm_wrapper else None,
    }