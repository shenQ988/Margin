import { render, screen, waitFor } from "@testing-library/react";
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
});
