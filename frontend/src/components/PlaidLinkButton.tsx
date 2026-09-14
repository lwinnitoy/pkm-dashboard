import { useCallback, useEffect, useState } from "react";
import { usePlaidLink, type PlaidLinkOnSuccess } from "react-plaid-link";
import { api } from "../api/client";

interface Props {
  onLinked: () => void;
}

// react-plaid-link stashes the link token so we can resume after an OAuth bank
// redirect (e.g. RBC), which reloads the app at the registered redirect URI with
// ?oauth_state_id in the URL.
const TOKEN_KEY = "plaid_link_token";
const isOAuthReturn =
  typeof window !== "undefined" && window.location.search.includes("oauth_state_id");

export default function PlaidLinkButton({ onLinked }: Props) {
  // On an OAuth return, reuse the token created before the redirect.
  const [linkToken, setLinkToken] = useState<string | null>(
    isOAuthReturn ? localStorage.getItem(TOKEN_KEY) : null,
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOAuthReturn) return; // mid-OAuth: keep the existing token
    api
      .createLinkToken()
      .then((r) => {
        setLinkToken(r.link_token);
        localStorage.setItem(TOKEN_KEY, r.link_token);
      })
      .catch((e) => setError(String(e)));
  }, []);

  const onSuccess = useCallback<PlaidLinkOnSuccess>(
    async (public_token, metadata) => {
      if (!public_token) return;
      try {
        await api.exchangeToken(public_token, metadata.institution?.name ?? undefined);
        localStorage.removeItem(TOKEN_KEY);
        if (isOAuthReturn) {
          // Drop ?oauth_state_id so a refresh doesn't re-trigger Link.
          window.history.replaceState({}, "", window.location.pathname);
        }
        onLinked();
      } catch (e) {
        setError(String(e));
      }
    },
    [onLinked],
  );

  const { open, ready } = usePlaidLink({
    token: linkToken,
    onSuccess,
    ...(isOAuthReturn ? { receivedRedirectUri: window.location.href } : {}),
  });

  // Automatically re-open Link when returning from the bank's OAuth page.
  useEffect(() => {
    if (isOAuthReturn && ready) open();
  }, [ready, open]);

  if (error) return <span className="error">Link error: {error}</span>;

  return (
    <button className="btn-ghost btn" disabled={!ready || !linkToken} onClick={() => open()}>
      + Connect a bank
    </button>
  );
}
