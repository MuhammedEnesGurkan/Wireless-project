import { useEffect, useMemo, useState } from "react";
import { useStore } from "@/store";
import { api, type TestHistoryRecord } from "@/services/api";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from "@/components/ui/table";
import {
  CONDITION_LABELS,
  PROTOCOL_META,
  fmtMs,
  fmtMbps,
  fmtPercent,
  scoreColor,
} from "@/lib/utils";

export function SummaryTable() {
  const summaryRows = useStore((s) => s.summaryRows);
  const [historyRows, setHistoryRows] = useState<TestHistoryRecord[]>([]);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      api
        .getTestHistory(100)
        .then((rows) => {
          if (!cancelled) setHistoryRows(rows);
        })
        .catch(() => {
          if (!cancelled) setHistoryRows([]);
        });
    };
    load();
    const timer = window.setTimeout(load, 900);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [summaryRows.length]);

  const rows = useMemo(() => {
    if (historyRows.length > 0) return historyRows;
    return summaryRows.map((row, idx) => ({
      id: idx,
      run_id: String(row.run_id),
      recorded_at: row.recorded_at / 1000,
      duration_sec: null,
      client_vm: "",
      protocol: row.protocol,
      condition: row.condition,
      status: "success",
      phase: "complete",
      avg_latency_ms: row.avg_latency_ms,
      max_latency_ms: row.max_latency_ms,
      avg_throughput_mbps: row.avg_throughput_mbps,
      upload_mbps: row.upload_mbps ?? 0,
      download_mbps: row.download_mbps ?? 0,
      avg_cpu_percent: row.avg_cpu_percent,
      score: row.score,
      dpi_resistance_score: row.dpi_resistance_score,
      recommended: row.recommended,
      error_message: row.error_message ?? null,
    }));
  }, [historyRows, summaryRows]);

  const bestKeys = useMemo(() => {
    const groups = new Map<string, { id: number; score: number }>();
    for (const row of rows) {
      if (row.status !== "success") continue;
      const key = `${row.client_vm || "live"}:${row.condition}`;
      const current = groups.get(key);
      if (!current || row.score > current.score) {
        groups.set(key, { id: row.id, score: row.score });
      }
    }
    return new Set(
      Array.from(groups.entries()).map(([group, best]) => `${group}:${best.id}`),
    );
  }, [rows]);

  return (
    <Card className="flex flex-col h-full overflow-hidden">
      <CardHeader className="pb-2 shrink-0 flex flex-row items-center justify-between">
        <CardTitle>Results History</CardTitle>
        <span className="text-[10px] text-muted-foreground">
          SQLite · last {rows.length}
        </span>
      </CardHeader>
      <CardContent className="p-0 flex-1 overflow-auto">
        {rows.length === 0 ? (
          <div className="flex h-20 items-center justify-center text-sm text-muted-foreground">
            Results will appear here after each test
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Run</TableHead>
                <TableHead>VM</TableHead>
                <TableHead>Protocol</TableHead>
                <TableHead>Condition</TableHead>
                <TableHead>Time</TableHead>
                <TableHead>Avg Latency</TableHead>
                <TableHead>Max Latency</TableHead>
                <TableHead>Throughput</TableHead>
                <TableHead>CPU %</TableHead>
                <TableHead>Score</TableHead>
                <TableHead>DPI Resistance</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row, idx) => {
                const meta = PROTOCOL_META[row.protocol];
                const isFailed = row.status !== "success";
                const groupKey = `${row.client_vm || "live"}:${row.condition}`;
                const isBest = bestKeys.has(`${groupKey}:${row.id}`);
                return (
                  <TableRow key={`${row.run_id}-${row.protocol}-${row.condition}-${row.recorded_at}-${idx}`}>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {String(row.run_id).slice(-8)}
                    </TableCell>
                    <TableCell className="uppercase text-[10px] text-muted-foreground">
                      {row.client_vm || "live"}
                    </TableCell>
                    <TableCell>
                      <span className="flex items-center gap-2">
                        <span
                          className="inline-block h-2 w-2 rounded-full shrink-0"
                          style={{ backgroundColor: meta?.color ?? "#94a3b8" }}
                        />
                        <span className="text-foreground">{meta?.label ?? row.protocol}</span>
                      </span>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {CONDITION_LABELS[row.condition as keyof typeof CONDITION_LABELS] ?? row.condition}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {new Date(row.recorded_at * 1000).toLocaleTimeString()}
                    </TableCell>
                    <TableCell>{isFailed ? "—" : fmtMs(row.avg_latency_ms)}</TableCell>
                    <TableCell>{isFailed ? "—" : fmtMs(row.max_latency_ms)}</TableCell>
                    <TableCell>{isFailed ? "—" : fmtMbps(row.avg_throughput_mbps)}</TableCell>
                    <TableCell>{isFailed ? "—" : fmtPercent(row.avg_cpu_percent)}</TableCell>
                    <TableCell>
                      <span className={`font-mono font-semibold ${scoreColor(row.score)}`}>
                        {row.score.toFixed(1)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className={`font-mono font-semibold ${scoreColor(row.dpi_resistance_score)}`}>
                        {row.dpi_resistance_score.toFixed(1)}
                      </span>
                    </TableCell>
                    <TableCell>
                      {isFailed ? (
                        <Badge variant="destructive" title={row.error_message ?? undefined}>
                          Failed
                        </Badge>
                      ) : isBest ? (
                        <Badge variant="success">✅ Best</Badge>
                      ) : (
                        <Badge variant="outline" className="text-slate-500 border-vpn-border" title="Saved successful run">
                          OK
                        </Badge>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
