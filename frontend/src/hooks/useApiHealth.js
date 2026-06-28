import { useCallback, useEffect, useState } from "react";
import { fetchTemplates } from "../api";

/**
 * Tracks the API base URL and a lightweight live/dead indicator for it,
 * backed by GET /templates. Re-checks whenever `checkApi` is called
 * explicitly (e.g. on blur of the API base input).
 */
export default function useApiHealth(initialBase) {
  const [apiBase, setApiBase] = useState(initialBase);
  const [status, setStatus] = useState({ state: "checking", text: "checking…" });

  const checkApi = useCallback(async (base) => {
    setStatus({ state: "checking", text: "checking…" });
    try {
      const data = await fetchTemplates(base);
      const count = Array.isArray(data?.templates) ? data.templates.length : "?";
      setStatus({ state: "ok", text: `live · ${count} template(s) registered` });
    } catch (err) {
      setStatus({ state: "bad", text: "unreachable — is the server running?" });
    }
  }, []);

  useEffect(() => {
    checkApi(apiBase);
    // Only run once on mount with the initial value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { apiBase, setApiBase, status, checkApi };
}
