import { useCallback, useEffect, useState } from "react";

import { fetchWeReadBookNotes, type WeReadBookNoteQuoteItem } from "@/lib/api";
import { useClient } from "@/providers/ClientProvider";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; title: string; author: string | null; items: WeReadBookNoteQuoteItem[] };

export function NoteDetailView({
  bookId,
  fallbackTitle,
  deepLink,
  onBack,
}: {
  bookId: string;
  fallbackTitle: string;
  deepLink?: string | null;
  onBack: () => void;
}) {
  const { getToken } = useClient();
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const load = useCallback(async () => {
    setState({ status: "loading" });
    try {
      const payload = await fetchWeReadBookNotes(getToken(), bookId);
      setState({
        status: "ready",
        title: payload.book.title ?? fallbackTitle,
        author: payload.book.author,
        items: payload.items,
      });
    } catch (e) {
      setState({ status: "error", message: e instanceof Error ? e.message : String(e) });
    }
  }, [getToken, bookId, fallbackTitle]);

  useEffect(() => {
    void load();
  }, [load]);

  const title = state.status === "ready" ? state.title : fallbackTitle;

  return (
    <>
      <header className="header">
        <div className="header-title-wrap">
          <button type="button" className="header-btn" onClick={onBack} aria-label="Back to notes">
            ← Back
          </button>
        </div>
        {deepLink ? (
          <a
            href={deepLink}
            target="_blank"
            rel="noopener noreferrer"
            className="header-btn"
          >
            Open in WeRead ↗
          </a>
        ) : null}
      </header>

      <div style={{ padding: "0 16px 12px" }}>
        <h1 style={{ fontSize: 20, fontWeight: 600 }}>{title}</h1>
        {state.status === "ready" && state.author ? (
          <p style={{ fontSize: 13, marginTop: 2 }}>{state.author}</p>
        ) : null}
      </div>

      {state.status === "loading" ? (
        <p style={{ textAlign: "center", fontSize: 14 }}>Loading quotes...</p>
      ) : state.status === "error" ? (
        <div style={{ margin: "0 16px", padding: 14, border: "3px solid var(--crayon-black)", borderRadius: 10, background: "var(--book-paper)", display: "flex", flexDirection: "column", gap: 4 }}>
          <span className="book-title">Couldn't load this book's notes</span>
          <span style={{ fontSize: 13 }}>{state.message}</span>
          <button type="button" className="header-btn" onClick={() => void load()} style={{ alignSelf: "flex-start" }}>
            Retry
          </button>
        </div>
      ) : state.items.length === 0 ? (
        <p style={{ textAlign: "center", fontSize: 14 }}>No highlights or thoughts for this book yet.</p>
      ) : (
        <div className="quote-list">
          {state.items.map((item) => (
            <div key={item.id} className="quote-card">
              {item.chapterTitle ? <span className="quote-chapter">{item.chapterTitle}</span> : null}
              {item.type === "highlight" ? (
                <p className="quote-text">{item.text}</p>
              ) : (
                <>
                  {item.quote ? <p className="quote-original">{item.quote}</p> : null}
                  <p className="quote-thought">{item.text}</p>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
