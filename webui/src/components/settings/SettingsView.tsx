import { useEffect, useState } from "react";

import { fetchWeReadStatus } from "@/lib/api";
import { useClient } from "@/providers/ClientProvider";

export function SettingsView({
  theme,
  onToggleTheme,
  onLogout,
}: {
  theme: "light" | "dark";
  onToggleTheme: () => void;
  onLogout: () => void;
}) {
  const { getToken } = useClient();
  const [configured, setConfigured] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchWeReadStatus(getToken())
      .then((status) => {
        if (!cancelled) setConfigured(status.configured);
      })
      .catch(() => {
        if (!cancelled) setConfigured(null);
      });
    return () => {
      cancelled = true;
    };
  }, [getToken]);

  return (
    <>
      <header className="header">
        <div className="header-title-wrap">
          <h1>Setting</h1>
        </div>
      </header>

      <div className="shelf-container">
        <div className="book-item toread" style={{ height: "auto", padding: 14 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span className="book-name">WeRead connection</span>
            <span style={{ fontSize: 13 }}>
              {configured === null
                ? "Checking..."
                : configured
                  ? "Connected"
                  : "Not connected (set WEREAD_API_KEY)"}
            </span>
          </div>
        </div>

        <div className="book-item toread" style={{ height: "auto", padding: 14 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span className="book-name">Theme</span>
            <span style={{ fontSize: 13 }}>{theme === "dark" ? "Dark" : "Light"} (affects Ask-Book)</span>
          </div>
          <span className="book-info">
            <button type="button" className="header-btn" onClick={onToggleTheme}>
              Toggle
            </button>
          </span>
        </div>

        <button type="button" className="header-btn" style={{ width: "100%", padding: "12px 0" }} onClick={onLogout}>
          Log out
        </button>
      </div>
    </>
  );
}
