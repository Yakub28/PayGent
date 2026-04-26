"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/agents", label: "Agents" },
  { href: "/simulation", label: "Simulation" },
];

export default function Nav() {
  const pathname = usePathname();
  return (
    <nav className="border-b border-gray-800 bg-gray-950/90 backdrop-blur sticky top-0 z-10">
      <div className="max-w-5xl mx-auto px-8 py-3 flex items-center gap-6">
        <span className="font-bold text-purple-400">PayGent</span>
        <div className="flex gap-4 text-sm">
          {links.map((l) => {
            const active = pathname === l.href;
            return (
              <Link
                key={l.href}
                href={l.href}
                className={
                  active
                    ? "text-white border-b-2 border-purple-500 pb-2"
                    : "text-gray-400 hover:text-gray-200 pb-2"
                }
              >
                {l.label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
