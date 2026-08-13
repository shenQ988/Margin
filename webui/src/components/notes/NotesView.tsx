import { useCallback, useEffect, useState } from "react";

import { fetchWeReadNotes, fetchWeReadStatus, type WeReadNoteItem } from "@/lib/api";
import { useClient } from "@/providers/ClientProvider";

type LoadState =
  | { status: "loading" }
  | { status: "not-configured" }
  | { status: "error"; message: string }
  | { status: "ready"; items: WeReadNoteItem[] };

export function NotesView() {
  const { getToken } = useClient();
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const status = await fetchWeReadStatus(getToken());
      if (!status.configured) {
        setState({ status: "not-configured" });
        return;
      }
      const notes = await fetchWeReadNotes(getToken());
      setState({ status: "ready", items: notes.items });
    } catch (e) {
      setState({ status: "error", message: e instanceof Error ? e.message : String(e) });
    }
  }, [getToken]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <header className="header">
        <div className="header-title-wrap">
          <h1>Notes</h1>
        </div>
        <div>
          <button type="button" className="header-btn" onClick={() => void load()}>
            Sync
          </button>
        </div>
      </header>

      {state.status === "loading" ? (
        <p style={{ textAlign: "center", fontSize: 14 }}>Loading your notes...</p>
      ) : state.status === "not-configured" ? (
        <div className="shelf-container">
          <div className="book-item toread" style={{ height: "auto", flexDirection: "column", alignItems: "flex-start", gap: 4, padding: 14 }}>
            <span className="book-name">WeRead is not connected</span>
            <span style={{ fontSize: 13 }}>
              Set the WEREAD_API_KEY environment variable and restart nanobot gateway to see your notes.
            </span>
          </div>
        </div>
      ) : state.status === "error" ? (
        <div className="shelf-container">
          <div className="book-item toread" style={{ height: "auto", flexDirection: "column", alignItems: "flex-start", gap: 4, padding: 14 }}>
            <span className="book-name">Couldn't load your notes</span>
            <span style={{ fontSize: 13 }}>{state.message}</span>
            <button type="button" className="header-btn" onClick={() => void load()}>
              Retry
            </button>
          </div>
        </div>
      ) : state.items.length === 0 ? (
        <p style={{ textAlign: "center", fontSize: 14 }}>You don't have any notes yet.</p>
      ) : (
        <div className="shelf-container">
          {state.items.map((item) => (
            <div
              key={item.bookId}
              className="book-item toread"
              style={{ height: "auto", flexDirection: "column", alignItems: "flex-start", gap: 2, padding: "10px 14px" }}
            >
              <span className="book-name">{item.title}</span>
              {item.author ? <span style={{ fontSize: 12 }}>{item.author}</span> : null}
              <span style={{ fontSize: 12 }}>
                {item.totalNotes} notes · {item.reviewCount} thoughts · {item.noteCount} highlights ·{" "}
                {item.bookmarkCount} bookmarks
              </span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
