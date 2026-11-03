import Link from "next/link";
import Image from "next/image";
import { Icon } from "./ui/Icon";

export function BrandLink() {
  return <Link href="/" className="brand-mark" aria-label="SignalRankAI home">
    <Image src="/brand/icon.svg" alt="" width={30} height={30} unoptimized /><span className="brand-word">SignalRank<span>AI</span></span>
  </Link>;
}

export function AuthAside() {
  return <aside className="auth-aside" aria-label="About your SignalRankAI workspace">
    <BrandLink/>
    <div className="auth-aside-copy">
      <h1>Your signals, your paper account and your record, in one place.</h1>
      <p>Sign in to see every signal you have received, how each one ended, and the setup record behind it.</p>
      <ul className="auth-points">
        <li><span><Icon name="telegram"/></span>The same account works here and on Telegram.</li>
        <li><span><Icon name="key"/></span>You can add an authenticator app for two-step sign-in.</li>
        <li><span><Icon name="lock"/></span>Linking a broker account never places a trade on its own.</li>
      </ul>
    </div>
    <p className="auth-disclaimer">Trading carries risk. Signals are research to inform your own decisions, not guarantees.</p>
  </aside>;
}
