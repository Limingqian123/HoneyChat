# services/honeypot/protocol/ssh_server.py
"""
SSH 协议实现模块。

基于 paramiko 的 ServerInterface，模拟一个高交互 SSH 服务。
允许任意用户名/密码认证，接收命令并通过 handler.process_command 处理。
"""

import socket
import threading
import paramiko
import structlog
import time
from typing import Optional, Tuple

import handler
from config import settings
from utils.ip_utils import extract_client_ip, is_private_ip

logger = structlog.get_logger(__name__)

# 主机密钥（在运行时动态生成或加载，这里使用 RSA 密钥，生产环境应持久化）
HOST_KEY = paramiko.RSAKey.generate(2048)


class HoneypotSSHServer(paramiko.ServerInterface):
    """
    SSH 服务器接口实现。
    """

    def __init__(self, client_ip: str, client_port: int):
        self.client_ip = client_ip
        self.client_port = client_port
        self.event = threading.Event()
        self.session_id = handler.generate_session_id()
        self.command_count = 0
        self.last_activity = time.time()
        logger.info("New SSH connection", session_id=self.session_id, ip=client_ip, port=client_port)

    def check_channel_request(self, kind: str, chanid: int) -> int:
        """允许所有通道请求"""
        if kind == "session":
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username: str, password: str) -> int:
        """允许任意密码（生产环境可配置为仅允许特定用户名/密码，此处为了演示全部放行）"""
        logger.info("Auth attempt", session_id=self.session_id, username=username, password=password)
        # 更新活动时间
        self.last_activity = time.time()
        return paramiko.AUTH_SUCCESSFUL

    def check_auth_publickey(self, username: str, key: paramiko.PKey) -> int:
        """拒绝公钥认证（简化）"""
        return paramiko.AUTH_FAILED

    def get_allowed_auths(self, username: str) -> str:
        """返回允许的认证方式"""
        return "password"

    def check_channel_shell_request(self, channel: paramiko.Channel) -> bool:
        """处理 shell 请求（交互式终端）"""
        self.event.set()
        logger.info("Shell request", session_id=self.session_id)
        # 启动一个线程处理交互式会话
        threading.Thread(target=self._handle_shell, args=(channel,), daemon=True).start()
        return True

    def check_channel_pty_request(
        self, channel: paramiko.Channel, term: str, width: int, height: int,
        pixelwidth: int, pixelheight: int, modes: bytes
    ) -> bool:
        """允许 PTY 请求"""
        self.last_activity = time.time()
        logger.debug("PTY request", session_id=self.session_id, term=term)
        return True

    def check_channel_exec_request(self, channel: paramiko.Channel, command: bytes) -> bool:
        """处理 exec 请求（直接执行命令）"""
        self.event.set()
        cmd_str = command.decode("utf-8", errors="replace").strip()
        logger.info("Exec request", session_id=self.session_id, command=cmd_str)
        threading.Thread(target=self._handle_exec, args=(channel, cmd_str), daemon=True).start()
        return True

    def _handle_shell(self, channel: paramiko.Channel) -> None:
        """
        处理交互式 shell 会话。
        模拟一个简单的命令行环境，支持命令循环。
        """
        # 发送欢迎横幅
        banner = "Welcome to Ubuntu 22.04 LTS (GNU/Linux 5.15.0-generic x86_64)\n\n"
        channel.send(banner)

        # 命令循环
        try:
            while not channel.closed:
                # 检查空闲超时
                if time.time() - self.last_activity > settings.session_idle_timeout:
                    channel.send("\nSession timeout.\n")
                    break

                # 发送提示符
                prompt = f"user@{self.client_ip}:~$ "
                channel.send(prompt)

                # 读取一行命令（以换行符结束）
                command = ""
                while True:
                    try:
                        data = channel.recv(1024)
                        if not data:
                            return
                        # 处理退格等简单编辑（简化）
                        for byte in data:
                            if byte == 0x03:  # Ctrl+C
                                channel.send("^C\n")
                                break
                            elif byte == 0x04:  # Ctrl+D
                                channel.send("logout\n")
                                return
                            elif byte == 0x08 or byte == 0x7f:  # Backspace
                                if command:
                                    command = command[:-1]
                                    channel.send("\b \b")
                            elif byte == 0x0d:  # Enter
                                channel.send("\r\n")
                                break
                            else:
                                char = chr(byte)
                                command += char
                                channel.send(char)
                        else:
                            continue
                        break
                    except socket.timeout:
                        if time.time() - self.last_activity > settings.session_idle_timeout:
                            channel.send("\nSession timeout.\n")
                            return
                        continue

                cmd = command.strip()
                if not cmd:
                    continue

                self.command_count += 1
                self.last_activity = time.time()

                # 处理命令
                # 可以内置一些特殊命令如 exit, logout 直接断开
                if cmd.lower() in ("exit", "logout"):
                    channel.send("logout\n")
                    break

                # 调用 handler 处理命令
                response = handler.process_command(
                    session_id=self.session_id,
                    command=cmd,
                    client_ip=self.client_ip,
                    protocol="ssh",
                    threat_tags=None,  # 威胁标签可以在外部设置，此处简化
                )
                channel.send(response)

                # 如果命令过多，可限制防止资源耗尽
                if self.command_count > settings.max_session_history:
                    channel.send("\nMaximum command limit reached. Closing session.\n")
                    break

        except Exception as e:
            logger.exception("Error in shell handler", session_id=self.session_id, error=str(e))
        finally:
            try:
                channel.close()
            except:
                pass
            logger.info("Shell session closed", session_id=self.session_id, commands=self.command_count)

    def _handle_exec(self, channel: paramiko.Channel, command: str) -> None:
        """
        处理 exec 请求（单命令执行）。
        """
        try:
            self.last_activity = time.time()
            self.command_count += 1
            response = handler.process_command(
                session_id=self.session_id,
                command=command,
                client_ip=self.client_ip,
                protocol="ssh",
                threat_tags=None,
            )
            channel.send(response)
        except Exception as e:
            logger.exception("Error in exec handler", session_id=self.session_id, error=str(e))
        finally:
            channel.send_exit_status(0)  # 总是返回成功
            channel.close()
            logger.info("Exec session closed", session_id=self.session_id, command=command)


