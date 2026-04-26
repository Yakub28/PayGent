// frontend/components/StatsBar.tsx
import { Stats } from "@/lib/api";

interface Props { stats: Stats }

const TIER_TEXT: Record<string, string> = {
  bronze: "text-amber-400",
  silver: "text-blue-400",
  gold: "text-yellow-400",
};

export default function StatsBar({ stats }: Props) {
  const cards = [
    { label: "Total Volume", value: `${stats.total_volume_sats.toLocaleString()} sat` },
    { label: "Fees Earned", value: `${stats.total_fees_sats.toLocaleString()} sat` },
    { label: "Total Calls", value: stats.total_calls.toString() },
    { label: "Wallet Balance", value: `${stats.marketplace_balance_sats.toLocaleString()} sat` },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
      {cards.map(({ label, value }) => (
        <div key={label} className="bg-gray-900 border border-purple-700 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-purple-400">{value}</div>
          <div className="text-sm text-gray-400 mt-1">{label}</div>
        </div>
      ))}
      <div className="bg-gray-900 border border-purple-700 rounded-xl p-4 text-center">
        {stats.top_rated_name ? (
          <>
            <div className={`text-lg font-bold truncate ${TIER_TEXT[stats.top_rated_tier ?? "bronze"] ?? "text-purple-400"}`}>
              {stats.top_rated_name}
            </div>
            <div className="text-sm text-gray-400 mt-1">Top Rated</div>
          </>
        ) : (
          <>
            <div className="text-2xl font-bold text-gray-600">—</div>
            <div className="text-sm text-gray-400 mt-1">Top Rated</div>
          </>
        )}
      </div>
    </div>
  );
}
