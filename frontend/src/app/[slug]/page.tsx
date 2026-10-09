import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PublicEditorial, type EditorialPage } from "../../components/PublicEditorial";

const pages: Record<string, EditorialPage> = {
  pricing: {
    slug:"pricing", eyebrow:"Plans and entitlements",
    title:"Research access, with every entitlement accounted for.",
    introduction:"Compare the role of plan access, signal eligibility, research tools and simulated execution. Prices and active subscriptions are always retrieved from the canonical billing service rather than being invented on a brochure.",
    emphasis:"PLAN ACCESS ≠ TRADE AUTHORIZATION",
    details:[
      {index:"01",eyebrow:"Entitlements",title:"Your plan defines access, not outcomes.",
       description:"Signal detail, analytics, asset classes and delivery access are governed by the server-side tier policy. Upgrading access does not override a rejected setup or a risk control.",
       points:["Permission checks run on the server, not only in navigation.","Quality thresholds continue to apply even when more instruments are available.","An unavailable or expired subscription cannot be described as active."]},
      {index:"02",eyebrow:"Payments",title:"The account service owns every price and receipt.",
       description:"Checkout pricing, currency, subscription status and payment confirmation must come from the authenticated billing system. A marketing page cannot validate payment by itself.",
       points:["No static prices or discounts are displayed without current verified plan data.","Receipt numbers and charged amounts are read from server-confirmed records.","Provider subscriptions and renewal permissions are independently managed."]},
      {index:"03",eyebrow:"Execution",title:"Broker operation is an independent qualification.",
       description:"A paid plan cannot unlock live-money trading without account, provider, risk, environment and release approval.",
       points:["Paper balances are simulated and must never look like broker funds.","Live permission, portfolio risk and kill-switch state are checked separately.","Available order actions depend on per-account broker certification."]},
    ],
    note:"Pricing, taxes, regional availability and subscription eligibility can change. Sign in to view authoritative offers before making a payment.",
    next:{label:"Security and account controls",href:"/security"}
  },
  methodology: {
    slug:"methodology",eyebrow:"Research methodology",
    title:"An opportunity earns its place in the feed.",
    introduction:"SignalRankAI combines market-data checks, strategy candidates, calibrated model decisions and risk admission. The absence of a trade is a valid result when evidence does not support execution.",
    emphasis:"REJECT WEAK EVIDENCE · PRESERVE STRONG RULES",
    details:[
      {index:"01",eyebrow:"Discovery",title:"Multiple markets, one source of truth.",
       description:"Crypto, foreign exchange, indices, equities and commodities have different venue hours, instrument identities and data-quality requirements.",
       points:["Identify canonical instruments before comparing provider symbols.","Validate freshness, coverage and available trading session.","Fail closed when the quote or venue is ambiguous."]},
      {index:"02",eyebrow:"Decision",title:"Strategy consensus before distribution.",
       description:"Candidates pass defined scoring, strategy, regime, ML calibration and risk gates. A high-looking raw score alone does not certify a signal.",
       points:["Identify strategy and timeframe alongside entry and invalidation levels.","Separate raw probability from calibrated probability.","Record the reasons rejected candidates did not qualify."]},
      {index:"03",eyebrow:"Evidence",title:"Delivery and trade lifecycle stay distinct.",
       description:"Delivered signals can include proof of access, model quality context, market observations and an outcome ledger. These are not interchangeable with broker execution receipts.",
       points:["Track receipt channel and confirmation timestamps.","Label paper fills as simulations, not live fills.","Confirm actual fills, fees and exits with the broker before treating an order as executed."]},
    ],
    note:"No historical backtest, ML probability or previous win rate guarantees a future outcome. Live decision and execution authority are governed by separate safety checks.",
    next:{label:"The risk system",href:"/risk"}
  },
  risk: {
    slug:"risk",eyebrow:"Risk architecture",
    title:"The right decision can be no trade.",
    introduction:"A multi-broker, multi-asset system needs explicit limits across account balance, instrument eligibility, drawdown, exposure, order sizing and venue state. The interface must not claim these checks passed merely because a chart moved.",
    emphasis:"RISK CONTROLS ARE NOT DECORATIVE",
    details:[
      {index:"01",eyebrow:"Market admission",title:"Start with trustworthy market data.",
       description:"Stale prices, uncertified sources and ambiguous instruments prevent a safe risk calculation.",
       points:["Validate canonical symbol, provider and market session.","Require price age and spread tolerances appropriate to the instrument.","Reject unresolvable stop distances or unsupported contract sizes."]},
      {index:"02",eyebrow:"Account admission",title:"Every connected account must qualify separately.",
       description:"A user can have several brokers, but a shared instrument must not silently generate duplicate orders or multiply planned total risk.",
       points:["Identify the explicitly selected account and matching venue.","Respect equity, free margin, leverage, position limits and daily loss controls.","An unknown balance or ambiguous destination is an execution block."]},
      {index:"03",eyebrow:"Execution evidence",title:"Confirm what actually happened.",
       description:"A submitted request, accepted order, partial fill, stop move and closed position are distinct events. Failures and broker disconnects require explicit recovery behavior.",
       points:["Treat kill-switch and user permissions as server-enforced gates.","Record fees, partial exits, rejected orders and breakeven confirmations.","Reconcile any broker response before presenting a realized return."]},
    ],
    note:"Loss of capital is possible. SignalRankAI is research and workflow software, not an assurance of profitable trading. Do not commit live capital on unverified signals or broker integrations.",
    next:{label:"Security and privacy",href:"/security"}
  },
  security: {
    slug:"security",eyebrow:"Security and identity",
    title:"Trust belongs in the architecture, not the headline.",
    introduction:"Account identity, payment confirmation, trading authorizations and credential storage are separate trust boundaries. The web workspace must not bypass backend permission checks or treat a linked broker as an approved trading venue.",
    emphasis:"AUTHORITY IS SERVER-SIDE",
    details:[
      {index:"01",eyebrow:"Identity",title:"One account across supported channels.",
       description:"The account platform is designed to reconcile web and Telegram identities while protecting authenticated access with secure sessions and optional stronger verification.",
       points:["Use HttpOnly session cookies and CSRF protection in the browser.","Complete email verification, recovery and MFA through canonical identity routes.","Revoke or expire sessions when their proof is invalid."]},
      {index:"02",eyebrow:"Broker credentials",title:"Connection is not permission.",
       description:"Sensitive brokerage connections require verification and authorization independent of an ordinary profile view.",
       points:["Avoid withdrawal permissions for trading API connections.","Never expose provider secrets in a rendered page or analytics event.","Require explicit account selection for otherwise ambiguous execution routing."]},
      {index:"03",eyebrow:"Operations",title:"Fail closed when readiness is uncertain.",
       description:"Administrative visibility does not by itself allow configuration changes or remove environment isolation. Runtime and release controls remain separately enforced.",
       points:["Separate staging and production data, credentials and queues.","Preserve kill-switch, rate-limit and recent-auth requirements.","Record code versions and decision provenance for audits."]},
    ],
    note:"The described controls do not assert that any particular deployment has passed a penetration test, audit, broker certification or production-readiness review. Verify that evidence separately.",
    next:{label:"Data provider lineage",href:"/providers"}
  },
  providers: {
    slug:"providers",eyebrow:"Data provenance",
    title:"Every price needs a known source.",
    introduction:"The quality of an investment decision is bounded by the quality of the underlying quotes. Instrument aliases, source delays and missing sessions cannot be papered over with an attractive terminal.",
    emphasis:"NO TRUSTED DATA · NO EXECUTION",
    details:[
      {index:"01",eyebrow:"Instrument registry",title:"Identify the market before the trade.",
       description:"An apparent symbol match can represent different contract types, venues or settlement rules.",
       points:["Resolve a canonical instrument identifier and asset class.","Keep venue, provider symbol and instrument capabilities traceable.","Preserve tick size, quantity step and minimum notional requirements."]},
      {index:"02",eyebrow:"Quality gates",title:"Freshness is contextual.",
       description:"Cryptocurrency trades continuously, while stocks, FX and commodity markets depend on venue and session.",
       points:["Check actual provider timestamps and quote age.","Reject stale, incomplete or unverified market-data classes.","Treat provider fallback as a recorded decision, not silent continuity."]},
      {index:"03",eyebrow:"Broker parity",title:"A common signal is not a common contract.",
       description:"Different brokers may quote, support or prohibit the same instrument differently, so execution cannot be copied blindly.",
       points:["Re-verify contract geometry and available order types per account.","Reject missing certified fills or position reconciliation.","Disclose unavailable coverage rather than invent data."]},
    ],
    note:"Provider support changes with market hours, provider terms, certification and subscription status. The authenticated service and operational evidence are authoritative.",
    next:{label:"Research methodology",href:"/methodology"}
  },
  status: {
    slug:"status",eyebrow:"Operational posture",
    title:"A running service is not a ready market.",
    introduction:"Service health, data readiness, authenticated access and broker order certification are separate signals. An online server cannot certify that financial execution is available.",
    emphasis:"READINESS ≠ UPTIME",
    details:[
      {index:"01",eyebrow:"Runtime",title:"Evaluate the actual deployment.",
       description:"Runtime markers identify which commit and migration is serving traffic. A failed newer deployment can coexist with an older healthy deployment.",
       points:["Check container and endpoint readiness against deployed revision.","Verify Postgres, Redis, queues and worker health independently.","Compare release SHA and expected database migration head."]},
      {index:"02",eyebrow:"Market quality",title:"Coverage matters at market open.",
       description:"An API can be online while the relevant venue is closed, quotes are missing or a required data provider is rate limited.",
       points:["Verify real provider observations for each supported asset class.","Differentiate provider outages from no qualified signals.","Do not manufacture sample statistics as live status."]},
      {index:"03",eyebrow:"Safety",title:"Deployment does not grant trade approval.",
       description:"Separate staging soak, authenticated broker test results, replay recovery and safety audits are needed before promotion.",
       points:["Confirm staged versus production service and data isolation.","Prove demo fills, stop and partial exit reconciliation with the provider.","Require explicit sign-off before any live-financial enablement."]},
    ],
    note:"This page describes how readiness should be evaluated; it is not a live status monitor and does not claim any system is currently operational or certified.",
    next:{label:"Risk architecture",href:"/risk"}
  },
  docs: {
    slug:"docs",eyebrow:"Platform documentation",
    title:"One lifecycle. Every surface accountable.",
    introduction:"Web, Telegram, paper trading, broker integrations and analytics must share canonical accounts and signal identifiers while preserving the trust boundary of every action.",
    emphasis:"SOURCE CODE · CONTRACTS · EVIDENCE",
    details:[
      {index:"01",eyebrow:"Accounts",title:"Authenticate and inspect your rights.",
       description:"The authenticated workspace exposes account-scoped data from the canonical platform API.",
       points:["Use email sign-in, verification, MFA and account recovery.","Review plan entitlements, notification preferences and saved watchlists.","Treat account status and route permissions as server-controlled."]},
      {index:"02",eyebrow:"Research",title:"Explore received signals and evidence.",
       description:"The signal history distinguishes a delivered record, its strategy context, lifecycle tracking and eventual outcomes.",
       points:["Filter delivered signals by asset, class, timeframe and strategy.","Inspect receipt provenance and model context for an entitled signal.","Use paper trading and performance views without confusing them with brokerage results."]},
      {index:"03",eyebrow:"Operations",title:"Review state before acting.",
       description:"Owners have special diagnostic routes, but an operator UI is not automatically a release control.",
       points:["Verify actual running commit, migration, data and queue health.","Keep staging isolated while certifying providers, fills and recovery.","Require audit evidence for release gates, kill-switch behavior and parity."]},
    ],
    note:"Some capabilities are conditional on an account plan, deployed services and independent financial certification. This page documents intended product relationships, not completed deployment acceptance.",
    next:{label:"Account plans",href:"/pricing"}
  },
};

export function generateStaticParams() { return Object.keys(pages).map(slug=>({slug})); }
export async function generateMetadata({params}:{params:Promise<{slug:string}>}):Promise<Metadata>{
  const {slug}=await params;
  const page=pages[slug];
  return page?{title:page.title,description:page.introduction,alternates:{canonical:`/${slug}`}}:{robots:{index:false}};
}
export default async function PublicPage({params}:{params:Promise<{slug:string}>}){
  const {slug}=await params;
  const page=pages[slug];
  if(!page)notFound();
  return <PublicEditorial page={page}/>;
}
