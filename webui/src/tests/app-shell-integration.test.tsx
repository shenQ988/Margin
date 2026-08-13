import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/AppShell";
import type { ConnectionStatus, NanobotClient } from "@/lib/nanobot-client";
import { ClientProvider } from "@/providers/ClientProvider";

vi.mock("@/components/bookshelf/BookshelfView", () => ({
  BookshelfView: () => <div data-testid="shelf-view" />,
}));
vi.mock("@/components/notes/NotesView", () => ({
  NotesView: () => <div data-testid="notes-view" />,
}));
vi.mock("@/components/settings/SettingsView", () => ({
  SettingsView: () => <div data-testid="settings-view" />,
}));

function makeClient() {
  const chatHandlers = new Map<string, Set<(ev: import("@/lib/types").InboundEvent) => void>>();
  const sendMessage = vi.fn();
  const canReconcileCanonicalCompletion = vi.fn(() => true);
  const reconcileCanonicalCompletion = vi.fn(() => true);
  return {
    status: "open" as ConnectionStatus,
    defaultChatId: null as string | null,
    onStatus: (handler: (s: ConnectionStatus) => void) => {
      handler("open");
      return () => {};
    },
    onRuntimeModelUpdate: () => () => {},
    getRunStartedAt: () => null,
    finishRunLocally: vi.fn(),
    hasUnsettledRun: () => false,
    getRunGeneration: () => 0,
    canReconcileCanonicalCompletion,
    reconcileCanonicalCompletion,
    getGoalState: () => undefined,
    onChat: (chatId: string, handler: (ev: import("@/lib/types").InboundEvent) => void) => {
      let handlers = chatHandlers.get(chatId);
      if (!handlers) {
        handlers = new Set();
        chatHandlers.set(chatId, handlers);
      }
      handlers.add(handler);
      return () => handlers?.delete(handler);
    },
    onError: () => () => {},
    onSessionUpdate: () => () => {},
    sendMessage,
    sendSystemCommand: vi.fn().mockResolvedValue(undefined),
    newChat: vi.fn(async () => "chat-created-1"),
    forkChat: vi.fn(),
    attach: vi.fn(),
    connect: vi.fn(),
    close: vi.fn(),
    updateUrl: vi.fn(),
  };
}

describe("AppShell Ask-Book tab (real ThreadShell, no mocks)", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.location.hash = "#/ask-book";
  });

  it("shows a working composer on the Ask-Book tab and creates a chat on first send", async () => {
    const client = makeClient();
    render(
      <ClientProvider client={client as unknown as NanobotClient} token="tok">
        <AppShell theme="light" onToggleTheme={() => {}} onLogout={() => {}} />
      </ClientProvider>,
    );

    const composer = await screen.findByLabelText("Message input");
    expect(composer).toBeEnabled();

    fireEvent.change(composer, { target: { value: "what's on my bookshelf?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(client.newChat).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(client.sendMessage).toHaveBeenCalledWith(
        "chat-created-1",
        "what's on my bookshelf?",
        undefined,
        expect.objectContaining({ turnId: expect.any(String) }),
      ),
    );
  });
});
