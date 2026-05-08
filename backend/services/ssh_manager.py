"""
SSH connection pool manager using asyncssh.
Maintains at most `connection_pool_max` connections per VM,
reusing existing connections where possible.
Runtime config (set via /api/config) takes priority over config.yaml.
"""

from __future__ import annotations

import asyncio
import socket
from pathlib import Path
from typing import AsyncIterator

import asyncssh
from asyncssh import SSHClientConnection, SSHCompletedProcess

from backend.core.config import AppConfig, VmConfig, get_config
from backend.core.logging import get_logger

logger = get_logger(__name__)


class SshCommandError(RuntimeError):
    """Raised when a remote command exits with a non-zero status."""

    def __init__(self, cmd: str, exit_code: int, stderr: str) -> None:
        super().__init__(
            f"Command failed (exit={exit_code}): {cmd!r}\nstderr: {stderr}"
        )
        self.cmd = cmd
        self.exit_code = exit_code
        self.stderr = stderr


def _dbg(msg: str, hypothesis_id: str, data: dict, run_id: str = "pre-fix") -> None:
    # region agent log
    import json, time
    try:
        with open("debug-eb5d37.log", "a", encoding="utf-8") as _f:
            _f.write(
                json.dumps(
                    {
                        "sessionId": "eb5d37",
                        "runId": run_id,
                        "hypothesisId": hypothesis_id,
                        "timestamp": int(time.time() * 1000),
                        "location": "backend/services/ssh_manager.py",
                        "message": msg,
                        "data": data,
                    }
                )
                + "\n"
            )
    except Exception: pass
    # endregion


def _get_vm_sudo_password(vm_name: str) -> str:
    """
    Returns the sudo password for the given VM if password auth is enabled,
    otherwise returns an empty string.
    """
    from backend.services.runtime_config import get_runtime_config
    rt = get_runtime_config()
    rt_vm = getattr(rt, vm_name, None)
    if rt_vm and rt_vm.use_password_auth and rt_vm.ssh_password:
        return rt_vm.ssh_password
    return ""


def _inject_sudo_password(command: str, password: str) -> str:
    """
    Rewrites a command that uses `sudo` to feed the password via `sudo -S`.
    Handles commands where sudo is at the start or anywhere in a pipeline.
    Single-quotes in the password are escaped for safe shell embedding.
    """
    if not password or "sudo" not in command:
        return command
    # Escape single quotes in password for safe embedding in shell
    esc_pass = password.replace("'", "'\\''")
    # Rewrite every `sudo ` occurrence to `sudo -S -p '' ` and prepend the
    # password on a dedicated line so the first sudo reads it from stdin.
    # We use a here-string via `bash -c` to keep it shell-agnostic.
    rewritten = command.replace("sudo ", "sudo -S -p '' ", 1)
    return f"echo '{esc_pass}' | {rewritten}"


def _resolve_vm_params(vm_name: str, cfg: AppConfig) -> dict:
    """
    Merge runtime config overrides on top of config.yaml values.
    Returns a dict of SSH connection parameters.
    """
    from backend.services.runtime_config import get_runtime_config

    rt = get_runtime_config()
    rt_vm = getattr(rt, vm_name)
    cfg_vm: VmConfig = getattr(cfg.infrastructure, vm_name)

    host = rt_vm.host or cfg_vm.host
    port = rt_vm.port if rt_vm.host else cfg_vm.port
    user = rt_vm.user or cfg_vm.user

    # region agent log
    _dbg("resolve_vm_params", "H-B", {
        "vm": vm_name,
        "rt_host": rt_vm.host, "rt_user": rt_vm.user,
        "rt_use_password_auth": rt_vm.use_password_auth,
        "rt_has_password": bool(rt_vm.ssh_password),
        "rt_configured": rt.configured,
        "resolved_host": host, "resolved_user": user,
    })
    # endregion

    params: dict = dict(
        host=host,
        port=port,
        username=user,
        known_hosts=None,
        family=socket.AF_INET,
    )

    if rt_vm.use_password_auth and rt_vm.ssh_password:
        params["password"] = rt_vm.ssh_password
        params["username"] = user
        params["preferred_auth"] = "password"
        params["client_keys"] = None
        # region agent log
        _dbg("auth_mode", "H-D", {"vm": vm_name, "mode": "password",
                            "preferred_auth": "password", "client_keys": None})
        # endregion
    else:
        key_path_str = rt_vm.ssh_key_path or cfg_vm.ssh_key_path
        # region agent log
        _dbg("auth_mode", "H-B", {"vm": vm_name, "mode": "key",
                            "key_path": key_path_str})
        # endregion
        if key_path_str:
            key_path = Path(key_path_str).expanduser()
            if not key_path.exists():
                raise FileNotFoundError(
                    f"SSH key not found: {key_path}\n"
                    f"Fix this in the ⚙️ Settings panel or set the correct path in config.yaml."
                )
            params["client_keys"] = [str(key_path)]
        else:
            raise FileNotFoundError(
                "SSH key path is empty and password auth is disabled.\n"
                "⚙️ Settings panelini aç → 'Password' seç → şifreyi gir → Kaydet."
            )

    return params


