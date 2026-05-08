import { useCallback } from "react";
import { Play, Square, Loader2 } from "lucide-react";
import { useStore } from "@/store";
import { api } from "@/services/api";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  PROTOCOL_META,
  PROTOCOL_OPTIONS,
  CONDITION_LABELS,
  CONDITION_OPTIONS,
  conditionBadgeText,
} from "@/lib/utils";
import type { ClientVm, VpnProtocol, NetworkCondition } from "@/types";

export function ControlPanel() {
  const running = useStore((s) => s.running);
  const phase = useStore((s) => s.phase);
  const progress = useStore((s) => s.progress);
  const progressLabel = useStore((s) => s.progressLabel);
  const selectedProtocol = useStore((s) => s.selectedProtocol);
  const selectedCondition = useStore((s) => s.selectedCondition);
  const selectedClientVm = useStore((s) => s.selectedClientVm);
  const presets = useStore((s) => s.presets);
  const setSelectedProtocol = useStore((s) => s.setSelectedProtocol);
  const setSelectedCondition = useStore((s) => s.setSelectedCondition);
  const setSelectedClientVm = useStore((s) => s.setSelectedClientVm);
  const setRunning = useStore((s) => s.setRunning);
  const beginRun = useStore((s) => s.beginRun);
  const clearMetrics = useStore((s) => s.clearMetrics);
  const clearResults = useStore((s) => s.clearResults);
  const clearLog = useStore((s) => s.clearLog);
  const appendLog = useStore((s) => s.appendLog);

  const handleStart = useCallback(async () => {
    clearMetrics();
    clearResults();
    clearLog();
    beginRun();
    setRunning(true);

    appendLog({
      message: `▶ Starting ${PROTOCOL_META[selectedProtocol]?.label} under ${CONDITION_LABELS[selectedCondition]}`,
      phase: "applying_condition",
      status: "pending",
    });

    try {
      await api.startTest({
        condition: selectedCondition,
        protocol: selectedProtocol,
        client_vm: selectedClientVm,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      appendLog({ message: `❌ ${message}`, phase: "error", status: "error" });
      setRunning(false);
    }
  }, [
    selectedProtocol,
    selectedCondition,
    selectedClientVm,
    clearMetrics,
    clearResults,
    clearLog,
    setRunning,
    beginRun,
    appendLog,
  ]);

  const handleStop = useCallback(async () => {
    try {
      await api.stopTest();
      appendLog({ message: "⏹ Stop requested", phase: "idle", status: "pending" });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      appendLog({ message: `❌ Stop failed: ${message}`, phase: "error", status: "error" });
    }
  }, [appendLog]);

  const currentPreset = presets?.[selectedCondition];

  return (
    <div className="space-y-4">
      {/* Network Condition */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          Network Condition
        </label>
        <Select
          value={selectedCondition}
          onValueChange={(v) => setSelectedCondition(v as NetworkCondition)}
          disabled={running}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {CONDITION_OPTIONS.map((key) => (
              <SelectItem key={key} value={key}>
                {CONDITION_LABELS[key]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {currentPreset && (
          <Badge variant="outline" className="text-[10px] text-slate-400 border-vpn-border font-mono">
            {conditionBadgeText(currentPreset)}
          </Badge>
        )}
      </div>

      <Separator />

      {/* Protocol */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          Protocol
        </label>
        <Select
          value={selectedProtocol}
          onValueChange={(v) => setSelectedProtocol(v as VpnProtocol)}
          disabled={running}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PROTOCOL_OPTIONS.map((key) => {
              const meta = PROTOCOL_META[key];
              return (
                <SelectItem key={key} value={key}>
                  <span className="flex items-center gap-2">
                    <span
                      className="inline-block h-2 w-2 rounded-full"
                      style={{ backgroundColor: meta.color }}
                    />
                    {meta.label}
                  </span>
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
        <p className="text-[10px] text-muted-foreground">
          {PROTOCOL_META[selectedProtocol]?.description}
        </p>
      </div>

      <Separator />

      {/* Client/Test VM */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          Test Node (Client)
        </label>
        <Select
          value={selectedClientVm}
          onValueChange={(v) => setSelectedClientVm(v as ClientVm)}
          disabled={running}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="vm2">VM2 — Client / Test Engine</SelectItem>
            <SelectItem value="vm3">VM3 — Client / Test Engine</SelectItem>
          </SelectContent>
        </Select>
        <p className="text-[10px] text-muted-foreground">
          VM3 seçersen, VM3 üzerinde WireGuard/OpenVPN/IPSec client + iperf3 + tc kurulu olmalı.
        </p>
      </div>

      <Separator />

      {/* Action buttons */}
      <div className="space-y-2">
        <Button
          variant="success"
          className="w-full gap-2"
          disabled={running}
          onClick={handleStart}
        >
          {running && phase !== "idle" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          {running ? "Running…" : "Start Test"}
        </Button>

        <Button
          variant="destructive"
          className="w-full gap-2"
          disabled={!running}
          onClick={handleStop}
        >
          <Square className="h-4 w-4" />
          Stop
        </Button>
      </div>

      {/* Progress */}
      {running && (
        <div className="space-y-1">
          <div className="flex justify-between text-[10px] text-muted-foreground">
            <span>{progressLabel}</span>
            <span>{progress}%</span>
          </div>
          <Progress value={progress} />
        </div>
      )}
    </div>
  );
}
