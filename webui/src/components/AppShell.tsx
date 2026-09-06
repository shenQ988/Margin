import { useEffect, useState } from "react";

import { BookshelfView } from "@/components/bookshelf/BookshelfView";
import { NotesView } from "@/components/notes/NotesView";
import { SettingsView } from "@/components/settings/SettingsView";
import { cn } from "@/lib/utils";

type Tab = "shelf" | "notes" | "reading-map" | "settings";

const TABS: { id: Tab; label: string }[] = [
  { id: "shelf", label: "Shelf" },
  { id: "notes", label: "Notes" },
  { id: "reading-map", label: "Reading Map" },
  { id: "settings", label: "Setting" },
];

function readTab(): Tab {
  const hash = window.location.hash.replace(/^#\/?/, "");
  return TABS.some((tab) => tab.id === hash) ? (hash as Tab) : "shelf";
}

function writeTab(tab: Tab): void {
  const nextHash = `#/${tab}`;
  if (window.location.hash === nextHash) return;
  window.location.hash = nextHash;
}

export function AppShell({
  theme,
  onToggleTheme,
  onLogout,
}: {
  theme: "light" | "dark";
  onToggleTheme: () => void;
  onLogout: () => void;
}) {
  void theme;
  void onToggleTheme;
  const [tab, setTab] = useState<Tab>(readTab);
  const [visited, setVisited] = useState<Set<Tab>>(() => new Set([readTab()]));

  useEffect(() => {
    const onHashChange = () => {
      const next = readTab();
      setTab(next);
      setVisited((current) => (current.has(next) ? current : new Set(current).add(next)));
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const selectTab = (next: Tab) => {
    writeTab(next);
    setTab(next);
    setVisited((current) => (current.has(next) ? current : new Set(current).add(next)));
  };

  return (
    <div className="hd-shell relative h-full w-full">
      {/* Bookshelf/Notes/Settings each fetch on mount; mounting them lazily
          (only once visited) avoids firing several concurrent HTTP requests
          at page load. Ask-Book stays always-mounted so an in-flight
          streaming response survives switching tabs away and back. The bottom
          nav is `position: fixed` (see handdrawn.css), so panes get the full
          height and each screen reserves its own bottom clearance. */}
      {visited.has("shelf") ? (
        <Pane active={tab === "shelf"} scrollable>
          <BookshelfView />
        </Pane>
      ) : null}
      {visited.has("notes") ? (
        <Pane active={tab === "notes"} scrollable>
          <NotesView />
        </Pane>
      ) : null}
      {visited.has("reading-map") ? <Pane active={tab === "reading-map"} scrollable>
        <BookshelfView mapOnly />
      </Pane>
      : null}
      {visited.has("settings") ? (
        <Pane active={tab === "settings"} scrollable>
          <SettingsView onLogout={onLogout} />
        </Pane>
      ) : null}

      <nav className="bottom-nav" role="tablist" aria-label="Main navigation">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => selectTab(item.id)}
            className="nav-item"
          >
            {item.label}
          </button>
        ))}
      </nav>
    </div>
  );
}

function Pane({
  active,
  scrollable = false,
  bottomClearance = false,
  children,
}: {
  active: boolean;
  scrollable?: boolean;
  /** Reserve space for the fixed bottom nav instead of letting content (e.g.
      ThreadShell's own composer) render underneath it. Scrollable panes
      already do this via `.shelf-container`'s own bottom padding; this is
      for non-scrollable panes (Ask-Book) that fill their full container. */
  bottomClearance?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "absolute inset-0 flex flex-col",
        scrollable ? "overflow-y-auto" : "overflow-hidden",
        active ? "" : "hidden",
      )}
      style={bottomClearance ? { paddingBottom: "var(--bottom-nav-height, 60px)" } : undefined}
    >
      {children}
    </div>
  );
}
