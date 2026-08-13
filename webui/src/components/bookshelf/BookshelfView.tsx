import { useCallback, useEffect, useMemo, useState } from "react";

import { BookCard } from "@/components/bookshelf/BookCard";
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

  return (
    <>
      <header className="header">
        <div className="header-title-wrap">
          <div className="crayon-logo" aria-hidden="true">
            <span className="book b1" />
            <span className="book b2" />
            <span className="book b3" />
          </div>
          <h1>My Reading Agent</h1>
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
        <div className="shelf-container">
          <div className="book-item toread" style={{ height: "auto", flexDirection: "column", alignItems: "flex-start", gap: 4, padding: 14 }}>
            <span className="book-name">WeRead is not connected</span>
            <span style={{ fontSize: 13 }}>
              Set the WEREAD_API_KEY environment variable and restart nanobot gateway to see your bookshelf.
            </span>
          </div>
        </div>
      ) : state.status === "error" ? (
        <div className="shelf-container">
          <div className="book-item toread" style={{ height: "auto", flexDirection: "column", alignItems: "flex-start", gap: 4, padding: 14 }}>
            <span className="book-name">Couldn't load your shelf</span>
            <span style={{ fontSize: 13 }}>{state.message}</span>
            <button type="button" className="header-btn" onClick={() => void load()}>
              Retry
            </button>
          </div>
        </div>
      ) : filteredItems.length === 0 ? (
        <p style={{ textAlign: "center", fontSize: 14 }}>
          {items.length === 0 ? "Your shelf is empty." : "No books match this filter."}
        </p>
      ) : (
        <div className="shelf-container">
          {filteredItems.map((item) => (
            <BookCard key={`${item.kind}:${item.id}`} item={item} />
          ))}
        </div>
      )}
    </>
  );
}
