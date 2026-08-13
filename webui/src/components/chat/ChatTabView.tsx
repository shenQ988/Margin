import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

import { ThreadShell } from "@/components/thread/ThreadShell";
import { useClient } from "@/providers/ClientProvider";
import type { ChatSummary } from "@/lib/types";

const CHAT_ID_STORAGE_KEY = "nanobot-webui.chat-id";

function readPersistedChatId(): string | null {
  try {
    return window.localStorage.getItem(CHAT_ID_STORAGE_KEY);
  } catch {
    return null;
  }
}

function persistChatId(chatId: string): void {
  try {
    window.localStorage.setItem(CHAT_ID_STORAGE_KEY, chatId);
  } catch {
    // ignore storage errors (private mode, etc.)
  }
}

export function ChatTabView({
  theme,
  onToggleTheme,
}: {
  theme: "light" | "dark";
  onToggleTheme: () => void;
}) {
  const { t } = useTranslation();
  const { client } = useClient();
  const [chatId, setChatId] = useState<string | null>(readPersistedChatId);

  const handleCreateChat = useCallback(async (): Promise<string | null> => {
    try {
      const id = await client.newChat();
      persistChatId(id);
      setChatId(id);
      return id;
    } catch (e) {
      console.error("Failed to create chat", e);
      return null;
    }
  }, [client]);

  const session: ChatSummary | null = chatId
    ? {
        key: `websocket:${chatId}`,
        channel: "websocket",
        chatId,
        createdAt: null,
        updatedAt: null,
        title: "",
        preview: "",
        workspaceScope: null,
      }
    : null;

  return (
    <ThreadShell
      session={session}
      title={t("chat.newChat")}
      onToggleSidebar={() => {}}
      hideSidebarToggleForHostChrome
      onCreateChat={handleCreateChat}
      theme={theme}
      onToggleTheme={onToggleTheme}
    />
  );
}
