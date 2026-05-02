import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type { VpnProtocol, ProtocolMeta, NetworkCondition, NetworkConditionPreset } from "@/types";

// ── Tailwind class helper ──────────────────────────────────────────────────────

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

// ── Protocol metadata ──────────────────────────────────────────────────────────

export const PROTOCOL_META: Record<string, ProtocolMeta> = {
  wireguard: {
    key: "wireguard",
    label: "WireGuard",
    color: "#22c55e",
    description: "UDP · ChaCha20-Poly1305",
  },
  openvpn_udp: {
    key: "openvpn_udp",
    label: "OpenVPN UDP",
    color: "#3b82f6",
    description: "UDP · AES-256-GCM",
  },
  openvpn_tcp: {
    key: "openvpn_tcp",
    label: "OpenVPN TCP",
    color: "#f97316",
    description: "TCP · AES-256-GCM",
  },
  ipsec: {
    key: "ipsec",
    label: "IPSec/IKEv2",
    color: "#a855f7",
    description: "AES-128 + AES-NI",
  },
  all: {
    key: "all",
    label: "All Protocols",
    color: "#94a3b8",
    description: "Run all sequentially",
  },
};

export const PROTOCOL_OPTIONS: VpnProtocol[] = [
  "wireguard",
  "openvpn_udp",
  "openvpn_tcp",
  "ipsec",
  "all",
];

// ── Network condition metadata ─────────────────────────────────────────────────

export const CONDITION_LABELS: Record<NetworkCondition, string> = {
  real_time:      "🟢 Real Time (No Emulation)",
  home_network:   "🏠 Home Network",
  airplane_wifi:  "✈️ Airplane WiFi",
  industrial_iot: "🏗️ Industrial IoT",
  mobile_4g:      "📱 4G Mobile",
  stress_dos:     "🔥 Stress / DoS",
};

export const CONDITION_OPTIONS: NetworkCondition[] = [
  "real_time",
  "home_network",
  "airplane_wifi",
  "industrial_iot",
  "mobile_4g",
  "stress_dos",
];

// ── Score helpers ──────────────────────────────────────────────────────────────

export function scoreColor(score: number): string {
  if (score >= 70) return "text-vpn-green";
  if (score >= 40) return "text-vpn-orange";
  return "text-red-500";
}

export function scoreBadgeVariant(score: number): "default" | "secondary" | "destructive" {
  if (score >= 70) return "default";
  if (score >= 40) return "secondary";
  return "destructive";
}

// ── Formatting helpers ────────────────────────────────────────────────────────

export function fmtMs(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${ms.toFixed(1)}ms`;
}

export function fmtMbps(mbps: number): string {
  return `${mbps.toFixed(1)} Mbps`;
}

export function fmtPercent(pct: number): string {
  return `${pct.toFixed(1)}%`;
}

export function fmtTimestamp(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString();
}

// ── Phase display ──────────────────────────────────────────────────────────────

export const PHASE_LABELS: Record<string, string> = {
  idle:                "Idle",
  applying_condition:  "Applying Network Condition",
  starting_vpn_server: "Starting VPN Server",
  connecting_client:   "Connecting VPN Client",
  verifying_tunnel:    "Verifying Tunnel",
  running_latency:     "Running Latency Test",
  running_throughput:  "Running Throughput Test",
  collecting_cpu:      "Collecting CPU Metrics",
  calculating_score:   "Calculating Score",
  cleaning_up:         "Cleaning Up",
  complete:            "Complete",
  error:               "Error",
};

// ── Condition params badge text ────────────────────────────────────────────────

export function conditionBadgeText(preset: NetworkConditionPreset): string {
  const parts: string[] = [];
  if (preset.delay_ms > 0) parts.push(`delay:${preset.delay_ms}ms`);
  if (preset.jitter_ms > 0) parts.push(`jitter:±${preset.jitter_ms}ms`);
  if (preset.loss_percent > 0) parts.push(`loss:${preset.loss_percent}%`);
  if (preset.rate_mbit > 0) parts.push(`rate:${preset.rate_mbit}Mbit`);
  return parts.length > 0 ? parts.join(" · ") : "no emulation (live network)";
}

// ── Generate unique IDs ────────────────────────────────────────────────────────

export function generateId(): string {
  return Math.random().toString(36).slice(2, 11);
}
