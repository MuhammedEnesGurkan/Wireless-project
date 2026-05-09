"""
Pydantic v2 schemas for API requests, WebSocket messages, and internal models.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


# ── Enums ─────────────────────────────────────────────────────────────────────

class VpnProtocol(str, Enum):
    WIREGUARD    = "wireguard"
    OPENVPN_UDP  = "openvpn_udp"
    OPENVPN_TCP  = "openvpn_tcp"
    IPSEC        = "ipsec"
    ALL          = "all"


class NetworkCondition(str, Enum):
    REAL_TIME = "real_time"
    HOME_NETWORK  = "home_network"
    AIRPLANE_WIFI = "airplane_wifi"
    INDUSTRIAL_IOT = "industrial_iot"
    MOBILE_4G     = "mobile_4g"
    STRESS_DOS    = "stress_dos"


class TestPhase(str, Enum):
    IDLE                = "idle"
    APPLYING_CONDITION  = "applying_condition"
    STARTING_VPN_SERVER = "starting_vpn_server"
    CONNECTING_CLIENT   = "connecting_client"
    VERIFYING_TUNNEL    = "verifying_tunnel"
    RUNNING_LATENCY     = "running_latency"
    RUNNING_THROUGHPUT  = "running_throughput"
    COLLECTING_CPU      = "collecting_cpu"
    CALCULATING_SCORE   = "calculating_score"
    CLEANING_UP         = "cleaning_up"
    COMPLETE            = "complete"
    ERROR               = "error"

class ClientVm(str, Enum):
    VM2 = "vm2"
    VM3 = "vm3"


# ── HTTP Request / Response ────────────────────────────────────────────────────

class StartTestRequest(BaseModel):
    condition: NetworkCondition
    protocol: VpnProtocol
    client_vm: ClientVm = ClientVm.VM2

    model_config = {"use_enum_values": True}


class StopTestRequest(BaseModel):
    reason: str = Field(default="user_requested")


class TestStatusResponse(BaseModel):
    running: bool
    phase: TestPhase
    protocol: VpnProtocol | None
    condition: NetworkCondition | None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str


class TestHistoryRecord(BaseModel):
    id: int
    run_id: str
    recorded_at: float
    duration_sec: float | None = None
    client_vm: str
    protocol: str
    condition: str
    status: str
    phase: str | None = None
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    avg_throughput_mbps: float = 0.0
    upload_mbps: float = 0.0
    download_mbps: float = 0.0
    avg_cpu_percent: float = 0.0
    score: float = 0.0
    dpi_resistance_score: float = 0.0
    recommended: bool = False
    error_message: str | None = None


# ── WebSocket Message Types ────────────────────────────────────────────────────

class WsStatusMessage(BaseModel):
    type: Literal["status"] = "status"
    phase: str
    message: str


class WsLatencyMessage(BaseModel):
    type: Literal["latency"] = "latency"
    protocol: str
    timestamp: float
    value_ms: float


class WsThroughputMessage(BaseModel):
    type: Literal["throughput"] = "throughput"
    protocol: str
    timestamp: float
    upload_mbps: float
    download_mbps: float


class WsCpuMessage(BaseModel):
    type: Literal["cpu"] = "cpu"
    host: str
    timestamp: float
    usage_percent: float


class WsResultFinal(BaseModel):
    type: Literal["result_final"] = "result_final"
    protocol: str
    condition: str
    avg_latency_ms: float
    max_latency_ms: float
    avg_throughput_mbps: float
    avg_cpu_percent: float
    score: float
    dpi_resistance_score: float
    recommended: bool


class WsErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    phase: str
    message: str
    retry: bool = False


class WsProgressMessage(BaseModel):
    type: Literal["progress"] = "progress"
    percent: int
    label: str


class WsHeartbeat(BaseModel):
    type: Literal["heartbeat"] = "heartbeat"


# ── Internal Data Models ───────────────────────────────────────────────────────

class LatencySample(BaseModel):
    timestamp: float
    value_ms: float


class ThroughputSample(BaseModel):
    timestamp: float
    upload_mbps: float
    download_mbps: float


class CpuSample(BaseModel):
    host: str
    timestamp: float
    usage_percent: float


class ProtocolTestResult(BaseModel):
    protocol: str
    condition: str
    latency_samples: list[LatencySample] = Field(default_factory=list)
    throughput_samples: list[ThroughputSample] = Field(default_factory=list)
    cpu_samples: list[CpuSample] = Field(default_factory=list)
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    avg_throughput_mbps: float = 0.0
    avg_cpu_percent: float = 0.0
    score: float = 0.0
    dpi_resistance_score: float = 0.0
    recommended: bool = False

    @model_validator(mode="after")
    def compute_aggregates(self) -> "ProtocolTestResult":
        if self.latency_samples:
            vals = [s.value_ms for s in self.latency_samples]
            self.avg_latency_ms = sum(vals) / len(vals)
            self.max_latency_ms = max(vals)
        if self.throughput_samples:
            mbps_vals = [
                (s.upload_mbps + s.download_mbps) / 2
                for s in self.throughput_samples
            ]
            self.avg_throughput_mbps = sum(mbps_vals) / len(mbps_vals)
        if self.cpu_samples:
            cpu_vals = [s.usage_percent for s in self.cpu_samples]
            self.avg_cpu_percent = sum(cpu_vals) / len(cpu_vals)
        return self
