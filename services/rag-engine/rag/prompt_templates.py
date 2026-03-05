# services/rag-engine/rag/prompt_templates.py
"""
提示词模板管理模块。

提供用于构建 RAG 提示词的模板，支持动态插入检索结果、威胁标签等信息。
"""

from typing import List, Optional, Dict, Any
from string import Template


class PromptManager:
    """
    提示词管理器，负责根据上下文生成最终发送给 LLM 的提示词。
    """

    # 默认系统提示词模板
    DEFAULT_SYSTEM_TEMPLATE = """You are a realistic command-line simulator. You must respond to the user's command as if you are a real Linux system. Use the provided context from historical command-output pairs to ensure your responses are consistent and believable. Do not reveal that you are an AI or a simulator. Keep responses concise and technical, matching the style of a real system.

${context_str}

User command: ${command}
System response:"""

    # 简洁版本（当没有检索结果时）
    FALLBACK_SYSTEM_TEMPLATE = """You are a realistic command-line simulator. Respond to the user's command as if you are a real Linux system. Keep responses concise and technical.

User command: ${command}
System response:"""

    def __init__(self, system_template: Optional[str] = None):
        """
        初始化提示词管理器。

        Args:
            system_template: 自定义系统提示词模板，使用 ${variable} 占位符。
        """
        self.system_template = system_template or self.DEFAULT_SYSTEM_TEMPLATE
        self.fallback_template = self.FALLBACK_SYSTEM_TEMPLATE

    def build_prompt(
        self,
        command: str,
        context_pairs: Optional[List[tuple]] = None,
        threat_tags: Optional[List[str]] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """
        构建完整的提示词。

        Args:
            command: 用户输入的命令
            context_pairs: 检索到的上下文对列表，每个元素为 (command, output, distance)
            threat_tags: 威胁情报标签列表
            session_id: 会话 ID（可选，用于日志）

        Returns:
            构建好的提示词字符串
        """
        # 构建上下文部分
        context_str = self._format_context(context_pairs or [])

        # 如果有威胁标签，可以添加到上下文中（可选）
        if threat_tags:
            tag_str = "Threat intelligence tags: " + ", ".join(threat_tags)
            context_str = context_str + "\n" + tag_str if context_str else tag_str

        # 选择模板
        if context_str.strip():
            prompt = Template(self.system_template).safe_substitute(
                context_str=context_str,
                command=command,
            )
        else:
            prompt = Template(self.fallback_template).safe_substitute(
                command=command,
            )

        return prompt.strip()

    def _format_context(self, pairs: List[tuple]) -> str:
        """
        将检索到的命令-输出对格式化为文本。

        Args:
            pairs: (command, output, distance) 元组列表

        Returns:
            格式化的上下文字符串
        """
        if not pairs:
            return ""

        lines = ["Here are some examples of similar commands and their expected outputs:"]
        for i, (cmd, out, dist) in enumerate(pairs, 1):
            # 限制输出长度，避免提示词过长
            out_preview = out[:200] + "..." if len(out) > 200 else out
            lines.append(f"\nExample {i}:\n$ {cmd}\n{out_preview}")

        return "\n".join(lines)

    def get_system_message(self) -> str:
        """返回系统提示词（用于调试）。"""
        return self.system_template


# 预定义一些特定场景的模板变体
class PromptTemplates:
    """常用提示词模板集合。"""

    # 更严格的系统提示，要求只输出命令输出
    STRICT_SYSTEM = """You are a Linux terminal simulator. Respond ONLY with the exact output that a real system would produce for the given command. Do not add explanations, comments, or any extra text. Use the context examples for reference.

Context:
${context_str}

Command: ${command}
Output:"""

    # 用于 HTTP API 模拟的提示
    HTTP_SYSTEM = """You are a web server simulator. Respond to the HTTP request as if you were a real API endpoint. Return appropriate HTTP headers and body. Use the context examples to match the style.

Request: ${command}
Response:"""

    # 简洁版（用于快速响应）
    CONCISE_SYSTEM = """Simulate a Linux system. Respond concisely.

Command: ${command}
Output:"""


def get_prompt_manager(style: str = "default") -> PromptManager:
    """
    工厂函数，获取指定风格的提示词管理器。

    Args:
        style: "default", "strict", "http", "concise"

    Returns:
        PromptManager 实例
    """
    templates = {
        "default": PromptManager.DEFAULT_SYSTEM_TEMPLATE,
        "strict": PromptTemplates.STRICT_SYSTEM,
        "http": PromptTemplates.HTTP_SYSTEM,
        "concise": PromptTemplates.CONCISE_SYSTEM,
    }
    template = templates.get(style, PromptManager.DEFAULT_SYSTEM_TEMPLATE)
    return PromptManager(template)