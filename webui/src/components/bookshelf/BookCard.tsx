import type { WeReadShelfItem } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS_LABEL: Record<WeReadShelfItem["status"], string> = {
  reading: "Reading",
  toread: "To Read",
  finished: "Finished",
};

function openInWeRead(item: WeReadShelfItem): void {
  if (item.deepLink) {
    window.open(item.deepLink, "_blank", "noopener,noreferrer");
  }
}

export function BookCard({
  item,
  onOpenHighlights,
}: {
  item: WeReadShelfItem;
  onOpenHighlights: (item: WeReadShelfItem) => void;
}) {
  return (
    <button type="button" onClick={() => onOpenHighlights(item)} className="book-card">
      <span className={cn("book-cover", !item.cover && item.status)}>
        {item.cover ? (
          <img src={item.cover} alt="" loading="lazy" />
        ) : (
          <span className="book-cover-fallback">{item.title}</span>
        )}
        {item.hasNote ? (
          <span className="book-cover-note" aria-label="Has note">★</span>
        ) : null}
        {item.deepLink ? (
          <span
            role="button"
            tabIndex={0}
            className="book-cover-weread-link"
            aria-label="Open in WeRead"
            onClick={(e) => {
              e.stopPropagation();
              openInWeRead(item);
            }}
            onKeyDown={(e) => {
              if (e.key !== "Enter" && e.key !== " ") return;
              e.stopPropagation();
              e.preventDefault();
              openInWeRead(item);
            }}
          >
            ↗
          </span>
        ) : null}
        {item.progress != null ? (
          <span className="book-cover-progress">{item.progress}%</span>
        ) : null}
      </span>
      <span className="book-title">{item.title}</span>
      {item.progress == null ? <span className="book-status">{STATUS_LABEL[item.status]}</span> : null}
    </button>
  );
}
