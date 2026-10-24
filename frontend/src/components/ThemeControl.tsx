"use client";

import { useEffect, useState } from "react";
import { Icon } from "./ui/Icon";

const THEME_KEY = "signalrank.theme";
type Theme = "system" | "light" | "dark";
const options: { value: Theme; label: string; icon: "system" | "sun" | "moon" }[] = [
  { value: "system", label: "System theme", icon: "system" },
  { value: "light", label: "Light theme", icon: "sun" },
  { value: "dark", label: "Dark theme", icon: "moon" },
];

function apply(value: Theme) {
  if (value === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = value;
}

/** Global appearance preference. Applied before paint by the root layout script,
 * synchronised across tabs, and stored only as a cosmetic browser preference. */
export function ThemeControl() {
  const [theme, setTheme] = useState<Theme>("system");
  useEffect(() => {
    function sync() {
      let value: string = "system";
      try { value = localStorage.getItem(THEME_KEY) || "system"; } catch {}
      const next: Theme = value === "dark" || value === "light" ? value : "system";
      apply(next);
      setTheme(next);
    }
    sync();
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  function choose(value: Theme) {
    apply(value);
    setTheme(value);
    try {
      if (value === "system") localStorage.removeItem(THEME_KEY);
      else localStorage.setItem(THEME_KEY, value);
    } catch {}
  }

  return <div className="ui-segmented" role="group" aria-label="Color theme">
    {options.map(option => <button key={option.value} type="button" aria-pressed={theme === option.value}
      aria-label={option.label} title={option.label} onClick={() => choose(option.value)}>
      <Icon name={option.icon} />
    </button>)}
  </div>;
}
