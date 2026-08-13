import { useRef, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function AuthForm({
  failed,
  onSecret,
}: {
  failed: boolean;
  onSecret: (secret: string) => void;
}) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [validationError, setValidationError] = useState<"required" | "invalid" | null>(
    failed ? "invalid" : null,
  );
  const errorMessage = validationError ? t(`app.auth.${validationError}`) : null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const secret = value.trim();
    if (!secret) {
      setValidationError("required");
      inputRef.current?.focus();
      return;
    }
    setSubmitting(true);
    onSecret(secret);
  };

  return (
    <div className="flex h-full w-full items-center justify-center px-6">
      <form onSubmit={handleSubmit} className="flex w-full max-w-sm flex-col gap-4">
        <div className="space-y-2">
          <h1 className="text-sm font-medium text-foreground">
            <label htmlFor="webui-access-password">{t("app.auth.label")}</label>
          </h1>
          <div className="relative">
            <Input
              ref={inputRef}
              id="webui-access-password"
              name="webui-access-password"
              type={passwordVisible ? "text" : "password"}
              autoComplete="current-password"
              value={value}
              onChange={(e) => {
                setValue(e.target.value);
                setValidationError(null);
              }}
              disabled={submitting}
              aria-invalid={validationError ? true : undefined}
              aria-describedby={validationError ? "webui-auth-error" : undefined}
              className="pr-10"
              autoFocus
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              disabled={submitting}
              aria-label={t(passwordVisible ? "app.auth.hidePassword" : "app.auth.showPassword")}
              aria-controls="webui-access-password"
              onClick={() => setPasswordVisible((visible) => !visible)}
              className="absolute right-1 top-1/2 h-8 w-8 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              {passwordVisible ? (
                <EyeOff className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              ) : (
                <Eye className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              )}
            </Button>
          </div>
          {errorMessage ? (
            <p id="webui-auth-error" role="alert" className="text-sm text-destructive">
              {errorMessage}
            </p>
          ) : null}
        </div>
        <Button type="submit" className="w-full" disabled={submitting}>
          {t("app.auth.submit")}
        </Button>
      </form>
    </div>
  );
}
