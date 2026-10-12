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
      setResult("Choose entitled settings within the server-provided score and daily limits.");
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
          setResult("The update response did not include verified limits. Refresh to confirm before relying on changes.");
        } else {
          setScore(String(gotScore));
          setDaily(String(gotDaily));
          setProfile(display(confirmed.trade_profile, profile));
          setRisk(display(confirmed.risk_profile, risk));
          setClasses(allowedValues(confirmed.asset_classes));
          setIsError(false);
          setResult("Trading signal preferences saved and confirmed by the account service.");
          onSaved();
        }
      } else {
        setIsError(true);
        setResult(response.response.status===403?"This subscription cannot use one of these settings. Choose entitled options.":response.response.status===401?"Your session has expired. Sign in again.":"The account service did not confirm these changes.");
      }
    } catch {
      setIsError(true);
      setResult("Preferences could not be confirmed. No save success has been assumed.");
    } finally {setSaving(false);}
  }

  return <section className="sr-data-panel sr-preferences-panel" aria-labelledby="sr-pref-title">
    <p className="sr-overline">Account-specific decision preferences</p>
    <h2 id="sr-pref-title">Signal and screening settings</h2>
    <p>Plan limits come from your authenticated account. Changes affect personal signal preferences, not broker execution permission, prop rules or platform-wide ML risk gates.</p>
    <div className="sr-grid-two">
      <div className="sr-metric"><span>Minimum certified plan score</span><strong>{numberLabel(floor)}</strong><small>Lowest selectable score for your current tier</small></div>
      <div className="sr-metric"><span>Maximum daily signals</span><strong>{numberLabel(ceiling,0)}</strong><small>Maximum entitled personal limit</small></div>
    </div>
    {!supported&&<p className="sr-submit-feedback sr-submit-feedback--error" role="alert">Server entitlement options are incomplete. Changes are disabled until they can be verified.</p>}
    <form className="sr-create-form" onSubmit={save}>
      <div className="sr-form-grid">
        <label>Trading style
          <select value={profile} onChange={event=>setProfile(event.target.value)} disabled={!supported||saving}>
            {allowedProfiles.map(value=><option key={value} value={value}>{value.replaceAll("_"," ")}</option>)}
          </select>
        </label>
        <label>Risk style
          <select value={risk} onChange={event=>setRisk(event.target.value)} disabled={!supported||saving}>
            {allowedRiskProfiles.map(value=><option key={value} value={value}>{value.replaceAll("_"," ")}</option>)}
          </select>
        </label>
        <label>Minimum signal score
          <input type="number" inputMode="decimal" min={floor??0} max={100} step="0.1" value={score}
            onChange={e=>setScore(e.target.value)} disabled={!supported||saving} required />
        </label>
        <label>Maximum signals per day
          <input type="number" inputMode="numeric" min={1} max={ceiling??500} step={1} value={daily}
            onChange={e=>setDaily(e.target.value)} disabled={!supported||saving} required />
        </label>
      </div>
      <fieldset className="sr-pref-classes" disabled={!supported||saving}>
        <legend>Entitled market classes</legend>
        <p>Select at least one. The service will verify entitlement again on save.</p>
        <div>{allowedClasses.map(c=><label key={c}><input type="checkbox" checked={classes.includes(c)}
          onChange={e=>setClasses(current=>e.target.checked?[...current,c]:current.filter(x=>x!==c))}/><span>{c}</span></label>)}</div>
      </fieldset>
      <button type="submit" className="button" disabled={!supported||saving}>{saving?"Saving preferences…":"Save signal preferences"}</button>
      {result&&<p className={isError?"sr-submit-feedback sr-submit-feedback--error":"sr-submit-feedback"} role={isError?"alert":"status"}>{result}</p>}
    </form>
  </section>;
}
