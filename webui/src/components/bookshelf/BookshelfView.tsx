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

const EMPTY_READING_MAP: WeReadAdvisorPayload = {
  configured: true,
  deepReads: [],
  dormantBooks: [],
  activeBooks: [],
  topics: [],
  recommendation: null,
  confidence: "low",
};

export function BookshelfView({ mapOnly = false }: { mapOnly?: boolean } = {}) {
  const { getToken } = useClient();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [advisor, setAdvisor] = useState<WeReadAdvisorPayload | null>(null);
  const [readingMapOpen, setReadingMapOpen] = useState(mapOnly);
  const [topic, setTopic] = useState("");
  const [mapLoading, setMapLoading] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
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

  const generateMap = useCallback(async () => {
    const requestedTopic = topic.trim();
    if (!requestedTopic) {
      setMapError("Enter a topic before generating a map.");
      return;
    }
    setMapLoading(true);
    setMapError(null);
    try {
      setAdvisor(await fetchWeReadAdvisor(getToken(), "", requestedTopic));
    } catch (error) {
      setMapError(error instanceof Error ? error.message : "Could not generate the reading map.");
    } finally {
      setMapLoading(false);
    }
  }, [getToken, topic]);

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

  // The Reading Map is its own tab. Do not fall through to the shelf while
  // the initial advisor request is pending or unavailable.
  if (readingMapOpen && (advisor || mapOnly)) {
    return (
      <ReadingMapView
        advisor={advisor ?? EMPTY_READING_MAP}
        topic={topic}
        onTopicChange={setTopic}
        onGenerate={generateMap}
        isGenerating={mapLoading}
        error={mapError}
        onBack={mapOnly ? undefined : () => setReadingMapOpen(false)}
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

      {!mapOnly && advisor ? <AdvisorCard advisor={advisor} onOpen={() => setReadingMapOpen(true)} /> : null}

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

function ReadingMapView({ advisor, topic, onTopicChange, onGenerate, isGenerating, error, onBack }: { advisor: WeReadAdvisorPayload; topic: string; onTopicChange: (value: string) => void; onGenerate: () => void; isGenerating: boolean; error: string | null; onBack?: () => void }) {
  return (
    <main className="reading-map-view">
      <header className="header reading-map-header">
        {onBack ? <button type="button" className="header-btn" onClick={onBack}>Back</button> : <span />}
        <h1>Your Reading Map</h1>
        <span className="reading-map-confidence">
          {advisor.confidence === "high" ? "Based on your notes" : "Getting to know you"}
        </span>
      </header>

      <section className="reading-map-section">
        <h2>Explore a topic</h2>
        <p>Enter a topic to generate a map from your related WeRead activity.</p>
        <form className="reading-map-topic-form" onSubmit={(event) => { event.preventDefault(); onGenerate(); }}>
          <input value={topic} onChange={(event) => onTopicChange(event.target.value)} placeholder="e.g. product management" aria-label="Topic to explore" />
          <button type="submit" className="header-btn" disabled={isGenerating}>{isGenerating ? "Generating…" : "Generate map"}</button>
        </form>
        {error ? <p className="reading-map-error" role="alert">{error}</p> : null}
      </section>

      {advisor.suggestedBooks?.length ? (
        <section className="reading-map-section">
          <h2>Your suggested path</h2>
          <p>A three-step sequence from the live WeRead catalog for {topic}.</p>
          <ol className="reading-map-suggestions">
            {advisor.suggestedBooks.map((book) => (
              <li key={book.bookId}>
                <span className="reading-map-level">Step {book.step} of 3 · {book.level}</span>
                <strong>{book.title}</strong>
                <span>{book.author ?? "Unknown author"}{book.category ? ` · ${book.category}` : ""}</span>
                <p>{book.reason}</p>
                {book.deepLink ? <a href={book.deepLink} target="_blank" rel="noreferrer">Open in WeRead</a> : null}
              </li>
            ))}
          </ol>
        </section>
      ) : topic.trim() && !isGenerating ? (
        <section className="reading-map-section">
          <h2>No path yet</h2>
          <p>WeRead did not return eligible books for this topic. Try a shorter or more specific topic.</p>
        </section>
      ) : null}
    </main>
  );
}
