import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BookshelfView } from "@/components/bookshelf/BookshelfView";
import * as api from "@/lib/api";
import type { NanobotClient } from "@/lib/nanobot-client";
import { ClientProvider } from "@/providers/ClientProvider";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    fetchWeReadStatus: vi.fn(),
    fetchWeReadShelf: vi.fn(),
    fetchWeReadBookNotes: vi.fn(),
  };
});

function renderView() {
  const client = { newChat: vi.fn() } as unknown as NanobotClient;
  return render(
    <ClientProvider client={client} token="tok">
      <BookshelfView />
    </ClientProvider>,
  );
}

describe("BookshelfView", () => {
  beforeEach(() => {
    vi.mocked(api.fetchWeReadStatus).mockReset();
    vi.mocked(api.fetchWeReadShelf).mockReset();
    vi.mocked(api.fetchWeReadBookNotes).mockReset();
  });

  it("shows a not-configured empty state when WEREAD_API_KEY is unset", async () => {
    vi.mocked(api.fetchWeReadStatus).mockResolvedValue({ configured: false });
    renderView();
    await waitFor(() => expect(screen.getByText(/not connected/i)).toBeInTheDocument());
    expect(api.fetchWeReadShelf).not.toHaveBeenCalled();
  });

  it("renders the shelf grid when configured", async () => {
    vi.mocked(api.fetchWeReadStatus).mockResolvedValue({ configured: true });
    vi.mocked(api.fetchWeReadShelf).mockResolvedValue({
      configured: true,
      count: 1,
      items: [
        {
          kind: "book",
          id: "b1",
          title: "三体",
          author: "刘慈欣",
          cover: null,
          category: "科幻",
          finished: true,
          top: false,
          deepLink: null,
          updateTime: null,
          status: "finished",
          progress: null,
          hasNote: false,
        },
      ],
    });
    renderView();
    await waitFor(() => expect(screen.getAllByText("三体").length).toBeGreaterThan(0));
  });

  it("shows an error state with a retry button on failure", async () => {
    vi.mocked(api.fetchWeReadStatus).mockRejectedValue(new Error("boom"));
    renderView();
    await waitFor(() => expect(screen.getByText("boom")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("clicking a book opens its highlights instead of WeRead directly", async () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    vi.mocked(api.fetchWeReadStatus).mockResolvedValue({ configured: true });
    vi.mocked(api.fetchWeReadShelf).mockResolvedValue({
      configured: true,
      count: 1,
      items: [
        {
          kind: "book",
          id: "b1",
          title: "三体",
          author: "刘慈欣",
          cover: null,
          category: "科幻",
          finished: false,
          top: false,
          deepLink: "weread://book/b1",
          updateTime: null,
          status: "reading",
          progress: 40,
          hasNote: true,
        },
      ],
    });
    vi.mocked(api.fetchWeReadBookNotes).mockResolvedValue({
      configured: true,
      book: { bookId: "b1", title: "三体", author: "刘慈欣", cover: null },
      count: 1,
      items: [
        {
          id: "bm:1",
          type: "highlight",
          text: "HIGHLIGHT_TEXT",
          quote: null,
          chapterUid: 1,
          chapterTitle: "Chapter 1",
          createTime: 0,
        },
      ],
    });

    renderView();
    await waitFor(() => expect(screen.getAllByText("三体").length).toBeGreaterThan(0));

    fireEvent.click(screen.getByText("三体", { selector: ".book-title" }));

    expect(openSpy).not.toHaveBeenCalled();
    await waitFor(() => expect(api.fetchWeReadBookNotes).toHaveBeenCalledWith("tok", "b1"));
    await waitFor(() => expect(screen.getByText("HIGHLIGHT_TEXT")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /open in weread/i })).toHaveAttribute(
      "href",
      "weread://book/b1",
    );

    openSpy.mockRestore();
  });

  it("the WeRead icon on the card opens WeRead directly without navigating to highlights", async () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    vi.mocked(api.fetchWeReadStatus).mockResolvedValue({ configured: true });
    vi.mocked(api.fetchWeReadShelf).mockResolvedValue({
      configured: true,
      count: 1,
      items: [
        {
          kind: "book",
          id: "b1",
          title: "三体",
          author: "刘慈欣",
          cover: null,
          category: "科幻",
          finished: false,
          top: false,
          deepLink: "weread://book/b1",
          updateTime: null,
          status: "reading",
          progress: null,
          hasNote: false,
        },
      ],
    });

    renderView();
    await waitFor(() => expect(screen.getAllByText("三体").length).toBeGreaterThan(0));

    fireEvent.click(screen.getByRole("button", { name: /open in weread/i }));

    expect(openSpy).toHaveBeenCalledWith("weread://book/b1", "_blank", "noopener,noreferrer");
    expect(api.fetchWeReadBookNotes).not.toHaveBeenCalled();

    openSpy.mockRestore();
  });
});
