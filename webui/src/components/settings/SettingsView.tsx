import { useEffect, useState } from "react";

import { fetchWeReadStatus } from "@/lib/api";
import { useClient } from "@/providers/ClientProvider";

export function SettingsView({ onLogout }: { onLogout: () => void }) {
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

      <div className="settings-list">
        <div className="settings-row">
          <span className="settings-row-label">WeRead connection</span>
          <span className="settings-row-value">
            {configured === null
              ? "Checking..."
              : configured
                ? "Connected"
                : "Not connected (set WEREAD_API_KEY)"}
          </span>
        </div>

        <button type="button" className="settings-row settings-row-action" onClick={onLogout}>
          <span className="settings-row-label">Log out</span>
        </button>
      </div>
    </>
  );
}
