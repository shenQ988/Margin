import { useTranslation } from "react-i18next";

import { AppShell } from "@/components/AppShell";
import { AuthForm } from "@/components/AuthForm";
import { useBootstrapAuth } from "@/hooks/useBootstrapAuth";
import { ThemeProvider, useTheme } from "@/hooks/useTheme";
import { ClientProvider } from "@/providers/ClientProvider";

export default function App() {
  const { t } = useTranslation();
  const { state, bootstrapWithSecret, handleLogout } = useBootstrapAuth();
  const { theme, toggle } = useTheme();

  if (state.status === "loading") {
    return (
      <div className="flex h-full w-full items-center justify-center">
        <div className="flex flex-col items-center gap-3 animate-in fade-in-0 duration-300">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-foreground/40" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-foreground/60" />
            </span>
            {t("app.loading.connecting")}
          </div>
        </div>
      </div>
    );
  }

  if (state.status === "auth") {
    return <AuthForm failed={!!state.failed} onSecret={(s) => bootstrapWithSecret(s)} />;
  }

  if (state.status === "error") {
    return (
      <div className="flex h-full w-full items-center justify-center px-4 text-center">
        <div className="flex max-w-md flex-col items-center gap-3">
          <p className="text-lg font-semibold">{t("app.error.title")}</p>
          <p className="text-sm text-muted-foreground">{state.message}</p>
          <p className="text-xs text-muted-foreground">{t("app.error.gatewayHint")}</p>
        </div>
      </div>
    );
  }

  return (
    <ClientProvider
      client={state.client}
      token={state.token}
      modelName={state.modelName}
      ingressLimits={state.ingressLimits}
    >
      <ThemeProvider theme={theme}>
        <AppShell theme={theme} onToggleTheme={toggle} onLogout={handleLogout} />
      </ThemeProvider>
    </ClientProvider>
  );
}
