/**
 * HTTP API client — thin wrappers over fetch.
 * Base URL comes from env vars — no hardcoded values.
 */

import type { ClientVm, NetworkCondition, PresetsMap, VpnProtocol } from "@/types";

const BASE = import.meta.env.VITE_API_BASE_URL as string ?? "http://localhost:8000";

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`HTTP ${res.status}: ${body}`);
  }

  return res.json() as Promise<T>;
}

export interface StartTestPayload {
  condition: NetworkCondition;
  protocol: VpnProtocol;
  client_vm?: ClientVm;
}

export interface StartTestResponse {
  message: string;
  protocol: string;
  condition: string;
}

export interface StopTestResponse {
  message: string;
}

export interface TestStatusResponse {
  running: boolean;
  phase: string;
  protocol: string | null;
  condition: string | null;
}

export interface VmSettings {
  host: string;
  port: number;
  user: string;
  ssh_key_path: string;
  ssh_password?: string;
  use_password_auth: boolean;
}

export interface InfrastructureSettings {
  vm1: VmSettings;
  vm2: VmSettings;
  vm3?: VmSettings | null;
  configured: boolean;
}

export interface ConnectivityResult {
  vm: string;
  success: boolean;
  message: string;
  latency_ms: number | null;
}

export interface AutoRepairItem {
  vm: string;
  protocol: string;
  check: string;
  ok: boolean;
  message: string;
  fixed: boolean;
}

export interface AutoRepairReport {
  apply_fixes: boolean;
  summary: {
    total: number;
    ok: number;
    failed: number;
    fixed: number;
  };
  items: AutoRepairItem[];
}

export const api = {
  startTest: (payload: StartTestPayload): Promise<StartTestResponse> =>
    request("/api/test/start", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  stopTest: (): Promise<StopTestResponse> =>
    request("/api/test/stop", {
      method: "POST",
      body: JSON.stringify({ reason: "user_requested" }),
    }),

  getStatus: (): Promise<TestStatusResponse> =>
    request("/api/test/status"),

  getPresets: (): Promise<PresetsMap> =>
    request("/api/presets"),

  health: (): Promise<{ status: string; version: string }> =>
    request("/health"),

  // ── Infrastructure config ──────────────────────────────────────────────────
  getConfig: (): Promise<InfrastructureSettings> =>
    request("/api/config"),

  saveConfig: (payload: { vm1: VmSettings; vm2: VmSettings; vm3?: VmSettings | null }): Promise<InfrastructureSettings> =>
    request("/api/config", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  testConnectivity: (): Promise<ConnectivityResult[]> =>
    request("/api/config/test-connectivity", { method: "POST" }),

  autoRepair: (applyFixes: boolean): Promise<AutoRepairReport> =>
    request("/api/config/auto-repair", {
      method: "POST",
      body: JSON.stringify({ apply_fixes: applyFixes }),
    }),
};
