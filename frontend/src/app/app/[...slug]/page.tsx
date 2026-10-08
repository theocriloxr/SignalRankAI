import { notFound } from "next/navigation";
import { AppShell } from "../../../components/AppShell";
import { WorkspaceLive } from "../../../components/WorkspaceLive";

const sections = new Set([
  "signals", "markets", "research", "watchlists", "alerts",
  "paper", "portfolio", "performance", "journal", "brokers",
  "billing", "support", "settings", "operations",
]);

export default async function WorkspacePage({ params }: { params: Promise<{ slug: string[] }> }) {
  const { slug } = await params;
  const section = String(slug?.[0] || "").toLowerCase();
  const isDetail = section === "signals" && slug.length === 2 && slug[1]?.length <= 64;
  if (!sections.has(section) || (slug.length > 1 && !isDetail)) notFound();
  return (
    <AppShell active={section === "operations" ? "Operations" : section[0].toUpperCase() + section.slice(1)}>
      <WorkspaceLive
        section={section as "signals" | "markets" | "research" | "watchlists" | "alerts" |
          "paper" | "portfolio" | "performance" | "journal" | "brokers" |
          "billing" | "support" | "settings" | "operations"}
        signalId={isDetail ? slug[1] : undefined}
      />
    </AppShell>
  );
}
