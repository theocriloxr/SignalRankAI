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
      <p className="ui-eyebrow ui-eyebrow--brand">Your private trading workspace</p>
      <h1>See the evidence. <em>Make your next move.</em></h1>
      <p>Bring signal history, research, paper trading and broker connections together in one secure place.</p>
      <ul className="auth-points">
        <li><span><Icon name="lock"/></span>Secure sessions with HttpOnly cookies and CSRF protection</li>
        <li><span><Icon name="key"/></span>Optional authenticator two-step verification</li>
        <li><span><Icon name="telegram"/></span>One account across the web workspace and Telegram</li>
      </ul>
    </div>
    <p className="auth-disclaimer">Trading carries risk. Signals are research, not guarantees, and broker execution requires separate verification.</p>
  </aside>;
}
