import { useStore } from "@/store";
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

  return (
    <Card className="flex flex-col h-full overflow-hidden">
      <CardHeader className="pb-2 shrink-0">
        <CardTitle>Results Summary</CardTitle>
      </CardHeader>
      <CardContent className="p-0 flex-1 overflow-auto">
        {summaryRows.length === 0 ? (
          <div className="flex h-20 items-center justify-center text-sm text-muted-foreground">
            Results will appear here after each test
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Run</TableHead>
                <TableHead>Protocol</TableHead>
                <TableHead>Condition</TableHead>
                <TableHead>Time</TableHead>
                <TableHead>Avg Latency</TableHead>
                <TableHead>Max Latency</TableHead>
                <TableHead>Throughput</TableHead>
                <TableHead>CPU %</TableHead>
                <TableHead>Score</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {summaryRows.map((row, idx) => {
                const meta = PROTOCOL_META[row.protocol];
                return (
                  <TableRow key={`${row.run_id}-${row.protocol}-${row.condition}-${row.recorded_at}-${idx}`}>
                    <TableCell className="font-mono text-xs text-muted-foreground">#{row.run_id}</TableCell>
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
                      {new Date(row.recorded_at).toLocaleTimeString()}
                    </TableCell>
                    <TableCell>{fmtMs(row.avg_latency_ms)}</TableCell>
                    <TableCell>{fmtMs(row.max_latency_ms)}</TableCell>
                    <TableCell>{fmtMbps(row.avg_throughput_mbps)}</TableCell>
                    <TableCell>{fmtPercent(row.avg_cpu_percent)}</TableCell>
                    <TableCell>
                      <span className={`font-mono font-semibold ${scoreColor(row.score)}`}>
                        {row.score.toFixed(1)}
                      </span>
                    </TableCell>
                    <TableCell>
                      {row.recommended ? (
                        <Badge variant="success">✅ Best</Badge>
                      ) : (
                        <Badge variant="outline" className="text-slate-500 border-vpn-border">
                          —
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
