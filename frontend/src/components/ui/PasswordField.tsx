"use client";

import { useId, useState } from "react";
import { Icon } from "./Icon";

/** The account service's password rule (services/platform/identity.validate_password). */
export const PASSWORD_RULES: { id: string; label: string; test: (value: string) => boolean }[] = [
  { id: "length", label: "At least 10 characters", test: v => v.length >= 10 },
  { id: "kinds", label: "Three of: lowercase, uppercase, number, symbol",
    test: v => [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter(re => re.test(v)).length >= 3 },
];

export function passwordMeetsRules(value: string): boolean {
  return PASSWORD_RULES.every(rule => rule.test(value));
}

/** Password input with a show/hide button and, for new passwords, the live rule checklist. */
export function PasswordField({ label, name, autoComplete, required = true, showRules = false, minLength, maxLength = 256 }: {
  label: string; name: string; autoComplete: string; required?: boolean; showRules?: boolean; minLength?: number; maxLength?: number;
}) {
  const [visible, setVisible] = useState(false);
  const [value, setValue] = useState("");
  const id = useId();
  const rulesId = `${id}-rules`;
  return <div className="ui-field">
    <label htmlFor={id}>{label}</label>
    <div className="ui-password">
      <input id={id} className="ui-input" name={name} type={visible ? "text" : "password"} autoComplete={autoComplete}
        required={required} minLength={minLength} maxLength={maxLength} value={value}
        onChange={event => setValue(event.target.value)} aria-describedby={showRules ? rulesId : undefined}
        autoCapitalize="none" autoCorrect="off" spellCheck={false}/>
      <button type="button" className="ui-password-toggle" onClick={() => setVisible(v => !v)}
        aria-label={visible ? "Hide password" : "Show password"} aria-pressed={visible} aria-controls={id}>
        <Icon name={visible ? "eyeOff" : "eye"} size={18}/>
      </button>
    </div>
    {showRules && <ul className="ui-password-rules" id={rulesId} aria-live="polite">
      {PASSWORD_RULES.map(rule => {
        const ok = rule.test(value);
        return <li key={rule.id} data-ok={ok ? "true" : "false"}><Icon name={ok ? "check" : "info"} size={14}/>
          <span>{rule.label}</span></li>;
      })}
    </ul>}
  </div>;
}
