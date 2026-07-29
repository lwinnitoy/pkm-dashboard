import { useCallback, useEffect, useState } from "react";
import { usePlaidLink, type PlaidLinkOnSuccess } from "react-plaid-link";
import { api } from "../api/client";

interface Props {
  onLinked: () => void;
}

// Fetches a link_token, opens Plaid Link, then exchanges the public_token.
export default function PlaidLinkButton({ onLinked }: Props) {
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .createLinkToken()
      .then((r) => setLinkToken(r.link_token))
      .catch((e) => setError(String(e)));
  }, []);

  const onSuccess = useCallback<PlaidLinkOnSuccess>(
    async (public_token, metadata) => {
      if (!public_token) return;
      try {
        await api.exchangeToken(public_token, metadata.institution?.name ?? undefined);
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
  });

  if (error) return <span className="error">Link error: {error}</span>;

  return (
    <button disabled={!ready || !linkToken} onClick={() => open()}>
      + Connect a bank
    </button>
  );
}
