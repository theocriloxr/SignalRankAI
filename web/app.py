from flask import Flask, request, render_template, redirect, url_for, session, abort
from utils.async_runner import run_sync
import os
from db.session import get_session
from db.pg_features import list_signals_sent_today
from signalrank_telegram.access import resolve_user_tier

app = Flask(__name__)
app.secret_key = os.getenv("WEB_SECRET_KEY", "changeme")

@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user_id = request.form.get("user_id")
        # In production, use a secure token or Telegram login widget
        if user_id and user_id.isdigit():
            session["user_id"] = int(user_id)
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Invalid user ID")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))
    # Only show this user's signals
    signals = []
    tier = resolve_user_tier(user_id)
    try:
        if ENGINE is not None:
            import asyncio
            async def fetch():
                async with get_session() as s:
                    rows = await list_signals_sent_today(s, telegram_user_id=int(user_id))
                    await s.commit()
                    return rows
            signals = run_sync(fetch())
    except Exception:
        signals = []
    # Determine feature access by tier
    tier_norm = str(tier).strip().lower()
    show_advanced = tier_norm in ("premium", "vip", "admin", "owner")
    return render_template(
        "dashboard.html",
        signals=signals,
        tier=tier,
        show_advanced=show_advanced
    )

if __name__ == "__main__":
    app.run(debug=True, port=5000)
