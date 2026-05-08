import { AnimatePresence, motion } from "framer-motion";
import { Trophy } from "lucide-react";
import { useStore } from "@/store";
import { PROTOCOL_META, CONDITION_LABELS, fmtMs, fmtMbps, fmtPercent } from "@/lib/utils";
import type { NetworkCondition } from "@/types";

export function RecommendationBanner() {
  const recommendation = useStore((s) => s.recommendation);

  return (
    <AnimatePresence>
      {recommendation && (
        <motion.div
          key="recommendation"
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 24 }}
          transition={{ type: "spring", stiffness: 260, damping: 22 }}
          className="mt-3"
        >
          <div
            className="flex items-center gap-4 rounded-xl border px-5 py-3"
            style={{
              borderColor: PROTOCOL_META[recommendation.protocol]?.color ?? "#22c55e",
              background: `${PROTOCOL_META[recommendation.protocol]?.color ?? "#22c55e"}18`,
            }}
          >
            <Trophy
              className="h-6 w-6 shrink-0"
              style={{ color: PROTOCOL_META[recommendation.protocol]?.color ?? "#22c55e" }}
            />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-slate-100 leading-none mb-1">
                Best for{" "}
                {CONDITION_LABELS[recommendation.condition as NetworkCondition] ??
                  recommendation.condition}
                :{" "}
                <span style={{ color: PROTOCOL_META[recommendation.protocol]?.color ?? "#22c55e" }}>
                  {PROTOCOL_META[recommendation.protocol]?.label ?? recommendation.protocol}
                </span>
              </p>
              <p className="text-xs text-slate-400 font-mono">
                {fmtMs(recommendation.avg_latency_ms)} avg latency ·{" "}
                {fmtMbps(recommendation.avg_throughput_mbps)} ·{" "}
                CPU {fmtPercent(recommendation.avg_cpu_percent)} ·{" "}
                DPI {recommendation.dpi_resistance_score.toFixed(1)} ·{" "}
                Score{" "}
                <span className="text-vpn-green font-semibold">
                  {recommendation.score.toFixed(1)}
                </span>
              </p>
            </div>
            <div className="text-right">
              <span
                className="text-2xl font-bold font-mono"
                style={{ color: PROTOCOL_META[recommendation.protocol]?.color ?? "#22c55e" }}
              >
                {recommendation.score.toFixed(0)}
              </span>
              <p className="text-[10px] text-slate-500">score</p>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
