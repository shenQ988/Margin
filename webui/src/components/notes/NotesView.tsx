import { useCallback, useEffect, useState } from "react";

import { NoteDetailView } from "@/components/notes/NoteDetailView";
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
  const [selected, setSelected] = useState<{ bookId: string; title: string } | null>(null);

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

  if (selected) {
    return (
      <NoteDetailView
        bookId={selected.bookId}
        fallbackTitle={selected.title}
        onBack={() => setSelected(null)}
      />
    );
  }

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
        <div style={{ margin: "0 16px", padding: 14, border: "3px solid var(--crayon-black)", borderRadius: 10, background: "var(--book-paper)", display: "flex", flexDirection: "column", gap: 4 }}>
          <span className="book-title">WeRead is not connected</span>
          <span style={{ fontSize: 13 }}>
            Set the WEREAD_API_KEY environment variable and restart nanobot gateway to see your notes.
          </span>
        </div>
      ) : state.status === "error" ? (
        <div style={{ margin: "0 16px", padding: 14, border: "3px solid var(--crayon-black)", borderRadius: 10, background: "var(--book-paper)", display: "flex", flexDirection: "column", gap: 4 }}>
          <span className="book-title">Couldn't load your notes</span>
          <span style={{ fontSize: 13 }}>{state.message}</span>
          <button type="button" className="header-btn" onClick={() => void load()} style={{ alignSelf: "flex-start" }}>
            Retry
          </button>
        </div>
      ) : state.items.length === 0 ? (
        <p style={{ textAlign: "center", fontSize: 14 }}>You don't have any notes yet.</p>
      ) : (
        <div className="note-list">
          {state.items.map((item) => (
            <button
              type="button"
              key={item.bookId}
              className="note-item"
              onClick={() => setSelected({ bookId: item.bookId, title: item.title ?? "" })}
            >
              <span className="book-title">{item.title}</span>
              {item.author ? <span style={{ fontSize: 12 }}>{item.author}</span> : null}
              <span style={{ fontSize: 12 }}>
                {item.totalNotes} notes · {item.reviewCount} thoughts · {item.noteCount} highlights ·{" "}
                {item.bookmarkCount} bookmarks
              </span>
            </button>
          ))}
        </div>
      )}
    </>
  );
}
