import { useEffect, useState, type FormEvent } from "react";
import { api, type Repository, type RepositoryCheck, type WebhookSetup } from "../api";

const NAME_PATTERN = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;

function CopyField({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked (e.g. not a secure context): the value is still selectable.
    }
  }
  return (
    <div className="copy-field">
      <span className="muted">{label}</span>
      <div className="copy-row">
        <code>{value}</code>
        <button type="button" onClick={copy}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}

export default function AddRepoModal({
  onClose,
  onAdded,
}: {
  onClose: () => void;
  onAdded: (repo: Repository) => void;
}) {
  const [name, setName] = useState("");
  const [check, setCheck] = useState<RepositoryCheck | null>(null);
  const [repo, setRepo] = useState<Repository | null>(null);
  const [setup, setSetup] = useState<WebhookSetup | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.webhookSetup().then(setSetup).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Step 3: wait for GitHub's first delivery (the ping it sends when a webhook is saved).
  useEffect(() => {
    if (!repo || repo.last_event_at) return;
    const timer = setInterval(async () => {
      try {
        const latest = (await api.repos()).find((r) => r.id === repo.id);
        if (latest?.last_event_at) setRepo(latest);
      } catch {
        // Keep polling; a blip shouldn't end the setup.
      }
    }, 4000);
    return () => clearInterval(timer);
  }, [repo]);

  async function runCheck(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setCheck(null);
    try {
      setCheck(await api.checkRepo(name.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Check failed");
    } finally {
      setBusy(false);
    }
  }

  async function add() {
    if (!check) return;
    setBusy(true);
    setError(null);
    try {
      if (check.already_registered) {
        const existing = (await api.repos()).find((r) => r.full_name === check.full_name);
        if (existing) setRepo(existing);
      } else {
        const created = await api.addRepo(check.full_name);
        onAdded(created);
        setRepo(created);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add repository");
    } finally {
      setBusy(false);
    }
  }

  const step = repo ? 2 : 1;
  const nameValid = NAME_PATTERN.test(name.trim());

  return (
    <div className="overlay center-overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Add repository" onClick={(e) => e.stopPropagation()}>
        <div className="panel-head">
          <div>
            <div className="muted">Step {step} of 2</div>
            <h2>{step === 1 ? "Add a repository" : `Connect ${repo?.full_name}`}</h2>
          </div>
          <button className="link" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        {error && <p className="error">{error}</p>}

        {step === 1 && (
          <>
            <form onSubmit={runCheck} className="modal-form">
              <label>
                GitHub repository
                <input
                  placeholder="owner/repo, e.g. yeshashah1357/pr-guard-test"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    setCheck(null);
                  }}
                  autoFocus
                  required
                />
              </label>
              <button type="submit" disabled={!nameValid || busy}>
                {busy && !check ? "Checking…" : "Check on GitHub"}
              </button>
            </form>
            {name && !nameValid && <p className="muted">Use the form owner/repo.</p>}

            {check && (
              <div className={`check ${check.found ? "check-ok" : "check-warn"}`}>
                <strong>{check.found ? "✓ " : "⚠ "}{check.full_name}</strong>
                <span>{check.message}</span>
                {check.already_registered && <span>It's already registered; continue to see its webhook settings.</span>}
                {!check.found && (
                  <a href="https://github.com/settings/personal-access-tokens" target="_blank" rel="noreferrer">
                    Edit your token's repository access ↗
                  </a>
                )}
              </div>
            )}

            {check && (
              <div className="modal-actions">
                <button type="button" onClick={add} disabled={busy}>
                  {check.already_registered ? "Continue" : check.found ? "Add repository" : "Add anyway"}
                </button>
              </div>
            )}
          </>
        )}

        {step === 2 && repo && (
          <>
            <p className="muted">
              In this repository on GitHub, add a webhook with these settings. GitHub sends a test event as soon
              as you save it, and this window will show when it arrives.
            </p>
            <a
              className="button-link"
              href={`https://github.com/${repo.full_name}/settings/hooks/new`}
              target="_blank"
              rel="noreferrer"
            >
              Open webhook settings on GitHub ↗
            </a>

            {setup?.webhook_url ? (
              <CopyField label="Payload URL" value={setup.webhook_url} />
            ) : (
              <p className="check check-warn">
                No public URL is configured. Set PUBLIC_URL in the server's .env (your domain or tunnel URL), then
                use it + /api/webhooks/github.
              </p>
            )}
            <CopyField label="Content type" value={setup?.content_type ?? "application/json"} />
            <div className="copy-field">
              <span className="muted">Secret</span>
              <span>Paste the value of {setup?.secret_location ?? "GITHUB_WEBHOOK_SECRET in the server's .env file"}.</span>
            </div>
            <div className="copy-field">
              <span className="muted">Events</span>
              <span>Choose "Let me select individual events" and tick only {setup?.events.join(", ") ?? "Pull requests"}.</span>
            </div>

            <div className={`check ${repo.last_event_at ? "check-ok" : "check-wait"}`}>
              {repo.last_event_at ? (
                <strong>✓ Connected. GitHub reached PR Guard at {new Date(repo.last_event_at).toLocaleTimeString()}.</strong>
              ) : (
                <span>
                  <span className="spinner" aria-hidden /> Waiting for GitHub's first event…
                </span>
              )}
            </div>

            <div className="modal-actions">
              <button type="button" onClick={onClose}>
                {repo.last_event_at ? "Done" : "Finish later"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
