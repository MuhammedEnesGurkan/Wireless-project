import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useStore } from "@/store";
import type { PhaseLogEntry } from "@/types";

function logIcon(status: PhaseLogEntry["status"]): string {
  switch (status) {
    case "success": return "✅";
    case "error":   return "❌";
    case "pending": return "⏳";
  }
}

function logColor(status: PhaseLogEntry["status"]): string {
  switch (status) {
    case "success": return "text-vpn-green";
    case "error":   return "text-red-400";
    case "pending": return "text-slate-400";
  }
}

export function PhaseLog() {
  const phaseLog = useStore((s) => s.phaseLog);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [phaseLog.length]);

  return (
    <div className="space-y-1">
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
        Phase Log
      </p>
      <div className="h-44 overflow-y-auto rounded-lg border border-vpn-border bg-black/10 dark:bg-black/30 p-2 scrollbar-thin">
        <AnimatePresence initial={false}>
          {phaseLog.map((entry) => (
            <motion.div
              key={entry.id}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className={`flex items-start gap-2 py-0.5 font-mono text-[10px] leading-relaxed ${logColor(entry.status)}`}
            >
              <span className="shrink-0 select-none">{logIcon(entry.status)}</span>
              <span className="break-all">{entry.message}</span>
            </motion.div>
          ))}
        </AnimatePresence>
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
