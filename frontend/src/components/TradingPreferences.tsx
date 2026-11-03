"use client";

import { useState, type FormEvent } from "react";
import client from "../lib/client";
import { display, finite, record, numberLabel, type Row } from "../lib/presentation";

function allowedValues(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return Array.from(new Set(raw.filter((item): item is string =>
    typeof item === "string" && item.trim().length > 0)));
}

export function TradingPreferences({ data, onSaved }: { data: Row; onSaved: () => void }) {
  const prefs = record(data.preferences);
  const options = record(data.options);
  const policy = record(data.tier_policy);
  const allowedProfiles = allowedValues(options.trade_profiles);
  const allowedRiskProfiles = allowedValues(options.risk_profiles);
  const allowedClasses = allowedValues(options.asset_classes);
  const [profile, setProfile] = useState(display(prefs.trade_profile, "all"));
  const [risk, setRisk] = useState(display(prefs.risk_profile, "balanced"));
  const [score, setScore] = useState(String(finite(prefs.min_signal_score) ?? ""));
  const [daily, setDaily] = useState(String(finite(prefs.max_signals_per_day) ?? ""));
  const [classes, setClasses] = useState<string[]>(allowedValues(prefs.asset_classes));
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState("");
  const [isError, setIsError] = useState(false);
  const floor = finite(policy.minimum_signal_score);
  const ceiling = finite(policy.daily_signal_limit);
  const supported = allowedProfiles.length > 0 && allowedRiskProfiles.length > 0 &&
    floor !== null && ceiling !== null && allowedClasses.length > 0;

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving || !supported) return;
    const minScore = Number(score), maxDaily = Number(daily);
    if (!Number.isFinite(minScore) || minScore < floor! || minScore > 100 ||
        !Number.isInteger(maxDaily) || maxDaily < 1 || maxDaily > ceiling! ||
        !allowedProfiles.includes(profile) || !allowedRiskProfiles.includes(risk) ||
        classes.length === 0 || classes.some(c => !allowedClasses.includes(c))) {
      setIsError(true);
      setResult("Pick values within your plan's limits.");
      return;
    }

    setSaving(true);setResult("");
    try {
      const response = await client.PUT("/api/v1/platform/trading-profile",{
        body:{
          trade_profile:profile,
          risk_profile:risk,
          min_signal_score:minScore,
          max_signals_per_day:maxDaily,
          asset_classes:classes,
        },
      });
      if (response.response.ok && response.data) {
        const confirmed = record(response.data.preferences);
        const gotScore = finite(confirmed.min_signal_score);
        const gotDaily = finite(confirmed.max_signals_per_day);
        if (gotScore === null || gotDaily === null) {
          setIsError(true);
          setResult("Saved, but we couldn't read back your limits. Refresh to check.");
        } else {
          setScore(String(gotScore));
          setDaily(String(gotDaily));
          setProfile(display(confirmed.trade_profile, profile));
          setRisk(display(confirmed.risk_profile, risk));
          setClasses(allowedValues(confirmed.asset_classes));
          setIsError(false);
          setResult("Saved.");
          onSaved();
        }
      } else {
        setIsError(true);
        setResult(response.response.status===403?"One of these isn't on your plan.":response.response.status===401?"Your session has expired. Sign in again.":"That didn't save. Try again.");
      }
    } catch {
      setIsError(true);
      setResult("We couldn't confirm the change. Refresh to check.");
    } finally {setSaving(false);}
  }

  return <section className="ui-card" aria-labelledby="sr-pref-title">
    
    <h2 id="sr-pref-title">Which signals you get</h2>
    <p>These only change which signals reach you. They don&rsquo;t change how signals are chosen.</p>
    <div className="ws-grid-2">
      <div className="ui-stat"><span>Lowest score</span><strong>{numberLabel(floor)}</strong><small>The lowest your plan allows</small></div>
      <div className="ui-stat"><span>Most signals a day</span><strong>{numberLabel(ceiling,0)}</strong><small>The most your plan allows</small></div>
    </div>
    {!supported&&<p className="ui-feedback ui-feedback--error" role="alert">We couldn&rsquo;t load your plan&rsquo;s limits, so changes are switched off for now. Refresh to try again.</p>}
    <form className="ui-form" onSubmit={save}>
      <div className="ui-form-grid">
        <label className="ui-field">Trading style
          <select className="ui-select" value={profile} onChange={event=>setProfile(event.target.value)} disabled={!supported||saving}>
            {allowedProfiles.map(value=><option key={value} value={value}>{value.replaceAll("_"," ").replace(/^./,c=>c.toUpperCase())}</option>)}
          </select>
        </label>
        <label className="ui-field">Risk style
          <select className="ui-select" value={risk} onChange={event=>setRisk(event.target.value)} disabled={!supported||saving}>
            {allowedRiskProfiles.map(value=><option key={value} value={value}>{value.replaceAll("_"," ").replace(/^./,c=>c.toUpperCase())}</option>)}
          </select>
        </label>
        <label className="ui-field">Minimum signal score
          <input className="ui-input" type="number" inputMode="decimal" min={floor??0} max={100} step="0.1" value={score}
            onChange={e=>setScore(e.target.value)} disabled={!supported||saving} required />
        </label>
        <label className="ui-field">Maximum signals per day
          <input className="ui-input" type="number" inputMode="numeric" min={1} max={ceiling??500} step={1} value={daily}
            onChange={e=>setDaily(e.target.value)} disabled={!supported||saving} required />
        </label>
      </div>
      <fieldset className="ui-fieldset" disabled={!supported||saving}>
        <legend>Markets</legend>
        <p>Pick at least one.</p>
        <div className="ui-check-row">{allowedClasses.map(c=><label className="ui-check" key={c}><input type="checkbox" checked={classes.includes(c)}
          onChange={e=>setClasses(current=>e.target.checked?[...current,c]:current.filter(x=>x!==c))}/><span>{c}</span></label>)}</div>
      </fieldset>
      <button type="submit" className="ui-btn ui-btn--primary" disabled={!supported||saving}>{saving?"Saving preferences…":"Save"}</button>
      {result&&<p className={isError?"ui-feedback ui-feedback--error":"ui-feedback"} role={isError?"alert":"status"}>{result}</p>}
    </form>
  </section>;
}
