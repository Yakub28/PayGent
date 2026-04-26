// frontend/components/ServiceCatalog.tsx
import { Service } from "@/lib/api";

interface Props { services: Service[] }

const ICONS: Record<string, string> = {
  "Web Summarizer": "🔍",
  "Code Reviewer": "🧠",
  "Sentiment Analyzer": "📊",
};

const TIER_STYLES: Record<string, string> = {
  bronze: "bg-amber-900 text-amber-300 border border-amber-700",
  silver: "bg-blue-900 text-blue-300 border border-blue-700",
  gold: "bg-yellow-900 text-yellow-300 border border-yellow-700",
};

export default function ServiceCatalog({ services }: Props) {
  return (
    <div className="mb-8">
      <h2 className="text-lg font-semibold text-gray-300 mb-3">Available Services</h2>
      <div className="space-y-3">
        {services.map((s) => (
          <div
            key={s.id}
            className="flex items-center justify-between bg-gray-900 border border-gray-700 rounded-xl p-4 hover:border-purple-600 transition-colors"
          >
            <div className="flex items-center gap-3">
              <span className="text-2xl">{ICONS[s.name] ?? "⚡"}</span>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-white">{s.name}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${TIER_STYLES[s.tier] ?? TIER_STYLES.bronze}`}>
                    {s.tier.charAt(0).toUpperCase() + s.tier.slice(1)}
                  </span>
                </div>
                {s.is_verified && s.company_name && (
                  <div className="text-xs text-green-600 flex items-center gap-1 mt-0.5">
                    <span>✓</span>
                    <span>{s.company_name}</span>
                  </div>
                )}
                <div className="text-sm text-gray-400">{s.description}</div>
                <div className="flex items-center gap-3 mt-1">
                  {s.avg_quality_score !== null ? (
                    <span className="text-xs text-gray-500">
                      Avg: {Math.round(s.avg_quality_score)}
                    </span>
                  ) : s.call_count > 0 ? (
                    <span className="text-xs text-gray-600 italic">scoring…</span>
                  ) : null}
                  {s.call_count > 0 && (
                    <span className="text-xs text-gray-600">{s.call_count} calls</span>
                  )}
                </div>
              </div>
            </div>
            <div className="text-purple-400 font-mono font-bold whitespace-nowrap ml-4">
              {s.price_sats} sat
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
