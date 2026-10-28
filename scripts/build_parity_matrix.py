"""Generate docs/release/TELEGRAM_WEB_PARITY_MATRIX.md from the code (CX-CHAN-01, CX-TG-01).

Sources: the Telegram command catalogue, the web workspace sections, the routes
each section reads (``WorkspaceLive.tsx``) and every platform API route. Matches
are by name or by an explicit alias below; anything unmatched is listed as a
gap rather than claimed. ``--check`` fails when the committed file is stale.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "release" / "TELEGRAM_WEB_PARITY_MATRIX.md"

# Telegram command -> web workspace section, where the names differ.
COMMAND_SECTION_ALIASES = {
    "signals": "signals", "signal": "signals", "history": "signals", "feedback": "signals",
    "quality": "markets", "markets": "markets", "assets": "markets", "scan": "markets",
    "leaderboard": "research", "strategies": "research", "research": "research",
    "watchlist": "watchlists", "watch": "watchlists", "alerts": "alerts", "notifications": "notifications",
    "paper": "paper", "portfolio": "portfolio", "performance": "performance", "stats": "performance",
    "journal": "journal", "broker": "brokers", "brokers": "brokers", "mt5": "brokers", "bybit": "brokers",
    "billing": "billing", "subscribe": "billing", "upgrade": "billing", "plans": "billing",
    "support": "support", "ticket": "support", "settings": "settings", "account": "settings",
    "privacy": "settings", "security": "settings", "devices": "settings", "timezone": "settings",
    "link": "settings", "apikeys": "settings", "referral": "settings", "referrals": "settings",
    "ops": "operations", "operator": "operations", "release_guard": "operations",
    "account_merges": "operations", "killswitch": "operations", "maintenance": "operations",
    # Names used by the current catalogue.
    "dashboard": "overview", "mission": "overview", "about": "overview", "status": "settings",
    "outcome": "signals", "proof": "signals", "why_no_signal": "signals", "filter": "signals",
    "liveprice": "markets", "market": "markets", "analyze": "markets", "risk": "markets",
    "paper_balance": "paper", "paper_positions": "paper", "paper_history": "paper", "paper_performance": "paper",
    "paper_settings": "paper", "paper_close_all": "paper", "paper_reset": "paper", "simulate": "paper",
    "mystats": "performance", "report": "performance", "notify": "notifications",
    "connect_broker": "brokers", "mt5_link": "brokers", "mt5_status": "brokers", "verifybroker": "brokers",
    "setlot": "brokers", "execution": "brokers", "pricing": "billing", "tiers": "billing", "cancel": "billing",
    "elite": "billing", "early": "billing", "invite": "settings", "referral_leaderboard": "settings",
    "referral_rewards": "settings", "apikey": "settings", "profile": "settings", "setrisk": "settings",
    "language": "settings", "login_code": "settings", "app": "settings", "faq": "support",
    "disclaimer": "support", "kill_switch": "operations", "ops_health": "operations",
    "system_health": "operations", "provider_status": "operations", "queue_status": "operations",
    "engine_debug": "operations", "adaptive_status": "research",
}


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def load() -> tuple[list, list[str], list[tuple[str, str]], dict[str, list[str]]]:
    from signalrank_telegram.command_catalog import COMMANDS

    page = (ROOT / "frontend/src/app/app/[...slug]/page.tsx").read_text(encoding="utf-8")
    sections = re.findall(r'"([a-z]+)"', page[page.index("new Set(["):page.index("]);")])
    sections = ["overview"] + [s for s in sections if s != "overview"]
    api = (ROOT / "web/platform_api.py").read_text(encoding="utf-8")
    routes = sorted(set(re.findall(r'@router\.(get|post|put|patch|delete)\("([^"]+)"', api)), key=lambda r: (r[1], r[0]))
    live = (ROOT / "frontend/src/components/WorkspaceLive.tsx").read_text(encoding="utf-8")
    reads: dict[str, list[str]] = {}
    for section, path in re.findall(r'case "([a-z]+)":[^\n]*?client\.GET\("/api/v1/platform([^"]+)"', live):
        reads.setdefault(section, []).append(path)
    return list(COMMANDS), sections, routes, reads


def command_section(name: str, sections: list[str]) -> str | None:
    if name in COMMAND_SECTION_ALIASES:
        return COMMAND_SECTION_ALIASES[name]
    return next((s for s in sections if _norm(s) == _norm(name) or _norm(s).rstrip("s") == _norm(name)), None)


def route_commands(path: str, commands: list) -> list[str]:
    segments = {_norm(seg) for seg in re.split(r"[/{}]", path) if seg}
    return [c.name for c in commands if _norm(c.name) in segments]


def render() -> str:
    commands, sections, routes, reads = load()
    by_section: dict[str, list[str]] = {}
    for spec in commands:
        section = command_section(spec.name, sections)
        if section:
            by_section.setdefault(section, []).append(spec.name)
    lines = [
        "# Telegram and web parity matrix",
        "",
        "Generated by `python scripts/build_parity_matrix.py` from the command catalogue, the web workspace",
        "sections and `web/platform_api.py`. Matches are by name or an explicit alias in the script; a dash means",
        "no matching path was found, which is a gap to review, not a claim that the feature is missing.",
        "Owner-only mutating controls (kill switches, account merges, maintenance) stay web-only by design:",
        "they need explicit confirmation and a recent sign-in that a chat message cannot provide.",
        "",
        "## Web workspace sections",
        "",
        "| Web section | Reads | Telegram commands |",
        "| --- | --- | --- |",
    ]
    for section in sections:
        cmds = ", ".join(f"`/{c}`" for c in sorted(by_section.get(section, []))) or "—"
        api = ", ".join(f"`{p}`" for p in reads.get(section, [])) or "—"
        lines.append(f"| `/app/{section}` | {api} | {cmds} |")
    lines += ["", "## Telegram commands", "", "| Command | Tier | Area | Web section |", "| --- | --- | --- | --- |"]
    for spec in commands:
        section = command_section(spec.name, sections)
        web = f"`/app/{section}`" if section else "— (Telegram-only)"
        lines.append(f"| `/{spec.name}` | {spec.tier} | {spec.section} | {web} |")
    gaps = 0
    lines += ["", "## Platform API routes", "", "| Method | Route | Telegram commands |", "| --- | --- | --- |"]
    for method, path in routes:
        cmds = route_commands(path, commands)
        gaps += 0 if cmds else 1
        lines.append(f"| {method.upper()} | `{path}` | {', '.join(f'`/{c}`' for c in cmds) or '—'} |")
    unmatched = sum(1 for spec in commands if not command_section(spec.name, sections))
    lines += ["", f"Summary: {len(commands)} commands ({unmatched} without a web section), {len(sections)} web "
              f"sections, {len(routes)} routes ({gaps} without a name-matched command).", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = render()
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("parity matrix stale: run python scripts/build_parity_matrix.py", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(text.splitlines()[-1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
