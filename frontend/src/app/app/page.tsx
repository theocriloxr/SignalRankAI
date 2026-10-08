import type { Metadata } from "next";
import { AppShell } from "../../components/AppShell";
import { WorkspaceLive } from "../../components/WorkspaceLive";
import { PasswordRecovery } from "../../components/PasswordRecovery";

export const metadata: Metadata = { robots: { index: false, follow: false } };

export default async function AppOverview({ searchParams }: { searchParams: Promise<{ password_reset?: string }> }) {
  const { password_reset } = await searchParams;
  // The existing canonical backend emails reset links to /app?password_reset=TOKEN.
  // Show only the recovery flow, never a workspace or account balance before login.
  if (typeof password_reset === "string" && password_reset.length >= 16 && password_reset.length <= 512) {
    return <PasswordRecovery initialToken={password_reset}/>;
  }
  return <AppShell active="Overview"><WorkspaceLive section="overview" /></AppShell>;
}
