import type React from "react";
import { Activity, ArrowDown, ArrowUp, Gauge, Radio } from "lucide-react";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useStore } from "@/store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fmtMbps, fmtMs, PROTOCOL_META, scoreColor } from "@/lib/utils";

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function gaugePercent(mbps: number) {
  // Log-ish scale so VM3's low Mbps still moves the needle, while fast VM2
  // links do not instantly pin the gauge.
  const max = 100;
  return clamp((Math.log10(mbps + 1) / Math.log10(max + 1)) * 100, 0, 100);
}

function polarToCartesian(cx: number, cy: number, r: number, angle: number) {
  const radians = ((angle - 180) * Math.PI) / 180;
  return {
    x: cx + r * Math.cos(radians),
    y: cy + r * Math.sin(radians),
  };
}

function arcPath(cx: number, cy: number, r: number, startAngle: number, endAngle: number) {
  const start = polarToCartesian(cx, cy, r, endAngle);
  const end = polarToCartesian(cx, cy, r, startAngle);
  const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArcFlag} 0 ${end.x} ${end.y}`;
}

function SpeedGauge({
  value,
  label,
  color,
}: {
  value: number;
  label: string;
  color: string;
}) {
  const percent = gaugePercent(value);
  const angle = 180 * (percent / 100);
  const needle = polarToCartesian(100, 102, 62, angle);

  return (
    <div className="relative flex min-h-[190px] flex-col items-center justify-end overflow-hidden">
      <svg viewBox="0 0 200 126" className="absolute inset-x-0 top-0 h-[150px] w-full">
        <path
          d={arcPath(100, 102, 76, 0, 180)}
          fill="none"
          stroke="rgba(148,163,184,0.18)"
          strokeWidth="16"
          strokeLinecap="round"
        />
        <path
          d={arcPath(100, 102, 76, 0, angle)}
          fill="none"
          stroke={color}
          strokeWidth="16"
          strokeLinecap="round"
        />
        <line
          x1="100"
          y1="102"
          x2={needle.x}
          y2={needle.y}
          stroke="rgb(226,232,240)"
          strokeWidth="3"
          strokeLinecap="round"
        />
        <circle cx="100" cy="102" r="7" fill={color} />
        {[0, 25, 50, 75, 100].map((tick) => {
          const p = polarToCartesian(100, 102, 88, 180 * (tick / 100));
          return (
            <text
              key={tick}
              x={p.x}
              y={p.y}
              textAnchor="middle"
              dominantBaseline="middle"
              className="fill-slate-500 text-[9px]"
            >
              {tick === 100 ? "100+" : tick}
            </text>
          );
        })}
      </svg>

      <div className="relative z-10 text-center">
        <p className="text-[10px] uppercase text-muted-foreground">{label}</p>
        <p className="font-mono text-4xl font-bold text-foreground">
          {value.toFixed(value >= 10 ? 1 : 2)}
        </p>
        <p className="text-[11px] text-muted-foreground">Mbps</p>
      </div>
    </div>
  );
}

function MetricTile({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-vpn-border bg-black/20 px-3 py-2">
      <div className="text-slate-400">{icon}</div>
      <div className="min-w-0">
        <p className="text-[10px] text-muted-foreground">{label}</p>
        <p className="truncate font-mono text-sm font-semibold text-slate-100">{value}</p>
      </div>
    </div>
  );
}

export function SpeedTestPanel() {
  const throughputPoints = useStore((s) => s.throughputPoints);
  const latencyPoints = useStore((s) => s.latencyPoints);
  const recommendation = useStore((s) => s.recommendation);
  const running = useStore((s) => s.running);
  const phase = useStore((s) => s.phase);

  const latestThroughput = throughputPoints.at(-1);
  const latestLatencyPoint = latencyPoints.at(-1);
  const latestProtocol = latestThroughput?.protocol ?? recommendation?.protocol ?? "";
  const meta = PROTOCOL_META[latestProtocol] ?? PROTOCOL_META.all;
  const upload = latestThroughput?.upload ?? 0;
  const download = latestThroughput?.download ?? 0;
  const latency =
    latestLatencyPoint && latestProtocol && typeof latestLatencyPoint[latestProtocol] === "number"
      ? latestLatencyPoint[latestProtocol]
      : recommendation?.avg_latency_ms ?? 0;
  const score = recommendation?.score ?? 0;
  const isTesting = running && phase !== "idle";

  const miniData = throughputPoints.slice(-12).map((point) => ({
    timestamp: point.timestamp,
    upload: point.upload,
    download: point.download,
  }));

  return (
    <Card className="flex h-full flex-col overflow-hidden">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Gauge className="h-4 w-4 text-vpn-green" />
              VPN SPEED TEST BY GROUP 8
            </CardTitle>
            <p className="text-[10px] text-muted-foreground">
              {latestProtocol ? meta.label : "Waiting for throughput data"}
            </p>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-vpn-border bg-black/20 px-3 py-1">
            <span
              className={`h-2 w-2 rounded-full ${isTesting ? "animate-pulse" : ""}`}
              style={{ backgroundColor: meta.color }}
            />
            <span className="text-[10px] uppercase text-muted-foreground">
              {isTesting ? "testing" : latestProtocol ? "last run" : "idle"}
            </span>
          </div>
        </div>
      </CardHeader>

      <CardContent className="flex min-h-0 flex-1 flex-col gap-3 pb-3">
        <div className="grid min-h-[205px] grid-cols-2 gap-3">
          <div className="rounded-lg border border-vpn-border bg-black/20 px-2">
            <SpeedGauge value={download} label="Download" color={meta.color} />
          </div>
          <div className="rounded-lg border border-vpn-border bg-black/20 px-2">
            <SpeedGauge value={upload} label="Upload" color="#22c55e" />
          </div>
        </div>

        <div className="grid grid-cols-4 gap-2">
          <MetricTile icon={<Radio className="h-4 w-4" />} label="Ping" value={latency ? fmtMs(latency) : "--"} />
          <MetricTile icon={<ArrowDown className="h-4 w-4" />} label="Down" value={fmtMbps(download)} />
          <MetricTile icon={<ArrowUp className="h-4 w-4" />} label="Up" value={fmtMbps(upload)} />
          <MetricTile
            icon={<Activity className="h-4 w-4" />}
            label="Score"
            value={score ? score.toFixed(1) : "--"}
          />
        </div>

        <div className="min-h-0 flex-1 rounded-lg border border-vpn-border bg-black/20 px-2 py-2">
          {miniData.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              Start a throughput test to fill the gauge
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={miniData} margin={{ top: 4, right: 8, left: -24, bottom: 0 }}>
                <XAxis dataKey="timestamp" hide />
                <YAxis hide domain={[0, "dataMax + 5"]} />
                <Tooltip
                  contentStyle={{
                    background: "var(--vpn-card)",
                    border: "1px solid var(--vpn-border)",
                    borderRadius: 8,
                    color: "rgb(226,232,240)",
                    fontSize: 12,
                  }}
                  formatter={(value: number, name: string) => [
                    `${Number(value).toFixed(2)} Mbps`,
                    name === "download" ? "Download" : "Upload",
                  ]}
                />
                <Line type="monotone" dataKey="download" stroke={meta.color} strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="upload" stroke="#22c55e" strokeWidth={2} strokeDasharray="4 3" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        {score > 0 && (
          <div className="flex items-center justify-between rounded-lg border border-vpn-border bg-black/20 px-3 py-2">
            <span className="text-xs text-muted-foreground">Overall benchmark score</span>
            <span className={`font-mono text-lg font-bold ${scoreColor(score)}`}>{score.toFixed(1)}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
