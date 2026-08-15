import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  type ReactNode,
} from "react";

type Theme = "light" | "dark";
const ThemeContext = createContext<Theme>("light");

function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "dark") root.classList.add("dark");
  else root.classList.remove("dark");
}

// Dark mode is disabled app-wide (Ask-Book and Setting both dropped their
// toggle) — this always resolves to "light" and never reads/writes stored or
// system-preference theme. `toggle`/`setTheme` are kept as no-ops so callers
// that still hold onto them (tests, ThreadShell's optional prop) don't break.
export function useTheme(): {
  theme: Theme;
  toggle: () => void;
  setTheme: (t: Theme) => void;
} {
  const theme: Theme = "light";

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const setTheme = useCallback((_t: Theme) => {}, []);
  const toggle = useCallback(() => {}, []);
  return { theme, toggle, setTheme };
}

export function ThemeProvider({ theme, children }: { theme: Theme; children: ReactNode }) {
  return createElement(ThemeContext.Provider, { value: theme }, children);
}

export function useThemeValue(): Theme {
  return useContext(ThemeContext);
}
