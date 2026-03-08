# services/honeypot/virtual_fs.py
"""
虚拟文件系统

模拟真实的Linux文件系统，支持基础文件操作。
不需要真实文件，用字典结构模拟。
"""

import os
from typing import Dict, List, Optional, Tuple
import structlog

logger = structlog.get_logger(__name__)


class VirtualFileSystem:
    """虚拟文件系统"""

    def __init__(self):
        # 文件系统结构：路径 -> {"type": "file"|"dir", "content": str, "size": int}
        self.fs: Dict[str, Dict] = self._init_default_fs()

    def _init_default_fs(self) -> Dict[str, Dict]:
        """初始化默认文件系统结构"""
        return {
            "/": {"type": "dir"},
            "/home": {"type": "dir"},
            "/home/user": {"type": "dir"},
            "/home/user/.bashrc": {
                "type": "file",
                "content": "# .bashrc\nexport PATH=/usr/local/bin:$PATH\nalias ll='ls -la'\n",
                "size": 65,
            },
            "/home/user/.bash_history": {
                "type": "file",
                "content": "ls\ncd /tmp\nwhoami\n",
                "size": 20,
            },
            "/tmp": {"type": "dir"},
            "/etc": {"type": "dir"},
            "/etc/passwd": {
                "type": "file",
                "content": "root:x:0:0:root:/root:/bin/bash\nuser:x:1000:1000::/home/user:/bin/bash\n",
                "size": 80,
            },
            "/etc/hosts": {
                "type": "file",
                "content": "127.0.0.1 localhost\n192.168.1.100 server\n",
                "size": 45,
            },
            "/var": {"type": "dir"},
            "/var/log": {"type": "dir"},
            "/usr": {"type": "dir"},
            "/usr/bin": {"type": "dir"},
        }

    def normalize_path(self, path: str, cwd: str) -> str:
        """规范化路径（处理相对路径、..、.等）"""
        if not path.startswith("/"):
            path = os.path.join(cwd, path)
        return os.path.normpath(path)

    def exists(self, path: str) -> bool:
        """检查路径是否存在"""
        return path in self.fs

    def is_dir(self, path: str) -> bool:
        """检查是否为目录"""
        return path in self.fs and self.fs[path].get("type") == "dir"

    def is_file(self, path: str) -> bool:
        """检查是否为文件"""
        return path in self.fs and self.fs[path].get("type") == "file"

    def ls(self, path: str) -> List[str]:
        """列出目录内容"""
        if not self.is_dir(path):
            return []

        # 查找所有子项
        children = []
        path_prefix = path if path.endswith("/") else path + "/"
        if path == "/":
            path_prefix = "/"

        for p in self.fs.keys():
            if p == path:
                continue
            if p.startswith(path_prefix):
                # 只取直接子项
                relative = p[len(path_prefix):]
                if "/" not in relative:
                    children.append(relative)

        return sorted(children)

    def cat(self, path: str) -> Optional[str]:
        """读取文件内容"""
        if not self.is_file(path):
            return None
        return self.fs[path].get("content", "")

    def mkdir(self, path: str) -> bool:
        """创建目录"""
        if self.exists(path):
            return False

        # 检查父目录是否存在
        parent = os.path.dirname(path)
        if parent and not self.is_dir(parent):
            return False

        self.fs[path] = {"type": "dir"}
        logger.debug("Virtual directory created", path=path)
        return True

    def touch(self, path: str, content: str = "") -> bool:
        """创建或更新文件"""
        # 检查父目录是否存在
        parent = os.path.dirname(path)
        if parent and not self.is_dir(parent):
            return False

        self.fs[path] = {
            "type": "file",
            "content": content,
            "size": len(content),
        }
        logger.debug("Virtual file created", path=path, size=len(content))
        return True

    def rm(self, path: str) -> bool:
        """删除文件或空目录"""
        if not self.exists(path):
            return False

        # 如果是目录，检查是否为空
        if self.is_dir(path):
            if self.ls(path):
                return False  # 目录非空

        del self.fs[path]
        logger.debug("Virtual path removed", path=path)
        return True

    def add_bait_file(self, path: str, content: str):
        """添加诱饵文件"""
        self.touch(path, content)
        logger.info("Bait file added", path=path)


# 文件系统命令处理器
class FSCommandHandler:
    """处理文件系统相关命令"""

    def __init__(self, vfs: VirtualFileSystem):
        self.vfs = vfs

    def handle(self, command: str, cwd: str) -> Tuple[Optional[str], Optional[str]]:
        """
        处理命令，返回 (响应, 新的cwd)
        如果无法处理返回 (None, None)
        """
        parts = command.strip().split()
        if not parts:
            return None, None

        cmd = parts[0]

        # cd 命令
        if cmd == "cd":
            target = parts[1] if len(parts) > 1 else "/home/user"
            new_path = self.vfs.normalize_path(target, cwd)

            if self.vfs.is_dir(new_path):
                return "", new_path
            else:
                return f"cd: {target}: No such file or directory\n", None

        # pwd 命令
        elif cmd == "pwd":
            return f"{cwd}\n", None

        # ls 命令
        elif cmd == "ls":
            target = parts[1] if len(parts) > 1 else cwd
            path = self.vfs.normalize_path(target, cwd)

            if not self.vfs.exists(path):
                return f"ls: cannot access '{target}': No such file or directory\n", None

            if self.vfs.is_file(path):
                return f"{os.path.basename(path)}\n", None

            items = self.vfs.ls(path)
            if not items:
                return "", None
            return "  ".join(items) + "\n", None

        # cat 命令
        elif cmd == "cat":
            if len(parts) < 2:
                return "cat: missing file operand\n", None

            target = parts[1]
            path = self.vfs.normalize_path(target, cwd)

            content = self.vfs.cat(path)
            if content is None:
                return f"cat: {target}: No such file or directory\n", None
            return content, None

        # mkdir 命令
        elif cmd == "mkdir":
            if len(parts) < 2:
                return "mkdir: missing operand\n", None

            target = parts[1]
            path = self.vfs.normalize_path(target, cwd)

            if self.vfs.mkdir(path):
                return "", None
            else:
                return f"mkdir: cannot create directory '{target}': File exists\n", None

        # touch 命令
        elif cmd == "touch":
            if len(parts) < 2:
                return "touch: missing file operand\n", None

            target = parts[1]
            path = self.vfs.normalize_path(target, cwd)

            if self.vfs.touch(path):
                return "", None
            else:
                return f"touch: cannot touch '{target}': No such file or directory\n", None

        # 无法处理的命令
        return None, None
