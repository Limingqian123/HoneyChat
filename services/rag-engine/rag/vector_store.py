# services/rag-engine/rag/vector_store.py
"""
向量数据库封装模块。

基于 ChromaDB 实现命令-输出对的存储与相似度检索。
支持从 JSON 文件批量加载数据，并提供线程安全的客户端。
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils import embedding_functions
import structlog

logger = structlog.get_logger(__name__)


class VectorStore:
    """
    向量数据库封装类。

    负责初始化 Chroma 集合、添加文档、检索相似文档。
    使用默认的 all-MiniLM-L6-v2 嵌入模型。
    """

    def __init__(
        self,
        persist_directory: Path,
        collection_name: str = "command_pairs",
        embedding_model: str = "all-MiniLM-L6-v2",
        top_k: int = 3,
    ):
        """
        初始化向量存储。

        Args:
            persist_directory: ChromaDB 持久化目录
            collection_name: 集合名称
            embedding_model: 嵌入模型名称 (sentence-transformers)
            top_k: 默认检索数量
        """
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self.top_k = top_k

        # 确保持久化目录存在
        persist_directory.mkdir(parents=True, exist_ok=True)

        # 初始化 Chroma 客户端（使用持久化设置）
        self.client = chromadb.PersistentClient(
            path=str(persist_directory),
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True,  # 允许重置（仅用于测试）
            ),
        )

        # 创建嵌入函数
        self.embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=embedding_model
        )

        # 获取或创建集合
        self.collection = self._get_or_create_collection()

        logger.info(
            "Vector store initialized",
            persist_directory=str(persist_directory),
            collection=collection_name,
            embedding_model=embedding_model,
        )

    def _get_or_create_collection(self):
        """获取现有集合或创建新集合。"""
        try:
            # 尝试获取现有集合
            collection = self.client.get_collection(
                name=self.collection_name,
                embedding_function=self.embedding_func,
            )
            logger.info("Existing collection loaded", name=self.collection_name)
            return collection
        except ValueError:
            # 集合不存在，创建新集合
            logger.info("Creating new collection", name=self.collection_name)
            return self.client.create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_func,
                metadata={"hnsw:space": "cosine"},  # 使用余弦相似度
            )

    def add_documents(self, commands: List[str], outputs: List[str], ids: Optional[List[str]] = None) -> None:
        """
        向向量库添加文档。

        Args:
            commands: 命令列表
            outputs: 对应输出列表
            ids: 可选 ID 列表，若不提供则自动生成
        """
        if len(commands) != len(outputs):
            raise ValueError("commands and outputs must have the same length")

        if ids is None:
            # 生成基于内容的 ID（简单哈希）
            ids = [f"doc_{hash(cmd)}_{i}" for i, cmd in enumerate(commands)]
        else:
            if len(ids) != len(commands):
                raise ValueError("ids length mismatch")

        # 构造元数据（将输出存储在元数据中，也可作为文档内容）
        metadatas = [{"output": out} for out in outputs]

        try:
            self.collection.upsert(
                documents=commands,
                metadatas=metadatas,
                ids=ids,
            )
            logger.info("Documents added", count=len(commands))
        except Exception as e:
            logger.exception("Failed to add documents", error=str(e))
            raise

    def load_from_json(self, json_path: Path) -> int:
        """
        从 JSON 文件加载命令-输出对并添加到向量库。

        JSON 格式应为列表，每个元素为 {"command": "...", "output": "..."}

        Args:
            json_path: JSON 文件路径

        Returns:
            添加的文档数量
        """
        if not json_path.exists():
            logger.warning("JSON file not found, skipping load", path=str(json_path))
            return 0

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error("Failed to load JSON file", path=str(json_path), error=str(e))
            return 0

        if not isinstance(data, list):
            logger.error("JSON data is not a list", path=str(json_path))
            return 0

        commands = []
        outputs = []
        for item in data:
            if isinstance(item, dict) and "command" in item and "output" in item:
                commands.append(item["command"])
                outputs.append(item["output"])
            else:
                logger.warning("Skipping invalid item in JSON", item=item)

        if not commands:
            logger.warning("No valid command-output pairs found in JSON", path=str(json_path))
            return 0

        self.add_documents(commands, outputs)
        return len(commands)

    def search(self, query: str, top_k: Optional[int] = None) -> List[Tuple[str, str, float]]:
        """
        检索与查询最相似的文档。

        Args:
            query: 查询字符串（通常是攻击者输入的命令）
            top_k: 返回的最大结果数，若未提供则使用实例的 top_k

        Returns:
            列表，每个元素为 (command, output, distance) 元组，
            按距离升序（越相似距离越小）
        """
        k = top_k or self.top_k
        if k <= 0:
            return []

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=k,
                include=["documents", "metadatas", "distances"],
            )

            # 解析结果
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            dists = results.get("distances", [[]])[0]

            # 构建返回列表
            ret = []
            for doc, meta, dist in zip(docs, metas, dists):
                output = meta.get("output", "") if meta else ""
                ret.append((doc, output, dist))

            logger.debug(
                "Vector search completed",
                query=query[:50],
                results=len(ret),
            )
            return ret
        except Exception as e:
            logger.exception("Vector search failed", query=query, error=str(e))
            return []

    def count(self) -> int:
        """返回集合中的文档数量。"""
        return self.collection.count()

    def reset(self) -> None:
        """
        重置集合（清空所有文档）。
        仅用于测试，谨慎使用。
        """
        try:
            self.client.delete_collection(self.collection_name)
            self.collection = self._get_or_create_collection()
            logger.info("Vector store reset")
        except Exception as e:
            logger.exception("Failed to reset vector store", error=str(e))
            raise

    def close(self) -> None:
        """
        关闭客户端（释放资源）。
        ChromaDB 客户端没有显式 close 方法，但为了接口一致性保留。
        """
        # ChromaDB 客户端在 Python 退出时自动清理
        logger.info("Vector store closed")