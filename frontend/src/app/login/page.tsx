import type { Metadata } from "next";
import { AccountEntry } from "../../components/AccountEntry";

export const metadata: Metadata = {
  title: "Secure sign in",
  description: "Authenticate into the SignalRankAI account-scoped decision workspace.",
  robots: { index: false, follow: false },
};

export default function LoginPage() {
  return <AccountEntry/>;
}
