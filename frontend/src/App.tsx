import { useEffect } from "react";
import { motion } from "framer-motion";
import { useStore } from "@/store";
import { useVpnWebSocket } from "@/hooks/useVpnWebSocket";
import { api } from "@/services/api";
import { Sidebar } from "@/components/Sidebar";
import { LatencyChart } from "@/components/LatencyChart";
import { SpeedTestPanel } from "@/components/SpeedTestPanel";
import { SummaryTable } from "@/components/SummaryTable";
import { RecommendationBanner } from "@/components/RecommendationBanner";

export default function App() {
  // Mount WebSocket — handles lifecycle automatically
  useVpnWebSocket();

  const setPresets = useStore((s) => s.setPresets);
  const darkMode = useStore((s) => s.darkMode);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
    try { localStorage.setItem("vpn-theme", darkMode ? "dark" : "light"); } catch {}
  }, [darkMode]);

  useEffect(() => {
    api
      .getPresets()
      .then(setPresets)
      .catch(() => {
        // Non-fatal: presets will remain null
      });
  }, [setPresets]);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-vpn-bg transition-colors duration-200">
      {/* Left sidebar */}
      <Sidebar />

      {/* Main dashboard */}
      <main className="flex flex-1 flex-col overflow-hidden">
        {/* Charts row */}
        <div className="flex flex-1 gap-3 p-3 min-h-0">
          <motion.div
            className="flex-1 min-w-0"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
          >
            <LatencyChart />
          </motion.div>

          <motion.div
            className="flex-1 min-w-0"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.1 }}
          >
            <SpeedTestPanel />
          </motion.div>
        </div>

        {/* Bottom row: summary table + recommendation */}
        <motion.div
          className="flex flex-col px-3 pb-3 gap-2"
          style={{ height: "calc(50vh - 1.5rem)" }}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.2 }}
        >
          <div className="flex-1 min-h-0">
            <SummaryTable />
          </div>
          <RecommendationBanner />
        </motion.div>
      </main>
    </div>
  );
}
