import { useCallback, useEffect, useState } from "react";
import { usePlaidLink, type PlaidLinkOnSuccess } from "react-plaid-link";
import { api, errorText } from "../api/client";

interface Props {
  onLinked: () => void;
  /** Repair this existing login (Plaid update mode) instead of linking a new bank. */
  itemId?: number;
  label?: string;
}

// The Link session in progress, kept so it can resume after an OAuth bank
// redirect, which reloads the app at the registered redirect URI with
// ?oauth_state_id in the URL. Written when Link opens (not on mount), because
// the Accounts page can hold several of these buttons at once.
const STORE_KEY = "plaid_link_token";

interface Pending {
  token: string;
  itemId: number | null;
}

function readPending(): Pending | null {
  const raw = localStorage.getItem(STORE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Pending;
  } catch {
    return { token: raw, itemId: null }; // stored by an older build: a plain token
  }
}

// The URL the bank returned to, captured at page load: AppShell then forwards the
// return to /accounts, but Link has to be handed the address Plaid redirected to.
// Cleared once the link completes, so a later visit starts a fresh Link.
let oauthReturnUri: string | null =
  typeof window !== "undefined" && window.location.search.includes("oauth_state_id")
    ? window.location.href
    : null;

export default function PlaidLinkButton({ onLinked, itemId, label }: Props) {
  const mode = itemId ?? null;
  // Resume only in the button that started the flow (same new-link/update target).
  const [resume] = useState(() => {
    if (!oauthReturnUri) return null;
    const pending = readPending();
    return pending && pending.itemId === mode ? { uri: oauthReturnUri, token: pending.token } : null;
  });
  const [linkToken, setLinkToken] = useState<string | null>(resume?.token ?? null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (resume) return; // mid-OAuth: keep the token Link started with
    api
      .createLinkToken(mode ?? undefined)
      .then((r) => setLinkToken(r.link_token))
      .catch((e) => setError(errorText(e)));
  }, [resume, mode]);

  const onSuccess = useCallback<PlaidLinkOnSuccess>(
    async (public_token, metadata) => {
      try {
        // Update mode repairs the existing Item in place: nothing to exchange.
        if (mode == null) {
          if (!public_token) return;
          // institution_id lets the backend recognize a reconnect of a bank you
          // already linked, instead of duplicating all of its accounts.
          await api.exchangeToken(
            public_token,
            metadata.institution?.name ?? undefined,
            metadata.institution?.institution_id ?? undefined,
          );
        }
        localStorage.removeItem(STORE_KEY);
        if (resume) {
          oauthReturnUri = null;
          // Drop ?oauth_state_id so a refresh doesn't re-trigger Link.
          window.history.replaceState({}, "", window.location.pathname);
        }
        onLinked();
      } catch (e) {
        setError(errorText(e));
      }
    },
    [onLinked, mode, resume],
  );

  const { open, ready } = usePlaidLink({
    token: linkToken,
    onSuccess,
    ...(resume ? { receivedRedirectUri: resume.uri } : {}),
  });

  // Automatically re-open Link when returning from the bank's OAuth page.
  useEffect(() => {
    if (resume && ready) open();
  }, [resume, ready, open]);

  if (error) return <span className="error">Link error: {error}</span>;

  return (
    <button
      className="btn-ghost btn"
      disabled={!ready || !linkToken}
      onClick={() => {
        if (linkToken) {
          const pending: Pending = { token: linkToken, itemId: mode };
          localStorage.setItem(STORE_KEY, JSON.stringify(pending));
        }
        open();
      }}
    >
      {label ?? (mode == null ? "+ Connect a bank" : "Reconnect")}
    </button>
  );
}
