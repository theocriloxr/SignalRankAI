"use client";

import { useEffect, useRef } from "react";

const THEME_KEY = "signalrank.theme";

export function ThemeControl() {
  const select = useRef<HTMLSelectElement>(null);
  useEffect(() => {
    function sync() {
      let value = "system";
      try { value = localStorage.getItem(THEME_KEY) || "system"; } catch {}
      if (value !== "dark" && value !== "light") value = "system";
      if (value === "system") delete document.documentElement.dataset.theme;
      else document.documentElement.dataset.theme = value;
      if (select.current) select.current.value = value;
    }
    sync();
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  return <label className="appearanceControl">Appearance
    <select ref={select} aria-label="Color theme" defaultValue="system" onChange={(event) => {
      const value = event.target.value;
      if (value === "system") delete document.documentElement.dataset.theme;
      else document.documentElement.dataset.theme = value;
      try {
        if (value === "system") localStorage.removeItem(THEME_KEY);
        else localStorage.setItem(THEME_KEY, value);
      } catch {}
    }}>
      <option value="system">System</option><option value="dark">Dark</option><option value="light">Light</option>
    </select>
  </label>;
}
