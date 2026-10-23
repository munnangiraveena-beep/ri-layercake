"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark" | "system";
const KEY = "ri-layercake/theme";

/** Light by default; dark or follow the system, remembered in this browser. */
export default function ThemeSwitch() {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    let saved: Theme = "light";
    try {
      saved = (localStorage.getItem(KEY) as Theme) || "light";
    } catch {
      // storage blocked: stay light
    }
    Promise.resolve().then(() => setTheme(saved));
  }, []);

  function choose(t: Theme) {
    setTheme(t);
    document.documentElement.setAttribute("data-theme", t);
    try {
      localStorage.setItem(KEY, t);
    } catch {
      // not remembered, still applied
    }
  }

  return (
    <div className="theme-switch" role="radiogroup" aria-label="Colour theme">
      {(["light", "dark", "system"] as const).map((t) => (
        <button key={t} type="button" role="radio" aria-checked={theme === t} onClick={() => choose(t)}>
          {t === "light" ? "Light" : t === "dark" ? "Dark" : "System"}
        </button>
      ))}
    </div>
  );
}
