import { motion } from "framer-motion";
import { useStore } from "@/store";
import { Badge } from "@/components/ui/badge";
import type { TestPhase } from "@/types";

interface StatusConfig {
  color: string;
  pulseColor: string;
  label: string;
  badgeVariant: "success" | "warning" | "destructive" | "info";
}

const STATUS_CONFIG: Record<string, StatusConfig> = {
  idle: {
    color: "bg-slate-500",
    pulseColor: "bg-slate-500",
    label: "Idle",
    badgeVariant: "info",
  },
  applying_condition: {
    color: "bg-vpn-orange",
    pulseColor: "bg-vpn-orange",
    label: "Applying Condition",
    badgeVariant: "warning",
  },
  starting_vpn_server: {
    color: "bg-vpn-orange",
    pulseColor: "bg-vpn-orange",
    label: "Starting Server",
    badgeVariant: "warning",
  },
  connecting_client: {
    color: "bg-vpn-orange",
    pulseColor: "bg-vpn-orange",
    label: "Connecting Client",
    badgeVariant: "warning",
  },
  verifying_tunnel: {
    color: "bg-vpn-orange",
    pulseColor: "bg-vpn-orange",
    label: "Verifying Tunnel",
    badgeVariant: "warning",
  },
  running_latency: {
    color: "bg-vpn-green",
    pulseColor: "bg-vpn-green",
    label: "Testing Latency",
    badgeVariant: "success",
  },
  running_throughput: {
    color: "bg-vpn-green",
    pulseColor: "bg-vpn-green",
    label: "Testing Throughput",
    badgeVariant: "success",
  },
  collecting_cpu: {
    color: "bg-vpn-green",
    pulseColor: "bg-vpn-green",
    label: "Collecting CPU",
    badgeVariant: "success",
  },
  calculating_score: {
    color: "bg-vpn-blue",
    pulseColor: "bg-vpn-blue",
    label: "Calculating Score",
    badgeVariant: "info",
  },
  cleaning_up: {
    color: "bg-vpn-orange",
    pulseColor: "bg-vpn-orange",
    label: "Cleaning Up",
    badgeVariant: "warning",
  },
  complete: {
    color: "bg-vpn-green",
    pulseColor: "bg-vpn-green",
    label: "Complete ✅",
    badgeVariant: "success",
  },
  error: {
    color: "bg-red-500",
    pulseColor: "bg-red-500",
    label: "Error",
    badgeVariant: "destructive",
  },
};

function getConfig(phase: TestPhase): StatusConfig {
  return STATUS_CONFIG[phase] ?? STATUS_CONFIG.idle;
}

export function StatusIndicator() {
  const phase = useStore((s) => s.phase);
  const wsConnected = useStore((s) => s.wsConnected);
  const cfg = getConfig(phase);
  const isActive = phase !== "idle" && phase !== "complete" && phase !== "error";

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Status</p>
      <div className="flex items-center gap-3">
        {/* Animated pulse dot */}
        <div className="relative flex h-3 w-3 shrink-0">
          {isActive && (
            <motion.span
              className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${cfg.pulseColor}`}
              animate={{ scale: [1, 1.8, 1], opacity: [0.75, 0, 0.75] }}
              transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
            />
          )}
          <span className={`relative inline-flex rounded-full h-3 w-3 ${cfg.color}`} />
        </div>

        <Badge variant={cfg.badgeVariant} className="text-xs">
          {cfg.label}
        </Badge>
      </div>

      {/* WS connection indicator */}
      <div className="flex items-center gap-2 pt-1">
        <span
          className={`h-1.5 w-1.5 rounded-full ${wsConnected ? "bg-vpn-green" : "bg-red-500"}`}
        />
        <span className="text-xs text-muted-foreground">
          {wsConnected ? "WebSocket connected" : "WebSocket disconnected"}
        </span>
      </div>
    </div>
  );
}
