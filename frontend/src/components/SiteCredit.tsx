import Link from "next/link";

export function SiteCredit({compact=false}:{compact?:boolean}) {
  return <div className={"sr-powered-credit"+(compact?" sr-powered-credit-compact":"")}>
    <span>SignalRankAI / Decision intelligence</span>
    <span>Powered by <a href="https://www.criloxsolutions.com" target="_blank" rel="noopener noreferrer"
      aria-label="CRILOX Solutions — opens in a new tab">CRILOX Solutions <span aria-hidden="true">↗</span></a></span>
    <Link href="/risk">Risk disclosure</Link>
  </div>;
}
