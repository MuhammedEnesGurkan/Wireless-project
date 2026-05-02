import {
  AreaChart,
  Area,
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
  label?: number;
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-vpn-border bg-vpn-card text-foreground px-3 py-2 text-xs shadow-xl">
      <p className="mb-1 text-muted-foreground">{label ? new Date(label * 1000).toLocaleTimeString() : ""}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }}>
          {PROTOCOL_META[p.name]?.label ?? p.name}: {p.value.toFixed(1)} ms
        </p>
      ))}
    </div>
  );
}

export function LatencyChart() {
  const latencyPoints = useStore((s) => s.latencyPoints);

  // Derive which protocols have data
  const activeProtocols = new Set<string>();
  for (const pt of latencyPoints) {
    for (const key of Object.keys(pt)) {
      if (key !== "timestamp") activeProtocols.add(key);
    }
  }

  const isEmpty = latencyPoints.length === 0;

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="pb-2">
        <CardTitle>Latency (ms)</CardTitle>
        <p className="text-[10px] text-muted-foreground">Live ping RTT — last 60 s</p>
      </CardHeader>
      <CardContent className="flex-1 pb-2">
        {isEmpty ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            No data yet — start a test
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={latencyPoints} margin={{ top: 4, right: 12, left: -16, bottom: 0 }}>
              <defs>
                {Array.from(activeProtocols).map((proto) => {
                  const color = PROTOCOL_META[proto]?.color ?? "#94a3b8";
                  return (
                    <linearGradient key={proto} id={`grad-${proto}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor={color} stopOpacity={0.35} />
                      <stop offset="95%" stopColor={color} stopOpacity={0.02} />
                    </linearGradient>
                  );
                })}
              </defs>
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
                unit=" ms"
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend
                formatter={(value: string) => (
                  <span style={{ color: PROTOCOL_META[value]?.color ?? "#94a3b8", fontSize: 11 }}>
                    {PROTOCOL_META[value]?.label ?? value}
                  </span>
                )}
              />
              {Array.from(activeProtocols).map((proto) => {
                const color = PROTOCOL_META[proto]?.color ?? "#94a3b8";
                return (
                  <Area
                    key={proto}
                    type="monotone"
                    dataKey={proto}
                    stroke={color}
                    strokeWidth={2}
                    fill={`url(#grad-${proto})`}
                    dot={false}
                    activeDot={{ r: 4 }}
                    connectNulls
                  />
                );
              })}
            </AreaChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