class VmSshPool:
    """Per-VM SSH connection pool with a configurable max size."""

    def __init__(self, vm_name: str, cfg: AppConfig) -> None:
        self._vm_name = vm_name
        self._max = cfg.ssh.connection_pool_max
        self._timeout = cfg.ssh.connect_timeout
        self._cmd_timeout = cfg.ssh.command_timeout
        self._keepalive = cfg.ssh.keepalive_interval
        self._pool: list[SSHClientConnection] = []
        self._lock = asyncio.Lock()

    async def _connect(self) -> SSHClientConnection:
        cfg = get_config()
        params = _resolve_vm_params(self._vm_name, cfg)
        params["keepalive_interval"] = self._keepalive

        try:
            conn = await asyncio.wait_for(
                asyncssh.connect(**params),
                timeout=self._timeout,
            )
        except Exception as exc:
            # region agent log
            _dbg("connect_error", "H-A", {
                "vm": self._vm_name,
                "exc_type": type(exc).__name__,
                "exc_msg": str(exc),
                "host": params.get("host"),
                "user": params.get("username"),
                "preferred_auth": params.get("preferred_auth"),
                "has_password": "password" in params,
                "has_keys": params.get("client_keys") is not None,
            })
            # endregion
            raise

        logger.info(
            "ssh_connected",
            vm=self._vm_name,
            host=params["host"],
            pool_size=len(self._pool) + 1,
        )
        return conn

    async def acquire(self) -> SSHClientConnection:
        async with self._lock:
            alive = []
            for conn in self._pool:
                try:
                    if not conn.is_closing():
                        alive.append(conn)
                except Exception:  # noqa: BLE001
                    pass
            self._pool = alive

            if self._pool:
                return self._pool[0]

            if len(self._pool) < self._max:
                conn = await self._connect()
                self._pool.append(conn)
                return conn

            return self._pool[0]

    async def run(self, command: str, *, check: bool = True) -> SSHCompletedProcess:
        conn = await self.acquire()
        # Auto-inject sudo password when password auth is enabled
        sudo_pass = _get_vm_sudo_password(self._vm_name)
        actual_command = _inject_sudo_password(command, sudo_pass)
        # region agent log
        _dbg(
            "run_command",
            "H-E",
            {"vm": self._vm_name, "command": actual_command[:240], "check": check},
        )
        # endregion
        try:
            result = await asyncio.wait_for(
                conn.run(actual_command, check=False),
                timeout=self._cmd_timeout,
            )
        except asyncssh.DisconnectError:
            logger.warning("ssh_reconnecting", vm=self._vm_name)
            async with self._lock:
                self._pool.clear()
            conn = await self.acquire()
            result = await asyncio.wait_for(
                conn.run(command, check=False),
                timeout=self._cmd_timeout,
            )

        logger.debug(
            "ssh_command",
            vm=self._vm_name,
            cmd=command[:120],
            exit_code=result.exit_status,
        )

        if check and result.exit_status != 0:
            stderr = result.stderr or ""
            lower_stderr = stderr.lower()
            sudo_password_detected = (
                "terminal is required" in lower_stderr
                or "password is required" in lower_stderr
                or "a password is required" in lower_stderr
            )
            # region agent log
            _dbg(
                "command_failed",
                "H-C",
                {
                    "vm": self._vm_name,
                    "command": command[:240],
                    "exit_status": result.exit_status,
                    "stderr": stderr[:600],
                    "sudo_password_detected": sudo_password_detected,
                    "stderr_has_turkish_sifre": "şifre" in lower_stderr or "sifre" in lower_stderr,
                },
            )
            # endregion
            # Detect passwordless-sudo not configured — give actionable message
            if "sudo" in command and (
                "terminal is required" in stderr
                or "password is required" in stderr
                or "a password is required" in stderr
            ):
                from backend.services.runtime_config import get_runtime_config
                runtime_cfg = get_runtime_config()
                vm_user = runtime_cfg.vm2.user or "ubuntu"
                # region agent log
                _dbg(
                    "sudo_password_branch",
                    "H-A",
                    {
                        "vm": self._vm_name,
                        "suggested_user": vm_user,
                        "runtime_vm1_user": runtime_cfg.vm1.user,
                        "runtime_vm2_user": runtime_cfg.vm2.user,
                    },
                )
                # endregion
                raise SshCommandError(
                    command,
                    result.exit_status,
                    f"sudo şifre istiyor. Her iki VM'de şunu çalıştır:\n"
                    f"  echo '{vm_user} ALL=(ALL) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/vpn-bench\n"
                    f"  sudo chmod 440 /etc/sudoers.d/vpn-bench",
                )
            raise SshCommandError(command, result.exit_status, stderr)

        return result

    async def stream_run(self, command: str) -> AsyncIterator[str]:
        """Run a long-running command and yield stdout lines as they arrive."""
        conn = await self.acquire()
        async with conn.create_process(command) as proc:
            async for line in proc.stdout:
                yield line.rstrip("\n")

    async def close_all(self) -> None:
        async with self._lock:
            for conn in self._pool:
                conn.close()
            self._pool.clear()
        logger.info("ssh_pool_closed", vm=self._vm_name)


