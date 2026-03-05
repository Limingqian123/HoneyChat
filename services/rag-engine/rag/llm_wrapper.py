# services/rag-engine/rag/llm_wrapper.py
"""
LLM 封装模块。

基于 llama-cpp-python 实现 GGUF 模型的加载与推理。
提供统一的生成接口，包含错误处理和日志记录。
"""

import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Union

try:
    from llama_cpp import Llama
except ImportError as e:
    raise ImportError("llama-cpp-python is not installed. Please install it with: pip install llama-cpp-python") from e

import structlog

logger = structlog.get_logger(__name__)


class LLMWrapper:
    """
    LLM 封装类。

    负责加载 GGUF 模型并提供文本生成功能。
    支持自定义生成参数（温度、top_p、重复惩罚等）。
    """

    def __init__(
        self,
        model_path: Union[str, Path],
        n_ctx: int = 2048,
        n_threads: Optional[int] = None,
        n_batch: int = 512,
        use_mlock: bool = False,
        use_mmap: bool = True,
        verbose: bool = False,
    ):
        """
        初始化 LLM 封装器。

        Args:
            model_path: GGUF 模型文件路径
            n_ctx: 上下文窗口大小
            n_threads: 推理线程数，None 表示自动
            n_batch: 批处理大小
            use_mlock: 是否锁定内存（防止交换）
            use_mmap: 是否使用内存映射加载模型
            verbose: 是否输出详细日志
        """
        self.model_path = Path(model_path)
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self.n_batch = n_batch
        self.use_mlock = use_mlock
        self.use_mmap = use_mmap
        self.verbose = verbose

        self._model: Optional[Llama] = None
        self._load_model()

    def _load_model(self) -> None:
        """加载模型文件。"""
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model file not found: {self.model_path}")

        logger.info(
            "Loading model",
            path=str(self.model_path),
            n_ctx=self.n_ctx,
            n_threads=self.n_threads,
            n_batch=self.n_batch,
        )

        try:
            start_time = time.time()
            self._model = Llama(
                model_path=str(self.model_path),
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                n_batch=self.n_batch,
                use_mlock=self.use_mlock,
                use_mmap=self.use_mmap,
                verbose=self.verbose,
            )
            load_time = time.time() - start_time
            logger.info("Model loaded successfully", load_time_seconds=round(load_time, 2))
        except Exception as e:
            logger.exception("Failed to load model", error=str(e))
            raise

    def generate(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 0.9,
        repeat_penalty: float = 1.1,
        stop: Optional[List[str]] = None,
        echo: bool = False,
    ) -> str:
        """
        生成文本。

        Args:
            prompt: 输入提示
            max_tokens: 最大生成 token 数
            temperature: 温度参数 (0.0-2.0)
            top_p: Top-p 采样 (0.0-1.0)
            repeat_penalty: 重复惩罚
            stop: 停止词列表
            echo: 是否在输出中包含提示

        Returns:
            生成的文本字符串（不包含提示，除非 echo=True）

        Raises:
            RuntimeError: 如果模型未加载或生成失败
        """
        if self._model is None:
            raise RuntimeError("Model not loaded")

        if stop is None:
            stop = []

        try:
            logger.debug(
                "Generating text",
                prompt_preview=prompt[:100],
                max_tokens=max_tokens,
                temperature=temperature,
            )

            start_time = time.time()
            output = self._model(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                repeat_penalty=repeat_penalty,
                stop=stop,
                echo=echo,
            )
            elapsed = time.time() - start_time

            # 解析输出
            if isinstance(output, dict) and "choices" in output:
                text = output["choices"][0].get("text", "")
                if echo:
                    # 如果 echo=True，文本包含 prompt，可能需要去除
                    # 简单处理：去掉开头的 prompt
                    if text.startswith(prompt):
                        text = text[len(prompt):]
                logger.debug(
                    "Generation completed",
                    elapsed_seconds=round(elapsed, 2),
                    tokens=output.get("usage", {}).get("completion_tokens", 0),
                )
                return text
            else:
                logger.error("Unexpected output format", output=output)
                return ""
        except Exception as e:
            logger.exception("Text generation failed", error=str(e))
            raise RuntimeError(f"Generation error: {e}") from e

    def close(self) -> None:
        """释放模型资源（可选）。"""
        # llama-cpp-python 没有显式 close，但可以通过删除引用触发垃圾回收
        if self._model:
            # 可以调用模型的 `__del__` 或显式置空
            self._model = None
            logger.info("Model resource released")

    def is_loaded(self) -> bool:
        """检查模型是否已加载。"""
        return self._model is not None

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型基本信息。"""
        if not self._model:
            return {}
        return {
            "path": str(self.model_path),
            "n_ctx": self.n_ctx,
            "n_vocab": getattr(self._model, "n_vocab", None),
            "n_embd": getattr(self._model, "n_embd", None),
            "model_params": {
                "n_threads": self.n_threads,
                "n_batch": self.n_batch,
                "use_mlock": self.use_mlock,
                "use_mmap": self.use_mmap,
            }
        }


# 可选：提供一个快速测试函数（当模块直接运行时）
if __name__ == "__main__":
    import sys
    # 简单测试：需要指定模型路径
    if len(sys.argv) < 2:
        print("Usage: python llm_wrapper.py <model_path>")
        sys.exit(1)

    model_path = sys.argv[1]
    llm = LLMWrapper(model_path=model_path, n_ctx=512)
    prompt = "Hello, how are you?"
    response = llm.generate(prompt, max_tokens=50)
    print(f"Prompt: {prompt}")
    print(f"Response: {response}")
    llm.close()