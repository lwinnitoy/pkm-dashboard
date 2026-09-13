import { useEffect, useState } from "react";
import { api, getToken } from "../api/client";
import Login from "./Login";

type Gate = "loading" | "needauth" | "ok";

/**
 * Gates the app behind login when the backend requires it. When auth is disabled
 * (APP_PASSWORD unset) it renders through immediately. An expired token surfaces
 * as a 401 on the first data call, which the api client turns back into login.
 */
export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [gate, setGate] = useState<Gate>("loading");

  useEffect(() => {
    api
      .authStatus()
      .then((s) => setGate(!s.auth_required || getToken() ? "ok" : "needauth"))
      .catch(() => setGate("ok")); // backend unreachable — let the app surface the error
  }, []);

  if (gate === "loading") return <div className="login-screen muted">Loading…</div>;
  if (gate === "needauth") return <Login onSuccess={() => setGate("ok")} />;
  return <>{children}</>;
}
