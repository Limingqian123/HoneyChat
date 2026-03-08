# services/honeypot/attack_analyzer.py
"""
攻击链分析器

分析命令序列，识别攻击阶段和TTP（战术、技术、过程）
"""

from typing import List, Dict, Optional
import structlog

logger = structlog.get_logger(__name__)


class AttackPhase:
    """攻击阶段"""
    RECONNAISSANCE = "reconnaissance"  # 侦察
    PRIVILEGE_ESCALATION = "privilege_escalation"  # 提权
    PERSISTENCE = "persistence"  # 持久化
    CREDENTIAL_ACCESS = "credential_access"  # 凭证访问
    DISCOVERY = "discovery"  # 发现
    COLLECTION = "collection"  # 收集
    EXFILTRATION = "exfiltration"  # 数据窃取
    UNKNOWN = "unknown"


class AttackAnalyzer:
    """攻击分析器"""

    def __init__(self):
        # 命令模式 -> 攻击阶段映射
        self.patterns = {
            AttackPhase.RECONNAISSANCE: [
                "whoami", "id", "uname", "hostname", "ifconfig", "ip addr",
                "ps", "netstat", "ss", "w", "who", "last"
            ],
            AttackPhase.PRIVILEGE_ESCALATION: [
                "sudo", "su", "chmod +s", "pkexec", "exploit"
            ],
            AttackPhase.PERSISTENCE: [
                "crontab", "systemctl", "service", "rc.local", ".bashrc",
                "authorized_keys", "startup"
            ],
            AttackPhase.CREDENTIAL_ACCESS: [
                "passwd", "shadow", "password", "credential", ".ssh",
                "id_rsa", "private key", "token"
            ],
            AttackPhase.DISCOVERY: [
                "find", "locate", "ls -R", "tree", "grep -r", "search"
            ],
            AttackPhase.COLLECTION: [
                "tar", "zip", "gzip", "compress", "archive"
            ],
            AttackPhase.EXFILTRATION: [
                "curl", "wget", "scp", "ftp", "nc", "netcat", "base64"
            ],
        }

    def analyze_command(self, command: str) -> str:
        """分析单个命令，返回攻击阶段"""
        cmd_lower = command.lower()

        for phase, keywords in self.patterns.items():
            if any(kw in cmd_lower for kw in keywords):
                return phase

        return AttackPhase.UNKNOWN

    def analyze_session(self, commands: List[str]) -> Dict:
        """分析整个会话的命令序列"""
        if not commands:
            return {"phases": [], "summary": "No commands"}

        # 统计各阶段
        phase_counts = {}
        phase_sequence = []

        for cmd in commands:
            phase = self.analyze_command(cmd)
            phase_sequence.append(phase)
            phase_counts[phase] = phase_counts.get(phase, 0) + 1

        # 生成摘要
        dominant_phase = max(phase_counts.items(), key=lambda x: x[1])[0]

        return {
            "total_commands": len(commands),
            "phases": phase_counts,
            "sequence": phase_sequence,
            "dominant_phase": dominant_phase,
            "summary": self._generate_summary(phase_counts, dominant_phase),
        }

    def _generate_summary(self, phase_counts: Dict, dominant_phase: str) -> str:
        """生成攻击摘要"""
        summaries = {
            AttackPhase.RECONNAISSANCE: "Attacker is performing reconnaissance",
            AttackPhase.PRIVILEGE_ESCALATION: "Privilege escalation attempt detected",
            AttackPhase.PERSISTENCE: "Persistence mechanism installation detected",
            AttackPhase.CREDENTIAL_ACCESS: "Credential harvesting activity detected",
            AttackPhase.DISCOVERY: "System discovery and enumeration",
            AttackPhase.COLLECTION: "Data collection activity",
            AttackPhase.EXFILTRATION: "Data exfiltration attempt detected",
        }

        return summaries.get(dominant_phase, "Unknown attack pattern")

    def get_risk_score(self, commands: List[str]) -> int:
        """计算风险评分 (0-100)"""
        if not commands:
            return 0

        analysis = self.analyze_session(commands)
        score = 0

        # 基础分数：命令数量
        score += min(len(commands) * 2, 20)

        # 高危阶段加分
        high_risk_phases = [
            AttackPhase.PRIVILEGE_ESCALATION,
            AttackPhase.PERSISTENCE,
            AttackPhase.EXFILTRATION,
        ]

        for phase in high_risk_phases:
            if phase in analysis["phases"]:
                score += analysis["phases"][phase] * 10

        return min(score, 100)
