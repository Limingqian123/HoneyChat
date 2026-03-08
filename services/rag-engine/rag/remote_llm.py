# services/rag-engine/rag/remote_llm.py
"""
远程LLM包装器

支持DeepSeek等远程API调用
"""

import httpx
from typing import Optional, Dict, Any, List
import structlog

logger = structlog.get_logger(__name__)


class RemoteLLM:
    """远程LLM包装器（支持DeepSeek API）"""

    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
        timeout: int = 30,
    ):
        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)

    def generate(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 0.9,
        repeat_penalty: float = 1.1,
        stop: Optional[List[str]] = None,
        **kwargs
    ) -> str:
        """
        调用远程API生成响应

        :param prompt: 输入提示词
        :param max_tokens: 最大token数
        :param temperature: 温度
        :param top_p: top_p采样
        :param repeat_penalty: 重复惩罚（映射为frequency_penalty）
        :param stop: 停止词列表
        :return: 生成的文本
        """
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }

        # 添加可选参数
        if stop:
            payload["stop"] = stop
        if repeat_penalty > 1.0:
            payload["frequency_penalty"] = min((repeat_penalty - 1.0) * 2, 2.0)

        try:
            response = self.client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            logger.debug("Remote LLM response", model=self.model, length=len(content))
            return content

        except httpx.HTTPStatusError as e:
            logger.error("Remote LLM HTTP error", status=e.response.status_code, error=str(e))
            raise
        except Exception as e:
            logger.error("Remote LLM error", error=str(e))
            raise

    def is_loaded(self) -> bool:
        """检查模型是否可用"""
        return bool(self.api_key)

    def get_model_info(self) -> Dict[str, Any]:
        """返回模型信息"""
        return {
            "type": "remote",
            "model": self.model,
            "api_base": self.api_base,
        }

    def close(self):
        """关闭客户端"""
        self.client.close()
