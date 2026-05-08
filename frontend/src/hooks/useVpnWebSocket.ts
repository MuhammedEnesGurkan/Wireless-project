/**
 * useVpnWebSocket — wraps native WebSocket with:
 *   - auto-reconnect (3 attempts, exponential back-off)
 *   - heartbeat ping every 15 s
 *   - typed message dispatch into Zustand store
 *
 * React StrictMode safe: connection is kept in a module-level singleton
 * so the double-mount in development doesn't create duplicate sockets.
 */

import { useEffect, useRef } from "react";
import type { WsMessage } from "@/types";
import { useStore } from "@/store";

const WS_URL: string = (import.meta.env.VITE_WS_URL as string | undefined) ?? "ws://localhost:8000/ws/test";
const MAX_RECONNECT_ATTEMPTS = 3;
const HEARTBEAT_MS = 15_000;
const BASE_RECONNECT_DELAY_MS = 2_000;

// ── Module-level singleton so StrictMode double-mount is harmless ─────────────
let _ws: WebSocket | null = null;
let _heartbeatTimer: ReturnType<typeof setInterval> | null = null;
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let _reconnectAttempts = 0;
let _mountCount = 0;          // track how many hook instances are mounted

function clearHeartbeat() {
  if (_heartbeatTimer) { clearInterval(_heartbeatTimer); _heartbeatTimer = null; }
}
function clearReconnect() {
  if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
}

function startHeartbeat(ws: WebSocket) {
  clearHeartbeat();
  _heartbeatTimer = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ping" }));
    }
  }, HEARTBEAT_MS);
}

// Grab store actions once (stable references, no re-render needed)
function getActions() {
  return useStore.getState();
}

function connect() {
  if (_ws && (_ws.readyState === WebSocket.CONNECTING || _ws.readyState === WebSocket.OPEN)) {
    return; // Already connected or connecting
  }

  const ws = new WebSocket(WS_URL);
  _ws = ws;

  ws.onopen = () => {
    _reconnectAttempts = 0;
    getActions().setWsConnected(true);
    getActions().appendLog({
      message: "🔌 Connected to backend",
      phase: "idle",
      status: "success",
    });
    startHeartbeat(ws);

    // Sync state from backend on (re)connect — fixes stale "Running..." UI
    fetch(`${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"}/api/test/status`)
      .then((r) => r.json())
      .then((status: { running: boolean; phase: string }) => {
        if (!status.running) {
          getActions().setRunning(false);
          getActions().setPhase("idle");
        }
      })
      .catch(() => { /* ignore — WS message will handle it */ });
  };

  ws.onmessage = (ev: MessageEvent<string>) => {
    try {
      dispatch(JSON.parse(ev.data) as WsMessage);
    } catch {
      // Ignore unparseable frames
    }
  };

  ws.onclose = (ev) => {
    clearHeartbeat();
    getActions().setWsConnected(false);

    // If UI thinks test is running, verify with backend immediately
    if (getActions().running) {
      fetch(`${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"}/api/test/status`)
        .then((r) => r.json())
        .then((status: { running: boolean; phase: string }) => {
          if (!status.running) {
            getActions().setRunning(false);
            getActions().setPhase("idle");
            getActions().appendLog({
              message: "⚠️ Bağlantı koptu — test zaten tamamlandı veya hata ile sonuçlandı.",
              phase: "error",
              status: "error",
            });
          }
        })
        .catch(() => { /* backend unreachable, keep UI as-is */ });
    }

    // Normal closure (code 1000) or no active mounts — don't reconnect
    if (ev.code === 1000 || _mountCount === 0) return;

    if (_reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
      const delay = BASE_RECONNECT_DELAY_MS * Math.pow(2, _reconnectAttempts);
      _reconnectAttempts += 1;
      getActions().appendLog({
        message: `⚠️ Disconnected — reconnecting in ${delay / 1000}s (${_reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})…`,
        phase: "idle",
        status: "pending",
      });
      clearReconnect();
      _reconnectTimer = setTimeout(connect, delay);
    } else {
      getActions().appendLog({
        message: "❌ Could not reconnect to backend. Refresh the page to retry.",
        phase: "error",
        status: "error",
      });
    }
  };

  ws.onerror = () => {
    // onclose fires right after with the actual code
  };
}

function disconnect() {
  clearHeartbeat();
  clearReconnect();
  if (_ws) {
    _ws.close(1000, "component unmounted");
    _ws = null;
  }
}

function dispatch(msg: WsMessage) {
  const a = getActions();
  switch (msg.type) {
    case "status": {
      const phaseMap: Record<string, string> = {
        applying_condition:   "applying_condition",
        starting_vpn_server:  "starting_vpn_server",
        connecting_client:    "connecting_client",
        verifying_tunnel:     "verifying_tunnel",
        running_latency:      "running_latency",
        running_throughput:   "running_throughput",
        collecting_cpu:       "collecting_cpu",
        calculating_score:    "calculating_score",
        cleaning_up:          "cleaning_up",
        complete:             "complete",
        starting:             "applying_condition",
        cancelled:            "idle",
        idle:                 "idle",
      };
      a.setPhase((phaseMap[msg.phase] ?? "idle") as Parameters<typeof a.setPhase>[0]);
      if (msg.phase === "complete" || msg.phase === "cancelled") a.setRunning(false);
      a.appendLog({
        message: msg.message,
        phase: msg.phase,
        status: msg.phase === "complete" ? "success" : msg.phase === "error" ? "error" : "pending",
      });
      break;
    }
    case "latency":
      a.addLatency(msg.protocol, msg.timestamp, msg.value_ms);
      break;
    case "throughput":
      a.addThroughput(msg.protocol, msg.timestamp, msg.upload_mbps, msg.download_mbps);
      break;
    case "cpu":
      a.addCpu(msg);
      break;
    case "result_final":
      a.addResult(msg);
      a.appendLog({
        message: `✅ ${msg.protocol}: score=${msg.score} · dpi=${msg.dpi_resistance_score.toFixed(1)} · latency=${msg.avg_latency_ms.toFixed(1)}ms · ${msg.avg_throughput_mbps.toFixed(1)}Mbps`,
        phase: "complete",
        status: "success",
      });
      break;
    case "error":
      a.setPhase("error");
      a.setRunning(false);
      a.appendLog({ message: `❌ ${msg.message}`, phase: msg.phase, status: "error" });
      break;
    case "progress":
      a.setProgress(msg.percent, msg.label);
      break;
    case "heartbeat":
      break;
  }
}

// ── React hook ────────────────────────────────────────────────────────────────

export function useVpnWebSocket(): { disconnect: () => void } {
  const didInit = useRef(false);

  useEffect(() => {
    // StrictMode mounts twice in dev — skip the second phantom mount
    if (didInit.current) return;
    didInit.current = true;

    _mountCount += 1;
    connect();

    return () => {
      _mountCount -= 1;
      // Only fully disconnect when there are truly no more mounted consumers
      if (_mountCount === 0) {
        disconnect();
      }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return { disconnect };
}
