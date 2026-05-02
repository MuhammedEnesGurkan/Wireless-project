import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { useStore } from "@/store";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { PROTOCOL_META } from "@/lib/utils";

interface TooltipPayloadEntry {
  name: string;
  value: number;
  color: string;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-vpn-border bg-vpn-card text-foreground px-3 py-2 text-xs shadow-xl">
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }}>
          {p.name}: {p.value.toFixed(2)} Mbps
        </p>
      ))}
    </div>
  );
}

export function ThroughputChart() {
  const throughputPoints = useStore((s) => s.throughputPoints);
  const isEmpty = throughputPoints.length === 0;

  // Build chart data: one series per protocol with upload/download
  const chartData = throughputPoints.map((pt) => ({
    timestamp: pt.timestamp,
    [`${pt.protocol}_up`]:   pt.upload,
    [`${pt.protocol}_down`]: pt.download,
    protocol: pt.protocol,
  }));

  const activeProtocols = Array.from(new Set(throughputPoints.map((p) => p.protocol)));

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="pb-2">
        <CardTitle>Throughput (Mbps)</CardTitle>
        <p className="text-[10px] text-muted-foreground">iperf3 upload / download per protocol</p>
      </CardHeader>
      <CardContent className="flex-1 pb-2">
        {isEmpty ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            No data yet — start a test
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 4, right: 12, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--vpn-border)" />
              <XAxis
                dataKey="timestamp"
                tickFormatter={(v: number) => new Date(v * 1000).toLocaleTimeString()}
                tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
                stroke="var(--vpn-border)"
              />
              <YAxis
                tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
                stroke="var(--vpn-border)"
                unit=" M"
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend
                formatter={(value: string) => (
                  <span style={{ fontSize: 11, color: "#94a3b8" }}>{value}</span>
                )}
              />
              {activeProtocols.flatMap((proto) => {
                const color = PROTOCOL_META[proto]?.color ?? "#94a3b8";
                return [
                  <Line
                    key={`${proto}_up`}
                    type="monotone"
                    dataKey={`${proto}_up`}
                    name={`${PROTOCOL_META[proto]?.label ?? proto} ↑`}
                    stroke={color}
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4 }}
                    connectNulls
                  />,
                  <Line
                    key={`${proto}_down`}
                    type="monotone"
                    dataKey={`${proto}_down`}
                    name={`${PROTOCOL_META[proto]?.label ?? proto} ↓`}
                    stroke={color}
                    strokeWidth={2}
                    strokeDasharray="5 3"
                    dot={false}
                    activeDot={{ r: 4 }}
                    connectNulls
                  />,
                ];
              })}
            </LineChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
