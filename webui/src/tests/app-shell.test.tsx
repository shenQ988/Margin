import { render, screen } from "@testing-library/react";
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/AppShell";

vi.mock("@/components/bookshelf/BookshelfView", () => ({
  BookshelfView: () => <div data-testid="shelf-view" />,
}));
vi.mock("@/components/notes/NotesView", () => ({
  NotesView: () => <div data-testid="notes-view" />,
}));
vi.mock("@/components/chat/ChatTabView", () => ({
  ChatTabView: () => <div data-testid="ask-book-view" />,
}));
vi.mock("@/components/settings/SettingsView", () => ({
  SettingsView: () => <div data-testid="settings-view" />,
}));

function renderShell() {
  return render(<AppShell theme="light" onToggleTheme={() => {}} onLogout={() => {}} />);
}

describe("AppShell", () => {
  beforeEach(() => {
    window.location.hash = "";
  });

  it("defaults to the Shelf tab, mounts other panes lazily, and switches between all 4 tabs", () => {
    renderShell();

    // Only Shelf (the default tab) and Ask-Book (always-mounted, to preserve
    // in-flight chat state) exist in the DOM at first; Notes/Settings haven't
    // been visited yet, so they aren't mounted (avoids firing their fetches
    // concurrently with the initial WS handshake).
    expect(screen.getByRole("tab", { name: "Shelf" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("shelf-view").parentElement).not.toHaveClass("hidden");
    expect(screen.queryByTestId("notes-view")).not.toBeInTheDocument();
    expect(screen.queryByTestId("settings-view")).not.toBeInTheDocument();
    expect(screen.getByTestId("ask-book-view").parentElement).toHaveClass("hidden");

    act(() => {
      screen.getByRole("tab", { name: "Notes" }).click();
    });
    expect(window.location.hash).toBe("#/notes");
    expect(screen.getByTestId("notes-view").parentElement).not.toHaveClass("hidden");
    expect(screen.getByTestId("shelf-view").parentElement).toHaveClass("hidden");

    act(() => {
      screen.getByRole("tab", { name: "Ask-Book" }).click();
    });
    expect(window.location.hash).toBe("#/ask-book");
    expect(screen.getByTestId("ask-book-view").parentElement).not.toHaveClass("hidden");

    act(() => {
      screen.getByRole("tab", { name: "Setting" }).click();
    });
    expect(window.location.hash).toBe("#/settings");
    expect(screen.getByTestId("settings-view").parentElement).not.toHaveClass("hidden");

    // Once visited, a pane stays mounted (just hidden) when switching away.
    act(() => {
      screen.getByRole("tab", { name: "Shelf" }).click();
    });
    expect(screen.getByTestId("settings-view").parentElement).toHaveClass("hidden");
  });

  it("reads the initial tab from the URL hash", () => {
    window.location.hash = "#/notes";
    renderShell();
    expect(screen.getByRole("tab", { name: "Notes" })).toHaveAttribute("aria-selected", "true");
  });

  it("falls back to Shelf for an unknown hash", () => {
    window.location.hash = "#/unknown";
    renderShell();
    expect(screen.getByRole("tab", { name: "Shelf" })).toHaveAttribute("aria-selected", "true");
  });
});
