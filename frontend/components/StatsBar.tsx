// frontend/components/StatsBar.tsx
import { Stats } from "@/lib/api";

interface Props { stats: Stats }

export default function StatsBar({ stats }: Props) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
      {[
        { label: "Total Volume", value: `${stats.total_volume_sats.toLocaleString()} sat` },
        { label: "Fees Earned", value: `${stats.total_fees_sats.toLocaleString()} sat` },
        { label: "Total Calls", value: stats.total_calls.toString() },
        { label: "Wallet Balance", value: `${stats.marketplace_balance_sats.toLocaleString()} sat` },
      ].map(({ label, value }) => (
        <div key={label} className="bg-gray-900 border border-purple-700 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-purple-400">{value}</div>
          <div className="text-sm text-gray-400 mt-1">{label}</div>
        </div>
      ))}
    </div>
  );
}
