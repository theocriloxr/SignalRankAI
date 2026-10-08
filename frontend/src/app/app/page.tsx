import type { Metadata } from "next";
import { AppShell } from "../../components/AppShell";
import { WorkspaceLive } from "../../components/WorkspaceLive";
import { PasswordRecovery } from "../../components/PasswordRecovery";
import { AccountEmailLink } from "../../components/AccountEmailLink";

export const metadata: Metadata = { robots: { index: false, follow: false } };

export default async function AppOverview({ searchParams }: { searchParams: Promise<{ password_reset?: string; verify_email?: string; magic_login?: string }> }) {
  const { password_reset, verify_email, magic_login } = await searchParams;
  if (typeof verify_email === "string" && verify_email.length >= 20 && verify_email.length <= 512) {
    return <AccountEmailLink kind="verify" token={verify_email}/>;
  }
  if (typeof magic_login === "string" && magic_login.length >= 20 && magic_login.length <= 512) {
    return <AccountEmailLink kind="magic" token={magic_login}/>;
  }
  // The existing canonical backend emails reset links to /app?password_reset=TOKEN.
  // Show only the recovery flow, never a workspace or account balance before login.
  if (typeof password_reset === "string" && password_reset.length >= 16 && password_reset.length <= 512) {
    return <PasswordRecovery initialToken={password_reset}/>;
  }
  return <AppShell active="Overview"><WorkspaceLive section="overview" /></AppShell>;
}
