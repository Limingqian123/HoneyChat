# services/honeypot/scenario_engine.py
"""
攻击剧本引擎

根据攻击者行为动态投放诱饵，引导攻击者暴露更多TTP。
"""

import random
from typing import List, Dict, Optional
import structlog

logger = structlog.get_logger(__name__)


class Scenario:
    """攻击场景"""

    def __init__(self, name: str, triggers: List[str], baits: Dict[str, str]):
        self.name = name
        self.triggers = triggers  # 触发关键词
        self.baits = baits  # 诱饵文件 {路径: 内容}

    def is_triggered(self, command: str) -> bool:
        """检查命令是否触发该场景"""
        cmd_lower = command.lower()
        return any(trigger in cmd_lower for trigger in self.triggers)


class ScenarioEngine:
    """场景引擎"""

    def __init__(self):
        self.scenarios = self._init_scenarios()
        self.deployed_baits: Dict[str, set] = {}  # session_id -> set of bait paths

    def _init_scenarios(self) -> List[Scenario]:
        """初始化预设场景"""
        return [
            # 场景1：寻找配置文件
            Scenario(
                name="config_hunt",
                triggers=["config", "conf", ".env", "settings"],
                baits={
                    "/home/user/config.php": "<?php\n$db_host='localhost';\n$db_user='admin';\n$db_pass='P@ssw0rd123';\n?>",
                    "/home/user/.env": "DB_HOST=localhost\nDB_USER=root\nDB_PASS=secret123\nAPI_KEY=sk_test_abc123",
                },
            ),
            # 场景2：寻找SSH密钥
            Scenario(
                name="ssh_key_hunt",
                triggers=["ssh", "id_rsa", ".ssh", "key"],
                baits={
                    "/home/user/.ssh/id_rsa": "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...[fake key]...\n-----END RSA PRIVATE KEY-----",
                    "/home/user/.ssh/authorized_keys": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ... admin@server",
                },
            ),
            # 场景3：寻找密码文件
            Scenario(
                name="password_hunt",
                triggers=["password", "passwd", "shadow", "credential"],
                baits={
                    "/tmp/passwords.txt": "admin:Admin@123\nroot:Root@2024\nuser:User@456",
                    "/home/user/backup/shadow.bak": "root:$6$fake$hash:18000:0:99999:7:::\nuser:$6$fake$hash2:18000:0:99999:7:::",
                },
            ),
            # 场景4：寻找数据库备份
            Scenario(
                name="database_hunt",
                triggers=["database", "backup", ".sql", "dump"],
                baits={
                    "/var/backups/db_backup.sql": "-- MySQL dump\nCREATE TABLE users (id INT, username VARCHAR(50), password VARCHAR(255));\nINSERT INTO users VALUES (1, 'admin', 'hashed_password');",
                },
            ),
        ]

    def check_and_deploy(self, session_id: str, command: str, vfs) -> Optional[str]:
        """
        检查命令是否触发场景，如果触发则部署诱饵
        返回提示信息（可选）
        """
        if session_id not in self.deployed_baits:
            self.deployed_baits[session_id] = set()

        for scenario in self.scenarios:
            if scenario.is_triggered(command):
                # 检查是否已部署
                new_baits = []
                for path, content in scenario.baits.items():
                    if path not in self.deployed_baits[session_id]:
                        vfs.add_bait_file(path, content)
                        self.deployed_baits[session_id].add(path)
                        new_baits.append(path)

                if new_baits:
                    logger.info(
                        "Scenario triggered, baits deployed",
                        session_id=session_id,
                        scenario=scenario.name,
                        baits=new_baits,
                    )
                    # 可选：返回一个提示（让攻击者"发现"诱饵）
                    # 这里不返回，让攻击者自己探索
                    return None

        return None

    def get_random_hint(self, session_id: str) -> Optional[str]:
        """随机返回一个提示（模拟系统泄露信息）"""
        hints = [
            "# Backup files found in /tmp",
            "# Config files in current directory",
            "# Check .ssh directory for keys",
        ]
        if random.random() < 0.1:  # 10%概率
            return random.choice(hints)
        return None
