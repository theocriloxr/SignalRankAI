import type { EditorialPage } from "../components/PublicEditorial";

function page(slug: string, eyebrow: string, title: string, introduction: string,
  sections: [string, string, string[]][], next = "/docs"): EditorialPage {
  return {slug, eyebrow, title, introduction, emphasis: "RESEARCH · REVIEW · DECIDE",
    details: sections.map(([heading, description, points], i) => ({
      index: String(i + 1).padStart(2,"0"), eyebrow: heading, title: heading, description, points,
    })), note:"Trading can result in losses. Features depend on your plan, market coverage and account permissions. Paper activity is simulated; broker execution requires independent verification and authorization.",
    next:{label:next === "/docs" ? "Getting started" : "Explore the platform", href:next}};
}

export const additionalPublicPages: Record<string,EditorialPage> = {
  product: page("product", "The SignalRankAI workspace", "A clearer path from research to a trading decision.",
    "Explore opportunities, inspect their evidence and keep your decisions connected to their outcomes. Your account brings together the web workspace and Telegram delivery.", [
      ["Discover and examine", "Market discovery and your signal feed are distinct views of the opportunity set.", ["Search the instrument directory and save watchlists.", "Filter received signals by market, timeframe and strategy.", "Inspect the evidence and delivery history available to your account."]],
      ["Practice and monitor", "Paper trading provides a separate environment for simulated activity.", ["Review simulated positions, account settings and ledger entries.", "Keep a journal alongside portfolio and performance views.", "Inspect each broker connection and its verification status independently."]],
      ["Make it yours", "Preferences control the experience within the limits of your account.", ["Manage notification channels, quiet hours and alerts.", "Review your subscription and account security.", "Link Telegram once and review its connection status in your profile."]],
    ], "/features"),
  features: page("features", "Capabilities", "Research tools that stay connected to the evidence.",
    "SignalRankAI combines discovery, qualified signals, account tools and outcome tracking. Availability follows your account permissions and the services currently enabled.", [
      ["Market and signal research", "Use the market directory, watchlists, signal filters and authorized evidence views.", ["Instrument identity and provider lineage help explain coverage.", "Signal records retain strategy, timeframe and qualification context.", "Missing or rejected evidence does not become a trading recommendation."]],
      ["Account and execution controls", "Keep simulated activity and verified broker activity separate.", ["Paper settings, positions and history use the server's simulation records.", "Broker readiness and account-specific controls remain visible.", "Connection, execution permission and a confirmed fill are separate states."]],
      ["Review and collaborate", "Follow activity through notifications, journal entries and support.", ["Telegram and web use the same account entitlements.", "Professional integrations require their own permissions.", "Owner diagnostics are restricted to authorized operators."]],
    ], "/markets"),
  markets: page("markets", "Markets and assets", "Different markets deserve different assumptions.",
    "The instrument registry covers crypto, forex, equities, indices and commodities. Registry coverage describes discovery; it does not mean every instrument currently has a qualified feed or an executable broker contract.", [
      ["Explore the directory", "Search by symbol and asset class in your signed-in workspace.", ["Review provider symbols alongside the canonical instrument.", "Save instruments to your own watchlists.", "Respect the distinction between analysis-only and tradable instruments."]],
      ["Check the session and source", "Continuous crypto markets and exchange sessions have different freshness requirements.", ["Venue holidays and closed sessions affect available observations.", "Provider plans may restrict intraday or consolidated coverage.", "A delayed feed cannot substitute for an eligible execution quote."]],
      ["Match the account", "An index, spot asset and derivative can have similar names but different exposure.", ["Verify contract size, quantity steps and account currency.", "Available instruments vary by broker and jurisdiction.", "An unsupported contract remains unavailable for execution."]],
    ], "/providers"),
  strategies: page("strategies", "Strategy research", "Ask what a strategy knows, and when it knew it.",
    "Strategy candidates combine market structure, technical observations and regime context. Research and validation precede qualification; an attractive backtest alone does not authorize a trade.", [
      ["A testable idea", "Record the asset, timeframe, hypothesis and conditions that would invalidate it.", ["Keep entry, stop and target assumptions explicit.", "Separate information available at the decision from future observations.", "Review instrument-specific costs and execution assumptions."]],
      ["Independent evidence", "Research records make experiments and their outcomes inspectable.", ["Preserve failed experiments as well as promising candidates.", "Keep holdout results distinct from optimizer searches.", "Require enough eligible observations before drawing conclusions."]],
      ["Governed progression", "Candidate research, paper behavior and broker acceptance are separate stages.", ["Compare candidates with the current baseline.", "Review drift, calibration and changing regimes.", "A model improvement cannot bypass account or risk controls."]],
    ], "/methodology"),
  ai: page("ai", "AI evaluation", "A probability needs context before it becomes useful.",
    "Models add evidence to a decision alongside data quality, strategy and risk checks. Read their available calibration and provenance rather than interpreting a raw score as a promise.", [
      ["Know the evidence", "A model output depends on its feature definitions and training history.", ["Inspect available model version and evidence timestamps.", "Distinguish raw scores from calibrated probabilities.", "Missing model context must remain visible."]],
      ["Validate the result", "Out-of-sample behavior matters more than an appealing training score.", ["Look for untouched evaluation data and leakage checks.", "Compare performance by asset and market regime.", "Use sufficient outcome evidence to evaluate uncertainty."]],
      ["Keep decisions governed", "AI research does not grant execution permission.", ["Account risk, data admission and kill switches remain independent.", "Experiment history informs review rather than silently changing live rules.", "No model can guarantee future profitability."]],
    ], "/strategies"),
  privacy: page("privacy", "Privacy and account data", "Understand the records behind your workspace.",
    "Your account can hold identity information, preferences, linked channels, research activity and broker connection metadata. Use account and support tools to review access and request help with your information.", [
      ["Account information", "Sign-in, verification and linked channels support access to your account.", ["Review your email and Telegram connection in settings.", "Inspect active sessions and revoke access you no longer recognize.", "Use support for account ownership or data requests."]],
      ["Trading and service records", "Signals, receipts, simulations and journal entries have different purposes.", ["Paper records describe simulations, not a broker balance.", "Broker credentials belong in the secure connection flow.", "Do not share passwords, recovery codes or API secrets in support messages."]],
      ["Your controls", "Choose supported notification channels and review connected services.", ["Update preferences and quiet hours in your account.", "Review permissions before linking a brokerage or integration.", "This product guide is not a claim of regulatory certification or a substitute for applicable service terms."]],
    ], "/security"),
  faq: page("faq", "Frequently asked questions", "Start with the questions that affect your next decision.",
    "Account access, data coverage and trading permissions are independent. These answers explain where to look when a workflow is unavailable.", [
      ["Why have I received no new signals?", "A feed can be quiet when candidates do not pass data, strategy or risk qualification.", ["Check account entitlements and your notification preferences.", "Review connection status for Telegram in settings.", "Contact support if delivery history and your received messages disagree."]],
      ["Does connecting a broker enable trading?", "A connection must be verified and separately authorized before execution is possible.", ["Check the account environment and readiness details.", "Paper activity never proves that a broker order filled.", "Funded and prop accounts retain their individual restrictions."]],
      ["What if Telegram is already linked?", "A linked account should show its existing connection without asking for a new link.", ["Refresh your account status before attempting to reconnect.", "An ownership review must finish before a conflicting identity can be linked.", "Use support if the account status does not match your Telegram profile."]],
    ], "/contact"),
  contact: page("contact", "Contact and support", "Get help with the account and workflow you actually use.",
    "Open a support ticket from your signed-in workspace so the request stays associated with your account. Include the affected page, approximate time and the status or error you saw.", [
      ["Account and access", "Use sign-in and recovery first; account-specific requests belong in support.", ["Describe whether email, Telegram or a broker connection is affected.", "Include the visible error and the steps that led to it.", "Never send a password, OTP, recovery code or broker API secret."]],
      ["Signals and records", "Provide a signal reference or receipt when a delivered record seems incorrect.", ["Say which channel and approximate time were involved.", "Distinguish a signal notification from a paper or broker transaction.", "Use the journal and signal evidence views to review your own records."]],
      ["Service availability", "Check platform status before retrying an unavailable operation.", ["Retry account reads after a temporary connection failure.", "Review a transaction's recorded status before submitting it again.", "Contact your broker directly for broker account, funding or withdrawal assistance."]],
    ], "/status"),
};
