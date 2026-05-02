"""
In-memory runtime configuration store.
Allows the frontend to override infrastructure settings (VM IPs, SSH credentials)
without restarting the backend or editing config.yaml.
Values here take priority over config.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RuntimeVmConfig:
    host: str = ""
    port: int = 22
    user: str = ""
    ssh_key_path: str = ""
    ssh_password: str = ""           # Alternative to key-based auth
    use_password_auth: bool = False  # If True, use password instead of key


@dataclass
class RuntimeInfraConfig:
    vm1: RuntimeVmConfig = field(default_factory=RuntimeVmConfig)
    vm2: RuntimeVmConfig = field(default_factory=RuntimeVmConfig)
    configured: bool = False         # True once user has saved settings from UI


_runtime: RuntimeInfraConfig = RuntimeInfraConfig()


def get_runtime_config() -> RuntimeInfraConfig:
    return _runtime


def update_runtime_config(
    *,
    vm1_host: Optional[str] = None,
    vm1_port: Optional[int] = None,
    vm1_user: Optional[str] = None,
    vm1_ssh_key_path: Optional[str] = None,
    vm1_ssh_password: Optional[str] = None,
    vm1_use_password_auth: Optional[bool] = None,
    vm2_host: Optional[str] = None,
    vm2_port: Optional[int] = None,
    vm2_user: Optional[str] = None,
    vm2_ssh_key_path: Optional[str] = None,
    vm2_ssh_password: Optional[str] = None,
    vm2_use_password_auth: Optional[bool] = None,
) -> RuntimeInfraConfig:
    global _runtime

    if vm1_host is not None:              _runtime.vm1.host = vm1_host
    if vm1_port is not None:              _runtime.vm1.port = vm1_port
    if vm1_user is not None:              _runtime.vm1.user = vm1_user
    if vm1_ssh_key_path is not None:      _runtime.vm1.ssh_key_path = vm1_ssh_key_path
    if vm1_ssh_password is not None:      _runtime.vm1.ssh_password = vm1_ssh_password
    if vm1_use_password_auth is not None: _runtime.vm1.use_password_auth = vm1_use_password_auth

    if vm2_host is not None:              _runtime.vm2.host = vm2_host
    if vm2_port is not None:              _runtime.vm2.port = vm2_port
    if vm2_user is not None:             _runtime.vm2.user = vm2_user
    if vm2_ssh_key_path is not None:      _runtime.vm2.ssh_key_path = vm2_ssh_key_path
    if vm2_ssh_password is not None:      _runtime.vm2.ssh_password = vm2_ssh_password
    if vm2_use_password_auth is not None: _runtime.vm2.use_password_auth = vm2_use_password_auth

    _runtime.configured = bool(
        _runtime.vm1.host and _runtime.vm2.host and
        _runtime.vm1.user and _runtime.vm2.user and
        (
            (_runtime.vm1.ssh_key_path or _runtime.vm1.ssh_password) and
            (_runtime.vm2.ssh_key_path or _runtime.vm2.ssh_password)
        )
    )

    return _runtime
