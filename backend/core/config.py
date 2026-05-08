"""
Application configuration loaded from config.yaml and optional .env overrides.
All values are validated via Pydantic models — no hardcoded defaults anywhere.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator


# ── Sub-models ────────────────────────────────────────────────────────────────

class VmConfig(BaseModel):
    host: str
    port: int
    user: str
    ssh_key_path: str
    vpn_server_ip: str | None = None
    iperf3_port: int | None = None
    network_interface: str | None = None


class InfrastructureConfig(BaseModel):
    vm1: VmConfig
    vm2: VmConfig
    vm3: VmConfig | None = None


class SshConfig(BaseModel):
    connection_pool_max: int
    connect_timeout: int
    command_timeout: int
    keepalive_interval: int


class WireGuardConfig(BaseModel):
    server_interface: str
    client_interface: str
    server_vpn_ip: str
    client_vpn_ip: str
    listen_port: int
    service_name: str


class OpenVpnConfig(BaseModel):
    server_config: str
    client_config: str
    server_vpn_ip: str
    client_vpn_ip: str
    port: int
    protocol: str
    service_name: str


class IpsecConfig(BaseModel):
    server_vpn_ip: str
    client_vpn_ip: str
    service_name: str
    connection_name: str
    ike_proposal: str
    esp_proposal: str


class VpnConfig(BaseModel):
    wireguard: WireGuardConfig
    openvpn_udp: OpenVpnConfig
    openvpn_tcp: OpenVpnConfig
    ipsec: IpsecConfig


class NetworkConditionPreset(BaseModel):
    label: str
    emoji: str
    delay_ms: int
    jitter_ms: int
    loss_percent: float
    rate_mbit: int
    hping3_flood: bool
    hping3_target: str | None = None
    hping3_duration_sec: int | None = None


class LatencyTestConfig(BaseModel):
    ping_interval_sec: float
    ping_count: int
    verify_ping_count: int
    verify_max_attempts: int
    verify_wait_sec: int


class ThroughputTestConfig(BaseModel):
    iperf3_duration_sec: int
    iperf3_parallel: int
    iperf3_json: bool


class CpuTestConfig(BaseModel):
    vmstat_interval_sec: int
    vmstat_samples: int


class TestsConfig(BaseModel):
    latency: LatencyTestConfig
    throughput: ThroughputTestConfig
    cpu: CpuTestConfig


class ScoringConfig(BaseModel):
    latency_weight: float
    throughput_weight: float
    cpu_weight: float
    score_max: float


class BackendConfig(BaseModel):
    host: str
    port: int
    cors_origins: list[str]
    websocket_path: str
    websocket_heartbeat_sec: int
    log_level: str
    log_format: str


class FrontendConfig(BaseModel):
    port: int
    api_base_url: str
    ws_url: str


# ── Root config ───────────────────────────────────────────────────────────────

class AppConfig(BaseModel):
    infrastructure: InfrastructureConfig
    ssh: SshConfig
    vpn: VpnConfig
    network_conditions: dict[str, NetworkConditionPreset]
    tests: TestsConfig
    scoring: ScoringConfig
    backend: BackendConfig
    frontend: FrontendConfig

    @model_validator(mode="before")
    @classmethod
    def apply_env_overrides(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Override config.yaml fields with environment variables when present."""
        env_overrides: dict[str, Any] = {}

        if host := os.getenv("VM1_HOST"):
            env_overrides.setdefault("infrastructure", {})
            env_overrides["infrastructure"].setdefault("vm1", {})["host"] = host
        if host := os.getenv("VM2_HOST"):
            env_overrides.setdefault("infrastructure", {})
            env_overrides["infrastructure"].setdefault("vm2", {})["host"] = host
        if host := os.getenv("VM3_HOST"):
            env_overrides.setdefault("infrastructure", {})
            env_overrides["infrastructure"].setdefault("vm3", {})["host"] = host
        if key := os.getenv("VM1_SSH_KEY_PATH"):
            env_overrides.setdefault("infrastructure", {})
            env_overrides["infrastructure"].setdefault("vm1", {})["ssh_key_path"] = key
        if key := os.getenv("VM2_SSH_KEY_PATH"):
            env_overrides.setdefault("infrastructure", {})
            env_overrides["infrastructure"].setdefault("vm2", {})["ssh_key_path"] = key
        if key := os.getenv("VM3_SSH_KEY_PATH"):
            env_overrides.setdefault("infrastructure", {})
            env_overrides["infrastructure"].setdefault("vm3", {})["ssh_key_path"] = key
        if log_level := os.getenv("LOG_LEVEL"):
            env_overrides.setdefault("backend", {})["log_level"] = log_level
        if port := os.getenv("BACKEND_PORT"):
            env_overrides.setdefault("backend", {})["port"] = int(port)

        for section, overrides in env_overrides.items():
            if section in data and isinstance(data[section], dict):
                for k, v in overrides.items():
                    if isinstance(v, dict) and isinstance(data[section].get(k), dict):
                        data[section][k].update(v)
                    else:
                        data[section][k] = v
            else:
                data[section] = overrides

        return data


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    config_path = Path(os.getenv("CONFIG_PATH", "config.yaml"))
    if not config_path.is_absolute():
        # Resolve relative to project root (two levels up from this file)
        project_root = Path(__file__).parent.parent.parent
        config_path = project_root / config_path

    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    return AppConfig.model_validate(raw)
