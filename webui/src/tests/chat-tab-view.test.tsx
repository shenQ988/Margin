import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatTabView } from "@/components/chat/ChatTabView";
import type { NanobotClient } from "@/lib/nanobot-client";
import type { ChatSummary } from "@/lib/types";
import { ClientProvider } from "@/providers/ClientProvider";

let capturedOnCreateChat:
  | ((scope?: unknown, initialMessage?: string) => Promise<string | null>)
  | null = null;

vi.mock("@/components/thread/ThreadShell", () => ({
  ThreadShell: ({
    session,
    onCreateChat,
  }: {
    session: ChatSummary | null;
    onCreateChat?: (scope?: unknown, initialMessage?: string) => Promise<string | null>;
  }) => {
    capturedOnCreateChat = onCreateChat ?? null;
    return <div data-testid="thread-shell">{session ? session.chatId : "no-session"}</div>;
  },
}));

const CHAT_ID_STORAGE_KEY = "nanobot-webui.chat-id";

function fakeClient(newChatId: string) {
  return {
    newChat: vi.fn(async () => newChatId),
  };
}

describe("ChatTabView", () => {
  beforeEach(() => {
    window.localStorage.clear();
    capturedOnCreateChat = null;
  });

  it("renders with no session and does not eagerly call newChat", async () => {
    const client = fakeClient("chat-abc");
    render(
      <ClientProvider client={client as unknown as NanobotClient} token="tok">
        <ChatTabView theme="light" onToggleTheme={() => {}} />
      </ClientProvider>,
    );

    expect(screen.getByTestId("thread-shell")).toHaveTextContent("no-session");
    expect(client.newChat).not.toHaveBeenCalled();
  });

  it("creates and persists a chat when onCreateChat is invoked (first send)", async () => {
    const client = fakeClient("chat-abc");
    render(
      <ClientProvider client={client as unknown as NanobotClient} token="tok">
        <ChatTabView theme="light" onToggleTheme={() => {}} />
      </ClientProvider>,
    );

    expect(capturedOnCreateChat).toBeTypeOf("function");
    const id = await capturedOnCreateChat?.();
    expect(id).toBe("chat-abc");
    expect(client.newChat).toHaveBeenCalledTimes(1);
    expect(window.localStorage.getItem(CHAT_ID_STORAGE_KEY)).toBe("chat-abc");
    await waitFor(() => expect(screen.getByTestId("thread-shell")).toHaveTextContent("chat-abc"));
  });

  it("reuses a persisted chat id without calling newChat", async () => {
    window.localStorage.setItem(CHAT_ID_STORAGE_KEY, "chat-existing");
    const client = fakeClient("chat-new");
    render(
      <ClientProvider client={client as unknown as NanobotClient} token="tok">
        <ChatTabView theme="light" onToggleTheme={() => {}} />
      </ClientProvider>,
    );

    expect(screen.getByTestId("thread-shell")).toHaveTextContent("chat-existing");
    expect(client.newChat).not.toHaveBeenCalled();
  });
});
