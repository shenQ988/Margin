import { useCallback, useEffect, useMemo, useState } from "react";

import { BookCard } from "@/components/bookshelf/BookCard";
import { NoteDetailView } from "@/components/notes/NoteDetailView";
import { fetchWeReadShelf, fetchWeReadStatus, type WeReadShelfItem } from "@/lib/api";
import { useClient } from "@/providers/ClientProvider";

type LoadState =
  | { status: "loading" }
  | { status: "not-configured" }
  | { status: "error"; message: string }
  | { status: "ready"; items: WeReadShelfItem[] };

type StatusFilter = "all" | "reading" | "toread" | "finished";

export function BookshelfView() {
  const { getToken } = useClient();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [selected, setSelected] = useState<
    { bookId: string; title: string; deepLink: string | null } | null
  >(null);

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const status = await fetchWeReadStatus(getToken());
      if (!status.configured) {
        setState({ status: "not-configured" });
        return;
      }
      const shelf = await fetchWeReadShelf(getToken());
      setState({ status: "ready", items: shelf.items });
    } catch (e) {
      setState({ status: "error", message: e instanceof Error ? e.message : String(e) });
    }
  }, [getToken]);

  useEffect(() => {
    void load();
  }, [load]);

  const items = state.status === "ready" ? state.items : [];
  const filteredItems = useMemo(
    () => (filter === "all" ? items : items.filter((item) => item.status === filter)),
    [items, filter],
  );

  const handleOpenHighlights = useCallback((item: WeReadShelfItem) => {
    if (item.kind === "book") {
      setSelected({ bookId: String(item.id), title: item.title ?? "", deepLink: item.deepLink });
      return;
    }
    // Albums/collections don't have a per-book highlights view — fall back
    // to opening WeRead directly, same as the old default click behavior.
    if (item.deepLink) {
      window.open(item.deepLink, "_blank", "noopener,noreferrer");
    }
  }, []);

  if (selected) {
    return (
      <NoteDetailView
        bookId={selected.bookId}
        fallbackTitle={selected.title}
        deepLink={selected.deepLink}
        onBack={() => setSelected(null)}
      />
    );
  }

  return (
    <>
      <div className="bookshelf-hero">
        <img src="/bookshelf/bookshelf_bg.png" alt="Hand-drawn illustrated bookshelf" />
      </div>

      <header className="header">
        <div className="header-title-wrap">
          <h1>My Shelf</h1>
        </div>
        <div>
          <button type="button" className="header-btn" onClick={() => void load()}>
            Sync
          </button>
          <button
            type="button"
            className="header-btn"
            onClick={() =>
              setFilter((current) => {
                const order: StatusFilter[] = ["all", "reading", "toread", "finished"];
                return order[(order.indexOf(current) + 1) % order.length] ?? "all";
              })
            }
          >
            Filter{filter !== "all" ? `: ${filter}` : ""}
          </button>
        </div>
      </header>

      {state.status === "loading" ? (
        <p style={{ textAlign: "center", fontSize: 14 }}>Loading your shelf...</p>
      ) : state.status === "not-configured" ? (
        <div style={{ margin: "0 16px", padding: 14, border: "3px solid var(--crayon-black)", borderRadius: 10, background: "var(--book-paper)", display: "flex", flexDirection: "column", gap: 4 }}>
          <span className="book-title">WeRead is not connected</span>
          <span style={{ fontSize: 13 }}>
            Set the WEREAD_API_KEY environment variable and restart nanobot gateway to see your bookshelf.
          </span>
        </div>
      ) : state.status === "error" ? (
        <div style={{ margin: "0 16px", padding: 14, border: "3px solid var(--crayon-black)", borderRadius: 10, background: "var(--book-paper)", display: "flex", flexDirection: "column", gap: 4 }}>
          <span className="book-title">Couldn't load your shelf</span>
          <span style={{ fontSize: 13 }}>{state.message}</span>
          <button type="button" className="header-btn" onClick={() => void load()} style={{ alignSelf: "flex-start" }}>
            Retry
          </button>
        </div>
      ) : filteredItems.length === 0 ? (
        <p style={{ textAlign: "center", fontSize: 14 }}>
          {items.length === 0 ? "Your shelf is empty." : "No books match this filter."}
        </p>
      ) : (
        <div className="shelf-container">
          {filteredItems.map((item) => (
            <BookCard
              key={`${item.kind}:${item.id}`}
              item={item}
              onOpenHighlights={handleOpenHighlights}
            />
          ))}
        </div>
      )}
    </>
  );
}
