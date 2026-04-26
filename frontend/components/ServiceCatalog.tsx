// frontend/components/ServiceCatalog.tsx
import { Service } from "@/lib/api";

interface Props { services: Service[] }

const ICONS: Record<string, string> = {
  "Web Summarizer": "🔍",
  "Code Reviewer": "🧠",
  "Sentiment Analyzer": "📊",
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
                <div className="font-medium text-white">{s.name}</div>
                <div className="text-sm text-gray-400">{s.description}</div>
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
