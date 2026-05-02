// ── Enums ─────────────────────────────────────────────────────────────────────

export type VpnProtocol =
  | "wireguard"
  | "openvpn_udp"
  | "openvpn_tcp"
  | "ipsec"
  | "all";

export type NetworkCondition =
  | "real_time"
  | "home_network"
  | "airplane_wifi"
  | "industrial_iot"
  | "mobile_4g"
  | "stress_dos";

export type TestPhase =
  | "idle"
  | "applying_condition"
  | "starting_vpn_server"
  | "connecting_client"
  | "verifying_tunnel"
  | "running_latency"
  | "running_throughput"
  | "collecting_cpu"
  | "calculating_score"
  | "cleaning_up"
  | "complete"
  | "error";

// ── WebSocket Message Types ────────────────────────────────────────────────────

export interface WsStatusMessage {
  type: "status";
  phase: string;
  message: string;
}

export interface WsLatencyMessage {
  type: "latency";
  protocol: string;
  timestamp: number;
  value_ms: number;
}

export interface WsThroughputMessage {
  type: "throughput";
  protocol: string;
  timestamp: number;
  upload_mbps: number;
  download_mbps: number;
}

export interface WsCpuMessage {
  type: "cpu";
  host: string;
  timestamp: number;
  usage_percent: number;
}

export interface WsResultFinal {
  type: "result_final";
  protocol: string;
  condition: string;
  avg_latency_ms: number;
  max_latency_ms: number;
  avg_throughput_mbps: number;
  avg_cpu_percent: number;
  score: number;
  recommended: boolean;
}

export interface WsErrorMessage {
  type: "error";
  phase: string;
  message: string;
  retry: boolean;
}

export interface WsProgressMessage {
  type: "progress";
  percent: number;
  label: string;
}

export interface WsHeartbeat {
  type: "heartbeat";
}

export type WsMessage =
  | WsStatusMessage
  | WsLatencyMessage
  | WsThroughputMessage
  | WsCpuMessage
  | WsResultFinal
  | WsErrorMessage
  | WsProgressMessage
  | WsHeartbeat;

// ── Chart Data Points ──────────────────────────────────────────────────────────

export interface LatencyDataPoint {
  timestamp: number;
  [protocol: string]: number;
}

export interface ThroughputDataPoint {
  timestamp: number;
  upload: number;
  download: number;
  protocol: string;
}

// ── Phase Log Entry ────────────────────────────────────────────────────────────

export type LogStatus = "success" | "pending" | "error";

export interface PhaseLogEntry {
  id: string;
  timestamp: number;
  message: string;
  phase: string;
  status: LogStatus;
}

// ── Network Condition Preset ───────────────────────────────────────────────────

export interface NetworkConditionPreset {
  label: string;
  emoji: string;
  delay_ms: number;
  jitter_ms: number;
  loss_percent: number;
  rate_mbit: number;
  hping3_flood: boolean;
}

export type PresetsMap = Record<NetworkCondition, NetworkConditionPreset>;

// ── Protocol display meta ──────────────────────────────────────────────────────

export interface ProtocolMeta {
  key: VpnProtocol;
  label: string;
  color: string;
  description: string;
}

// ── Summary table row ──────────────────────────────────────────────────────────

export interface SummaryRow {
  run_id: number;
  recorded_at: number;
  protocol: string;
  condition: string;
  avg_latency_ms: number;
  max_latency_ms: number;
  avg_throughput_mbps: number;
  avg_cpu_percent: number;
  score: number;
  recommended: boolean;
}