class SshManager:
    """
    Application-level SSH manager.
    Owns one VmSshPool per VM and exposes a clean API.
    Pools are re-created after runtime config changes (shutdown() clears them).
    """

    def __init__(self) -> None:
        self._cfg = get_config()
        self._pools: dict[str, VmSshPool] = {}

    def pool_vm1(self) -> VmSshPool:
        return self._pool("vm1")

    def pool_vm2(self) -> VmSshPool:
        return self._pool("vm2")

    def pool_vm3(self) -> VmSshPool:
        return self._pool("vm3")

    def _pool(self, vm_name: str) -> VmSshPool:
        if vm_name not in self._pools:
            self._pools[vm_name] = VmSshPool(vm_name, self._cfg)
        return self._pools[vm_name]

    async def run_vm1(self, command: str, *, check: bool = True) -> SSHCompletedProcess:
        return await self._pool("vm1").run(command, check=check)

    async def run_vm2(self, command: str, *, check: bool = True) -> SSHCompletedProcess:
        return await self._pool("vm2").run(command, check=check)

    async def run_vm3(self, command: str, *, check: bool = True) -> SSHCompletedProcess:
        return await self._pool("vm3").run(command, check=check)

    async def stream_vm1(self, command: str) -> AsyncIterator[str]:
        return self._pool("vm1").stream_run(command)

    async def stream_vm2(self, command: str) -> AsyncIterator[str]:
        return self._pool("vm2").stream_run(command)

    async def stream_vm3(self, command: str) -> AsyncIterator[str]:
        return self._pool("vm3").stream_run(command)

    async def shutdown(self) -> None:
        for pool in self._pools.values():
            await pool.close_all()
        self._pools.clear()
        logger.info("ssh_manager_reset")


_ssh_manager: SshManager | None = None


def get_ssh_manager() -> SshManager:
    global _ssh_manager
    if _ssh_manager is None:
        _ssh_manager = SshManager()
    return _ssh_manager