def start_ssh_server(
    host: str = "0.0.0.0",
    port: int = 2222,
) -> None:
    """
    启动 SSH 蜜罐服务器。

    在指定地址和端口上监听，每个连接启动一个新线程处理。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except Exception as e:
        logger.error("Failed to bind SSH server", host=host, port=port, error=str(e))
        return

    sock.listen(100)
    logger.info("SSH server started", host=host, port=port)

    while True:
        try:
            client, addr = sock.accept()
            client.settimeout(settings.connection_timeout)
            client_ip, client_port = addr
            logger.info("New SSH connection accepted", ip=client_ip, port=client_port)

            # 启动处理线程
            threading.Thread(target=_handle_ssh_client, args=(client, client_ip, client_port), daemon=True).start()
        except Exception as e:
            logger.exception("Error accepting SSH connection", error=str(e))


def _handle_ssh_client(client_sock: socket.socket, client_ip: str, client_port: int) -> None:
    """
    处理单个 SSH 客户端连接。
    """
    transport = paramiko.Transport(client_sock)
    transport.local_version = "SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.4"
    transport.add_server_key(HOST_KEY)

    server = HoneypotSSHServer(client_ip, client_port)

    try:
        transport.start_server(server=server)
    except paramiko.SSHException:
        # 认证失败等，忽略
        transport.close()
        return
    except Exception as e:
        logger.exception("SSH transport error", ip=client_ip, error=str(e))
        transport.close()
        return

    # 等待认证和会话开始
    channel = transport.accept(20)  # 等待 20 秒
    if channel is None:
        transport.close()
        return

    # 等待会话事件
    server.event.wait(10)
    # 保持连接直到通道关闭
    while not channel.closed:
        time.sleep(1)
    transport.close()
    logger.info("SSH client disconnected", ip=client_ip, port=client_port)


# 如果直接运行此模块，启动 SSH 服务器（用于测试）
if __name__ == "__main__":
    # 简单的测试入口
    import sys
    sys.path.insert(0, "..")  # 使得可以从上级导入 config 等
    from config import settings
    start_ssh_server(host=settings.ssh_host, port=settings.ssh_port)