// frontend/components/TransactionFeed.tsx
import { Transaction } from "@/lib/api";

interface Props { transactions: Transaction[] }

function timeAgo(iso: string): string {
  const timestamp = iso.includes("+") || iso.endsWith("Z") ? iso : iso + "Z";
  const diff = Math.floor((Date.now() - new Date(timestamp).getTime()) / 1000);
  if (diff < 0) return "just now";
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

export default function TransactionFeed({ transactions }: Props) {
  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-300 mb-3">Live Payment Feed</h2>
      <div className="bg-gray-900 border border-gray-700 rounded-xl overflow-hidden">
        {transactions.length === 0 && (
          <div className="text-center text-gray-500 py-8">
            No transactions yet. Run the consumer agent to see payments flow.
          </div>
        )}
        {transactions.map((t) => (
          <div
            key={t.id}
            className="px-4 py-3 border-b border-gray-800 last:border-0"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className={t.status === "paid" ? "text-green-400" : "text-yellow-400"}>
                  {t.status === "paid" ? "✓" : "⏳"}
                </span>
                <span className="text-white font-medium">
                  {t.service_name ?? t.service_id.slice(0, 8)}
                </span>
              </div>
              <div className="flex items-center gap-6 text-sm">
                <span className="text-gray-300">{t.amount_sats} sat</span>
                <span className="text-purple-400">fee: {t.fee_sats ?? "—"} sat</span>
                {t.status === "paid" && (
                  t.quality_score !== null ? (
                    <span className="text-green-400 font-mono">{t.quality_score}/100</span>
                  ) : (
                    <span className="text-gray-600 text-xs">scoring…</span>
                  )
                )}
                <span className="text-gray-500">{timeAgo(t.created_at)}</span>
              </div>
            </div>
            {t.score_reason && (
              <div className="text-xs text-gray-500 mt-1 ml-6">{t.score_reason}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
