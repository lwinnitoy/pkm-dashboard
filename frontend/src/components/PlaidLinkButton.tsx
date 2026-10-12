import { useCallback, useEffect, useState } from "react";
import { usePlaidLink, type PlaidLinkOnSuccess } from "react-plaid-link";
import { api, errorText } from "../api/client";

interface Props {
  onLinked: () => void;
}

// react-plaid-link stashes the link token so we can resume after an OAuth bank
// redirect, which reloads the app at the registered redirect URI with
// ?oauth_state_id in the URL.
const TOKEN_KEY = "plaid_link_token";

// The URL the bank returned to, captured at page load: AppShell then forwards the
// return to /accounts, but Link has to be handed the address Plaid redirected to.
// Cleared once the link completes, so a later visit starts a fresh Link.
let oauthReturnUri: string | null =
  typeof window !== "undefined" && window.location.search.includes("oauth_state_id")
    ? window.location.href
    : null;

export default function PlaidLinkButton({ onLinked }: Props) {
  const [receivedRedirectUri] = useState(oauthReturnUri);
  // On an OAuth return, reuse the token created before the redirect.
  const [linkToken, setLinkToken] = useState<string | null>(
    receivedRedirectUri ? localStorage.getItem(TOKEN_KEY) : null,
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (receivedRedirectUri) return; // mid-OAuth: keep the existing token
    api
      .createLinkToken()
      .then((r) => {
        setLinkToken(r.link_token);
        localStorage.setItem(TOKEN_KEY, r.link_token);
      })
      .catch((e) => setError(errorText(e)));
  }, [receivedRedirectUri]);

  const onSuccess = useCallback<PlaidLinkOnSuccess>(
    async (public_token, metadata) => {
      if (!public_token) return;
      try {
        // institution_id lets the backend recognize a reconnect of a bank you
        // already linked, instead of duplicating all of its accounts.
        await api.exchangeToken(
          public_token,
          metadata.institution?.name ?? undefined,
          metadata.institution?.institution_id ?? undefined,
        );
        localStorage.removeItem(TOKEN_KEY);
        if (receivedRedirectUri) {
          oauthReturnUri = null;
          // Drop ?oauth_state_id so a refresh doesn't re-trigger Link.
          window.history.replaceState({}, "", window.location.pathname);
        }
        onLinked();
      } catch (e) {
        setError(errorText(e));
      }
    },
    [onLinked, receivedRedirectUri],
  );

  const { open, ready } = usePlaidLink({
    token: linkToken,
    onSuccess,
    ...(receivedRedirectUri ? { receivedRedirectUri } : {}),
  });

  // Automatically re-open Link when returning from the bank's OAuth page.
  useEffect(() => {
    if (receivedRedirectUri && ready) open();
  }, [receivedRedirectUri, ready, open]);

  if (error) return <span className="error">Link error: {error}</span>;

  return (
    <button className="btn-ghost btn" disabled={!ready || !linkToken} onClick={() => open()}>
      + Connect a bank
    </button>
  );
}
