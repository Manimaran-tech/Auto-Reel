import { useEffect, useMemo, useState } from "react";

/* ── Stage Metadata ──────────────────────────────────────────── */
const STAGE_META = [
  { key: "queued", label: "Queued", icon: "⏳" },
  { key: "scraper", label: "Scraping Product", icon: "🔍" },
  { key: "copywriter", label: "Writing Script", icon: "✍️" },
  { key: "voice_engine", label: "Generating Voice", icon: "🎙️" },
  { key: "video_renderer", label: "Rendering Video", icon: "🎬" },
  { key: "completed", label: "Completed", icon: "✅" },
];
const STAGES = STAGE_META.map((s) => s.key);

/* ── Simple Client-Side Router ───────────────────────────────── */
function useRoute() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const handler = () => setPath(window.location.pathname);
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, []);
  const navigate = (next) => {
    if (next !== path) {
      window.history.pushState({}, "", next);
      setPath(next);
    }
  };
  return { path, navigate };
}

/* ═══════════════════════════════════════════════════════════════
   APP SHELL
   ═══════════════════════════════════════════════════════════════ */
export default function App() {
  const { path, navigate } = useRoute();
  const [authStatus, setAuthStatus] = useState("loading");

  useEffect(() => {
    fetch("/api/settings")
      .then((r) => r.json())
      .then((data) => {
        if (data.instagram_connected) setAuthStatus("authed");
        else setAuthStatus("unauthed");
      })
      .catch(() => setAuthStatus("unauthed"));
  }, []);

  const view = path.startsWith("/analytics")
    ? "analytics"
    : path.startsWith("/settings")
      ? "settings"
      : "generator";

  if (authStatus === "loading") {
    return <div className="app-layout" style={{ justifyContent: "center", alignItems: "center" }}>Loading workspace...</div>;
  }

  if (authStatus === "unauthed") {
    return <LoginPage onLogin={() => setAuthStatus("authed")} />;
  }

  return (
    <div className="app-layout">
      {/* ── Sidebar ────────────────────────────────────────── */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="logo-text">AutoReel AI</div>
          <div className="logo-sub">Marketing Agent</div>
        </div>

        <nav className="sidebar-nav">
          <span className="nav-label">Workspace</span>
          <button
            className={`nav-item ${view === "generator" ? "active" : ""}`}
            onClick={() => navigate("/")}
          >
            <span className="nav-icon">⚡</span>
            Reel Generator
          </button>
          <button
            className={`nav-item ${view === "analytics" ? "active" : ""}`}
            onClick={() => navigate("/analytics")}
          >
            <span className="nav-icon">📊</span>
            Analytics
          </button>

          <span className="nav-label">Resources</span>
          <button className="nav-item" disabled>
            <span className="nav-icon">📁</span>
            Past Reels
          </button>
          <button
            className={`nav-item ${view === "settings" ? "active" : ""}`}
            onClick={() => navigate("/settings")}
          >
            <span className="nav-icon">⚙️</span>
            Settings
          </button>
        </nav>

        <div className="sidebar-footer">
          <span className="version">
            <span className="status-dot" />
            Ollama Connected
          </span>
        </div>
      </aside>

      {/* ── Main Content ──────────────────────────────────── */}
      <div className="main-content">
        {view === "analytics" ? (
          <AnalyticsPage />
        ) : view === "settings" ? (
          <SettingsPage />
        ) : (
          <GeneratorPage />
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   GENERATOR PAGE
   ═══════════════════════════════════════════════════════════════ */
function GeneratorPage() {
  const [url, setUrl] = useState("");
  const [jobId, setJobId] = useState("");
  const [status, setStatus] = useState({
    status: "idle",
    stage: "queued",
    progress: 0,
    artifacts: {},
    error: "",
  });
  const [busy, setBusy] = useState(false);
  const [distMsg, setDistMsg] = useState("");
  const [sessionOk, setSessionOk] = useState(null);

  /* Check Instagram session on mount */
  useEffect(() => {
    fetch("/api/ig-session/status")
      .then((r) => r.json())
      .then((d) => setSessionOk(d.valid))
      .catch(() => setSessionOk(false));
  }, []);

  /* Poll for job status */
  useEffect(() => {
    if (!jobId) return;
    let timer;
    const poll = async () => {
      try {
        const res = await fetch(`/api/status/${jobId}`);
        if (!res.ok) throw new Error("Failed to fetch status");
        const data = await res.json();
        setStatus(data);
        if (data.status === "completed" || data.status === "failed") {
          setBusy(false);
          return;
        }
        timer = setTimeout(poll, 1500);
      } catch {
        setBusy(false);
      }
    };
    timer = setTimeout(poll, 500);
    return () => clearTimeout(timer);
  }, [jobId]);

  const stageIdx = Math.max(STAGES.indexOf(status.stage), 0);
  const caption = status.artifacts?.caption_text ?? "";
  const videoUrl = status.artifacts?.video ? `/api/video/${jobId}` : "";

  const generate = async () => {
    if (!url.trim()) return;
    setBusy(true);
    setDistMsg("");
    setStatus({ status: "queued", stage: "queued", progress: 5, artifacts: {}, error: "" });
    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim() }),
      });
      if (!res.ok) throw new Error("Failed to start");
      const data = await res.json();
      setJobId(data.job_id);
    } catch (err) {
      setBusy(false);
      setStatus((p) => ({ ...p, status: "failed", error: String(err) }));
    }
  };

  const distribute = async () => {
    if (!jobId || !videoUrl) return;
    if (sessionOk === false) {
      setDistMsg("⚠️ No Instagram session! Go to Settings → Open Instagram Login first.");
      return;
    }
    setDistMsg("Posting to Instagram…");
    try {
      const res = await fetch(`/api/distribute/${jobId}`, { method: "POST" });
      const data = await res.json();
      setDistMsg(data.message || "Done.");
    } catch (err) {
      setDistMsg(`Failed: ${err}`);
    }
  };

  const copyCaption = async () => {
    if (caption) await navigator.clipboard.writeText(caption);
  };

  const statusLabel = useMemo(() => {
    if (status.status === "failed") return `Error: ${status.error || "Unknown"}`;
    if (status.status === "completed") return "Reel ready — preview, download, or post to Instagram";
    const meta = STAGE_META.find((s) => s.key === status.stage);
    return meta ? `${meta.icon} ${meta.label}…` : "Waiting…";
  }, [status]);

  return (
    <div className="gap-stack fade-in">
      <div className="page-header">
        <h1>⚡ Reel Generator</h1>
        <p className="page-desc">
          Paste any Amazon, Shopify, or Flipkart product URL to generate a viral Instagram Reel.
        </p>
      </div>

      {/* URL Input + Pipeline */}
      <div className="grid-2">
        <div className="card fade-in fade-in-d1">
          <div className="card-header">
            <h2>Product URL</h2>
            <span className={`card-badge badge-${status.status}`}>
              {status.status || "idle"}
            </span>
          </div>

          <div className="input-group">
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              type="url"
              placeholder="https://amazon.in/dp/B0XXXXX"
              onKeyDown={(e) => e.key === "Enter" && generate()}
            />
            <button className="btn btn-primary" disabled={busy} onClick={generate}>
              {busy ? "Working…" : "Generate"}
            </button>
          </div>

          <div style={{ marginTop: "1rem" }}>
            <div className="progress-track">
              <div
                className="progress-fill"
                style={{ width: `${Math.max(status.progress || 0, 3)}%` }}
              />
            </div>
            <p className="text-muted" style={{ marginTop: ".5rem" }}>{statusLabel}</p>
          </div>

          <div className="pipeline-steps">
            {STAGE_META.map((stage, i) => (
              <div
                key={stage.key}
                className={`pipeline-step ${i < stageIdx ? "done" : i === stageIdx ? "active" : ""}`}
              >
                <span className="step-dot" />
                <span>{stage.icon} {stage.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Video Preview */}
        <div className="card fade-in fade-in-d2">
          <div className="card-header">
            <h2>Preview</h2>
          </div>
          <div className="video-container">
            {videoUrl ? (
              <video src={videoUrl} controls playsInline />
            ) : (
              <div className="video-empty">
                <div className="video-icon">🎬</div>
                <p>Your generated reel will appear here</p>
              </div>
            )}
          </div>

          <div className="btn-row" style={{ marginTop: "1rem" }}>
            <a
              className={`btn btn-secondary ${!videoUrl ? "disabled" : ""}`}
              href={videoUrl || "#"}
              download={videoUrl ? `autoreel_${jobId}.mp4` : undefined}
              style={{ textDecoration: "none" }}
            >
              ↓ Download MP4
            </a>
            <button className="btn btn-ghost" onClick={distribute} disabled={!videoUrl}>
              📤 Post to Instagram
            </button>
            {sessionOk === false && videoUrl && (
              <span className="text-muted" style={{ fontSize: '.85rem', color: 'var(--warning, #f59e0b)' }}>⚠️ No IG session</span>
            )}
            <button className="btn btn-ghost" onClick={copyCaption} disabled={!caption}>
              📋 Copy Caption
            </button>
          </div>

          {distMsg && <p className="text-muted" style={{ marginTop: ".5rem" }}>{distMsg}</p>}
        </div>
      </div>

      {/* Caption */}
      <div className="card fade-in fade-in-d3">
        <div className="card-header">
          <h2>Generated Caption</h2>
        </div>
        <textarea
          value={caption}
          readOnly
          rows={4}
          placeholder="AI-generated Instagram caption with hashtags will appear here…"
        />
      </div>

      {/* Instagram Info Banner */}
      <div className="info-banner fade-in fade-in-d4">
        <span className="info-icon">ℹ️</span>
        <div>
          <strong>How Instagram posting works:</strong> Your credentials stay 100% local on your
          machine. When you click "Post to Instagram", we open a browser window using your saved
          session, upload the video with your caption + product link, and post it directly.
          Nothing is sent to any external server.
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   ANALYTICS PAGE
   ═══════════════════════════════════════════════════════════════ */
function AnalyticsPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/analytics");
      setData(await res.json());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const refreshStrategy = async () => {
    setRefreshing(true);
    try {
      await fetch("/api/analytics/refresh-strategy", { method: "POST" });
      await load();
    } finally {
      setRefreshing(false);
    }
  };

  const totals = data?.totals ?? {};
  const series = data?.timeseries ?? [];
  const strategy = data?.strategy ?? {};
  const maxVal = Math.max(...series.map((s) => Math.max(s.views || 0, s.clicks || 0, 1)), 1);

  return (
    <div className="gap-stack fade-in">
      <div className="page-header">
        <h1>📊 Analytics Dashboard</h1>
        <p className="page-desc">
          Track reel performance, monitor the AI's current marketing strategy, and trigger learning
          updates.
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid-5 fade-in fade-in-d1">
        <KPI label="Total Videos" value={totals.videos ?? 0} />
        <KPI label="Total Views" value={(totals.views ?? 0).toLocaleString()} />
        <KPI label="Total Clicks" value={(totals.clicks ?? 0).toLocaleString()} />
        <KPI
          label="Avg Watch %"
          value={`${totals.avg_watch_time_pct ?? 0}%`}
          change={totals.avg_watch_time_pct > 50 ? "up" : totals.avg_watch_time_pct > 0 ? "down" : "flat"}
          changeText={totals.avg_watch_time_pct > 50 ? "Good retention" : totals.avg_watch_time_pct > 0 ? "Needs work" : "—"}
        />
        <KPI
          label="CTR"
          value={`${totals.ctr ?? 0}%`}
          change={totals.ctr > 2 ? "up" : totals.ctr > 0 ? "down" : "flat"}
          changeText={totals.ctr > 2 ? "Above average" : totals.ctr > 0 ? "Below 2%" : "—"}
        />
      </div>

      {/* Chart + Strategy */}
      <div className="grid-2">
        {/* Bar Chart */}
        <div className="card fade-in fade-in-d2">
          <div className="card-header">
            <h2>Views vs Clicks (7 Days)</h2>
          </div>
          {series.length === 0 ? (
            <div className="empty-state">
              <p>No data yet. Ingest metrics after posting reels to see trends.</p>
            </div>
          ) : (
            <>
              <div className="chart-container">
                {series.map((item) => (
                  <div className="chart-col" key={item.date}>
                    <div className="chart-bars">
                      <span
                        className="chart-bar views"
                        style={{ height: `${((item.views || 0) / maxVal) * 140 + 4}px` }}
                        title={`${item.views} views`}
                      />
                      <span
                        className="chart-bar clicks"
                        style={{ height: `${((item.clicks || 0) / maxVal) * 140 + 4}px` }}
                        title={`${item.clicks} clicks`}
                      />
                      <span
                        className="chart-bar conversions"
                        style={{ height: `${((item.conversions || 0) / maxVal) * 140 + 4}px` }}
                        title={`${item.conversions} conversions`}
                      />
                    </div>
                    <span className="chart-label">{item.date?.slice(5) || "—"}</span>
                  </div>
                ))}
              </div>
              <div className="chart-legend">
                <span className="legend-item">
                  <span className="legend-dot" style={{ background: "var(--accent)" }} /> Views
                </span>
                <span className="legend-item">
                  <span className="legend-dot" style={{ background: "var(--pink)" }} /> Clicks
                </span>
                <span className="legend-item">
                  <span className="legend-dot" style={{ background: "var(--green)" }} /> Conversions
                </span>
              </div>
            </>
          )}
        </div>

        {/* AI Strategy Card */}
        <div className="card fade-in fade-in-d3">
          <div className="card-header">
            <h2>🧠 AI Strategy</h2>
            <button className="btn btn-secondary" onClick={refreshStrategy} disabled={refreshing}>
              {refreshing ? "Analyzing…" : "↻ Refresh"}
            </button>
          </div>

          <div className="strategy-display">
            <div className="strategy-label">Current Copywriting Rule</div>
            <div className="strategy-text">
              {strategy.current_rule || "No strategy loaded yet."}
            </div>
          </div>

          <p className="strategy-rationale">
            <strong>Rationale:</strong>{" "}
            {strategy.rationale || "Strategy rationale will appear after the AI analyzes your reel performance data."}
          </p>

          <p className="text-muted" style={{ marginTop: ".8rem" }}>
            Last updated: {strategy.updated_at || "—"}
          </p>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   LOGIN PAGE
   ═══════════════════════════════════════════════════════════════ */
function LoginPage({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!username || !password) return;
    setLoading(true);
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instagram_username: username, instagram_password: password }),
    });
    if (res.ok) {
      onLogin();
    } else {
      setLoading(false);
      alert("Failed to save credentials.");
    }
  };

  return (
    <div className="app-layout" style={{ justifyContent: "center", alignItems: "center", padding: "1rem" }}>
      <div className="card fade-in" style={{ maxWidth: 400, width: "100%", padding: "2.5rem" }}>
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <div className="logo-text" style={{ fontSize: "1.8rem", marginBottom: ".5rem" }}>AutoReel AI</div>
          <p className="text-muted">Enter your Instagram credentials to connect your workspace. Your data is stored securely on your local device.</p>
        </div>

        <form onSubmit={handleLogin} className="gap-stack">
          <div>
            <label className="text-muted" style={{ display: "block", marginBottom: ".5rem" }}>Instagram Username</label>
            <div className="input-group">
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="@your_handle"
                required
              />
            </div>
          </div>
          <div>
            <label className="text-muted" style={{ display: "block", marginBottom: ".5rem" }}>Password</label>
            <div className="input-group">
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
            </div>
          </div>
          <button type="submit" className="btn btn-primary" style={{ width: "100%", padding: "1rem", marginTop: ".5rem" }} disabled={loading}>
            {loading ? "Connecting..." : "Connect Account"}
          </button>
        </form>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   SETTINGS PAGE
   ═══════════════════════════════════════════════════════════════ */
function SettingsPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [saved, setSaved] = useState(false);
  const [connected, setConnected] = useState(false);
  const [currentUser, setCurrentUser] = useState("");
  const [model, setModel] = useState("");
  const [voice, setVoice] = useState("");
  const [sessionStatus, setSessionStatus] = useState(null);
  const [loginLoading, setLoginLoading] = useState(false);

  const checkSession = () => {
    fetch("/api/ig-session/status")
      .then((r) => r.json())
      .then((d) => setSessionStatus(d))
      .catch(() => setSessionStatus({ valid: false, message: "Failed to check session." }));
  };

  useEffect(() => {
    fetch("/api/settings")
      .then((r) => r.json())
      .then((data) => {
        setConnected(data.instagram_connected);
        setCurrentUser(data.instagram_username || "");
        setModel(data.ollama_model || "");
        setVoice(data.tts_voice || "");
      })
      .catch(() => { });
    checkSession();
  }, []);

  const openInstagramLogin = async () => {
    setLoginLoading(true);
    try {
      const res = await fetch("/api/ig-session/login", { method: "POST" });
      const data = await res.json();
      if (data.success) {
        setSessionStatus({ valid: true, message: data.message });
      } else {
        setSessionStatus({ valid: false, message: data.message || data.detail || "Login failed." });
      }
    } catch (err) {
      setSessionStatus({ valid: false, message: `Error: ${err}` });
    } finally {
      setLoginLoading(false);
    }
  };

  const saveCredentials = async () => {
    setSaved(false);
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instagram_username: username, instagram_password: password }),
    });
    if (res.ok) {
      setSaved(true);
      setConnected(true);
      setCurrentUser(username);
      setPassword("");
      setTimeout(() => setSaved(false), 3000);
    }
  };

  return (
    <div className="gap-stack fade-in">
      <div className="page-header">
        <h1>⚙️ Settings</h1>
        <p className="page-desc">Configure Instagram credentials and view system info.</p>
      </div>

      <div className="grid-2">
        {/* Instagram Credentials */}
        <div className="card fade-in fade-in-d1">
          <div className="card-header">
            <h2>Instagram Account</h2>
            <span className={`card-badge ${connected ? "badge-completed" : "badge-idle"}`}>
              {connected ? "Connected" : "Not Set"}
            </span>
          </div>

          {connected && (
            <div className="info-banner" style={{ marginBottom: "1rem" }}>
              <span className="info-icon">✅</span>
              <div>Currently configured: <strong>@{currentUser}</strong></div>
            </div>
          )}

          <div className="gap-stack">
            <div>
              <label className="text-muted" style={{ display: "block", marginBottom: ".3rem" }}>Username</label>
              <div className="input-group">
                <input
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="your_instagram_handle"
                />
              </div>
            </div>
            <div>
              <label className="text-muted" style={{ display: "block", marginBottom: ".3rem" }}>Password</label>
              <div className="input-group">
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                />
              </div>
            </div>
            <button
              className="btn btn-primary"
              onClick={saveCredentials}
              disabled={!username || !password}
            >
              {saved ? "✓ Saved!" : "Save Credentials"}
            </button>
          </div>

          {/* ── Instagram Session ─────────────────────── */}
          <div style={{ marginTop: "1.5rem", paddingTop: "1.5rem", borderTop: "1px solid var(--border, #333)" }}>
            <h3 style={{ margin: "0 0 .8rem 0", fontSize: "1rem", fontWeight: 600 }}>Instagram Session</h3>

            {sessionStatus && (
              <div className="info-banner" style={{ marginBottom: "1rem" }}>
                <span className="info-icon">{sessionStatus.valid ? "✅" : "⚠️"}</span>
                <div>{sessionStatus.message}</div>
              </div>
            )}

            <button
              className="btn btn-secondary"
              onClick={openInstagramLogin}
              disabled={loginLoading || !connected}
              style={{ width: "100%" }}
            >
              {loginLoading ? "Browser open — log in manually…" : "🔐 Open Instagram Login"}
            </button>
            <p className="text-muted" style={{ marginTop: ".5rem", fontSize: ".85rem" }}>
              Opens a real browser where you log in once. The session is saved locally so "Post to Instagram" works without CAPTCHAs.
            </p>
          </div>

          <div className="info-banner" style={{ marginTop: "1rem" }}>
            <span className="info-icon">🔒</span>
            <div>
              Your credentials are stored <strong>in-memory only</strong> for this session.
              They are never saved to disk or sent to any external server.
              When you restart the backend, you'll need to re-enter them.
            </div>
          </div>
        </div>

        {/* System Info */}
        <div className="card fade-in fade-in-d2">
          <div className="card-header">
            <h2>System Info</h2>
          </div>
          <div className="gap-stack">
            <div className="kpi-card">
              <span className="kpi-label">LLM Model</span>
              <span className="kpi-value" style={{ fontSize: "1.1rem" }}>{model || "—"}</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">TTS Voice</span>
              <span className="kpi-value" style={{ fontSize: "1.1rem" }}>{voice || "—"}</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">Video Format</span>
              <span className="kpi-value" style={{ fontSize: "1.1rem" }}>1080×1920 (9:16)</span>
            </div>
            <div className="kpi-card">
              <span className="kpi-label">Cost</span>
              <span className="kpi-value" style={{ fontSize: "1.1rem" }}>$0.00</span>
              <span className="kpi-change up">↑ 100% Free</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── KPI Metric Card Component ───────────────────────────────── */
function KPI({ label, value, change, changeText }) {
  return (
    <div className="kpi-card">
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
      {changeText && (
        <span className={`kpi-change ${change || "flat"}`}>
          {change === "up" ? "↑" : change === "down" ? "↓" : "—"} {changeText}
        </span>
      )}
    </div>
  );
}
