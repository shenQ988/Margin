import { useCallback, useEffect, useRef, useState } from "react";

import {
  BootstrapAuthRequiredError,
  clearSavedSecret,
  consumeUrlBootstrapSecret,
  deriveWsUrl,
  fetchBootstrap,
  loadSavedSecret,
  saveSecret,
} from "@/lib/bootstrap";
import { NanobotClient } from "@/lib/nanobot-client";
import { createRuntimeHost, toRuntimeSurface } from "@/lib/runtime";
import type { BootstrapResponse, RuntimeSurface } from "@/lib/types";

export type BootState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "auth"; failed?: boolean }
  | {
      status: "ready";
      client: NanobotClient;
      token: string;
      tokenExpiresAt: number | null;
      modelName: string | null;
      ingressLimits: BootstrapResponse["limits"] | null;
      runtimeSurface: RuntimeSurface;
    };

const TOKEN_REFRESH_MARGIN_MS = 30_000;
const TOKEN_REFRESH_MIN_DELAY_MS = 5_000;

function bootstrapTokenExpiresAt(expiresInSeconds: number): number {
  return Date.now() + Math.max(0, expiresInSeconds) * 1000;
}

function tokenRefreshDelayMs(expiresAt: number): number {
  const remaining = Math.max(0, expiresAt - Date.now());
  const margin = Math.min(TOKEN_REFRESH_MARGIN_MS, Math.max(1_000, remaining / 2));
  return Math.max(TOKEN_REFRESH_MIN_DELAY_MS, remaining - margin);
}

function isBootstrapAuthRequired(error: unknown): boolean {
  if (error instanceof BootstrapAuthRequiredError) return true;
  const msg = error instanceof Error ? error.message : String(error);
  return msg.includes("HTTP 401") || msg.includes("HTTP 403");
}

export function useBootstrapAuth(): {
  state: BootState;
  bootstrapWithSecret: (secret: string) => void;
  handleLogout: () => void;
} {
  const [state, setState] = useState<BootState>({ status: "loading" });
  const bootstrapSecretRef = useRef("");

  const refreshReadyClient = useCallback(
    async (client: NanobotClient, fallbackSurface: RuntimeSurface) => {
      const boot = await fetchBootstrap("", bootstrapSecretRef.current);
      const url = deriveWsUrl(boot.ws_path, boot.token, boot.ws_url);
      const runtimeSurface = boot.runtime_surface
        ? toRuntimeSurface(boot.runtime_surface)
        : fallbackSurface;
      const runtimeHost = createRuntimeHost(runtimeSurface, boot.runtime_capabilities);
      const tokenExpiresAt = boot.expires_in ? bootstrapTokenExpiresAt(boot.expires_in) : null;
      if (runtimeHost.socketFactory) {
        client.updateUrl(url, runtimeHost.socketFactory);
      } else {
        client.updateUrl(url);
      }
      client.updateMaxFrameBytes(boot.limits?.transport.max_frame_bytes);
      setState((current) =>
        current.status === "ready" && current.client === client
          ? {
              ...current,
              token: boot.api_token ?? "",
              tokenExpiresAt,
              modelName: boot.model_name ?? current.modelName,
              ingressLimits: boot.limits ?? current.ingressLimits,
              runtimeSurface,
            }
          : current,
      );
      return { token: boot.api_token ?? "", url };
    },
    [],
  );

  const bootstrapWithSecret = useCallback(
    (secret: string) => {
      (async () => {
        setState({ status: "loading" });
        try {
          const boot = await fetchBootstrap("", secret);
          if (secret) saveSecret(secret);
          const url = deriveWsUrl(boot.ws_path, boot.token, boot.ws_url);
          const runtimeSurface = toRuntimeSurface(boot.runtime_surface);
          const runtimeHost = createRuntimeHost(runtimeSurface, boot.runtime_capabilities);
          const client = new NanobotClient({
            url,
            maxFrameBytes: boot.limits?.transport.max_frame_bytes,
            socketFactory: runtimeHost.socketFactory,
            onReauth: async () => {
              try {
                const refreshed = await refreshReadyClient(client, runtimeSurface);
                return refreshed.url;
              } catch {
                return null;
              }
            },
          });
          bootstrapSecretRef.current = secret;
          client.connect();
          setState({
            status: "ready",
            client,
            token: boot.api_token ?? "",
            tokenExpiresAt: boot.expires_in ? bootstrapTokenExpiresAt(boot.expires_in) : null,
            modelName: boot.model_name ?? null,
            ingressLimits: boot.limits ?? null,
            runtimeSurface,
          });
        } catch (e) {
          if (isBootstrapAuthRequired(e)) {
            setState({ status: "auth", failed: !!secret });
          } else {
            setState({ status: "error", message: e instanceof Error ? e.message : String(e) });
          }
        }
      })();
    },
    [refreshReadyClient],
  );

  useEffect(() => {
    if (state.status !== "ready" || state.tokenExpiresAt === null) return;
    const client = state.client;
    const timer = window.setTimeout(async () => {
      try {
        await refreshReadyClient(client, state.runtimeSurface);
      } catch (e) {
        if (isBootstrapAuthRequired(e)) {
          setState({ status: "auth", failed: !!bootstrapSecretRef.current });
        }
      }
    }, tokenRefreshDelayMs(state.tokenExpiresAt));
    return () => window.clearTimeout(timer);
  }, [refreshReadyClient, state]);

  useEffect(() => {
    const saved = consumeUrlBootstrapSecret() || loadSavedSecret();
    bootstrapWithSecret(saved);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleLogout = useCallback(() => {
    if (state.status === "ready") {
      state.client.close();
    }
    clearSavedSecret();
    setState({ status: "auth" });
  }, [state]);

  return { state, bootstrapWithSecret, handleLogout };
}
