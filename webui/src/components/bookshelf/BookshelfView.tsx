import { useCallback, useEffect, useMemo, useState } from "react";

import { BookCard } from "@/components/bookshelf/BookCard";
import { NoteDetailView } from "@/components/notes/NoteDetailView";
import {
  fetchWeReadAdvisor,
  fetchWeReadShelf,
  fetchWeReadStatus,
  type WeReadAdvisorPayload,
  type WeReadShelfItem,
} from "@/lib/api";
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
  const [advisor, setAdvisor] = useState<WeReadAdvisorPayload | null>(null);
  const [readingMapOpen, setReadingMapOpen] = useState(false);
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
      const [shelf, readingAdvisor] = await Promise.all([
        fetchWeReadShelf(getToken()),
        fetchWeReadAdvisor(getToken()).catch(() => null),
      ]);
      setState({ status: "ready", items: shelf.items });
      setAdvisor(readingAdvisor);
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

  if (readingMapOpen && advisor) {
    return <ReadingMapView advisor={advisor} onBack={() => setReadingMapOpen(false)} />;
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

      {advisor ? <AdvisorCard advisor={advisor} onOpen={() => setReadingMapOpen(true)} /> : null}

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

function AdvisorCard({ advisor, onOpen }: { advisor: WeReadAdvisorPayload; onOpen: () => void }) {
  const recommendation = advisor.recommendation;
  return (
    <button type="button" className="advisor-card" aria-label="Open Reading Map" onClick={onOpen}>
      <div className="advisor-card-heading">
        <strong>Your Reading Map</strong>
        <span>{advisor.confidence === "high" ? "Based on your notes" : "Getting to know you"}</span>
      </div>
      {advisor.topics.length ? (
        <p>Deep-reading topics: {advisor.topics.map((topic) => topic.name).join(", ")}</p>
      ) : null}
      {recommendation ? (
        <div className="advisor-recommendation">
          <span>Read next</span>
          <strong>{recommendation.title}</strong>
          {recommendation.author ? <small>{recommendation.author}</small> : null}
          <p>{recommendation.reason}</p>
        </div>
      ) : advisor.deepReads.length === 0 ? (
        <p>Add highlights or notes to a few books and Margin will start finding reading patterns.</p>
      ) : (
        <p>We found your reading history. Open the map to see the books shaping it.</p>
      )}
      <span className="advisor-open-label">Open map →</span>
    </button>
  );
}

function ReadingMapView({ advisor, onBack }: { advisor: WeReadAdvisorPayload; onBack: () => void }) {
  const route = buildReadingRoute(advisor);

  return (
    <main className="reading-map-view">
      <header className="header reading-map-header">
        <button type="button" className="header-btn" onClick={onBack}>Back</button>
        <h1>Your Reading Map</h1>
        <span className="reading-map-confidence">
          {advisor.confidence === "high" ? "Based on your notes" : "Getting to know you"}
        </span>
      </header>

      <section className="reading-map-section" aria-labelledby="reading-path-title">
        <h2 id="reading-path-title">Deep reads</h2><p>Books with five or more notes, highlights, or bookmarks.</p>
        <ReadingMapBookList books={advisor.deepReads} />
      </section>
      <section className="reading-map-section"><h2>Currently reading</h2><p>Unfinished books opened recently.</p>
        <ReadingMapBookList books={advisor.activeBooks} />
      </section>
      <section className="reading-map-section"><h2>Ready to revisit</h2><p>Books without recent activity or notes.</p>
        <ReadingMapBookList books={route.filter((step) => step.label === "Revisit").map((step) => step.book)} />
      </section>

      {advisor.topics.length || advisor.deepReads.length ? (
        <section className="reading-map-section">
          <h2>What this path builds on</h2>
          {advisor.topics.length ? (
            <div className="reading-map-topics">
              {advisor.topics.map((topic) => (
                <span key={topic.name}>{topic.name} · {topic.deepReadCount} book{topic.deepReadCount === 1 ? "" : "s"}</span>
              ))}
            </div>
          ) : null}
          {advisor.deepReads.length ? (
            <p>Deep reads: {advisor.deepReads.map((book) => book.title).join(", ")}.</p>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}

function ReadingMapBookList({ books }: { books: WeReadAdvisorPayload["deepReads"] }) {
  return books.length ? <ul className="reading-map-book-list">{books.map((book) => <li key={book.bookId}><strong>{book.title}</strong><span>{book.author ?? "Unknown author"}</span><small>{book.noteCount ?? 0} notes</small></li>)}</ul> : <p className="reading-map-empty">Nothing here yet.</p>;
}

function buildReadingRoute(advisor: WeReadAdvisorPayload) {
  const seen = new Set<string>();
  const route: Array<{
    book: WeReadAdvisorPayload["deepReads"][number];
    label: "Continue" | "Revisit" | "Read next";
    detail: string;
  }> = [];
  const add = (
    book: WeReadAdvisorPayload["deepReads"][number],
    label: "Continue" | "Revisit" | "Read next",
    detail: string,
  ) => {
    if (!seen.has(book.bookId)) {
      seen.add(book.bookId);
      route.push({ book, label, detail });
    }
  };

  advisor.activeBooks.forEach((book) => add(book, "Continue", "Recently active"));
  if (advisor.recommendation) {
    add(advisor.recommendation, "Read next", advisor.recommendation.reason ?? "Matches your reading map");
  }
  advisor.dormantBooks.forEach((book) => add(book, "Revisit", "Ready for a fresh pass"));
  return route;
}
