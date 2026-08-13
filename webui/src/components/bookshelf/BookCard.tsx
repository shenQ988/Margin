import type { WeReadShelfItem } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS_LABEL: Record<WeReadShelfItem["status"], string> = {
  reading: "Reading",
  toread: "To Read",
  finished: "Finished",
};

function openBook(item: WeReadShelfItem): void {
  // eslint-disable-next-line no-console
  console.log("openBook", item);
  if (item.deepLink) {
    window.open(item.deepLink, "_blank", "noopener,noreferrer");
  }
}

export function BookCard({ item }: { item: WeReadShelfItem }) {
  return (
    <button type="button" onClick={() => openBook(item)} className={cn("book-item", item.status)}>
      <span className="book-name">{item.title}</span>
      <span className="book-info">
        <span>{item.progress != null ? `${item.progress}%` : STATUS_LABEL[item.status]}</span>
        {item.hasNote ? <span aria-label="Has note">★ Note</span> : null}
      </span>
    </button>
  );
}
