import { useCallback, useEffect, useRef, useState } from 'react';
import './App.css';
import { ApiError, fetchEventStats, fetchPlugins, fetchRecentEvents, submitTestEvent } from './api';
import type { TestEventInput } from './api';
import type { EventStats, PluginInfo, RecentEvent } from './types';

const POLL_INTERVAL_MS = 4000;

const EVENT_TYPES = ['person_detected', 'vehicle_detected', 'loitering', 'motion'];

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className="confidence-bar-wrap">
      <div className="confidence-bar">
        <div className="confidence-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span>{pct}%</span>
    </div>
  );
}

function App() {
  const [apiKey, setApiKey] = useState('');
  const [events, setEvents] = useState<RecentEvent[]>([]);
  const [stats, setStats] = useState<EventStats | null>(null);
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [loadedOnce, setLoadedOnce] = useState(false);

  const [form, setForm] = useState<TestEventInput>({
    camera_id: 'cam-demo-01',
    event_type: 'person_detected',
    confidence: 0.92,
    zone: 'lobby',
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitMessage, setSubmitMessage] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const apiKeyRef = useRef(apiKey);
  apiKeyRef.current = apiKey;

  const refresh = useCallback(async () => {
    const key = apiKeyRef.current;
    if (!key) {
      setConnected(false);
      return;
    }
    try {
      const [recent, eventStats, pluginList] = await Promise.all([
        fetchRecentEvents(key, 50),
        fetchEventStats(key),
        fetchPlugins(key),
      ]);
      setEvents(recent);
      setStats(eventStats);
      setPlugins(pluginList);
      setConnected(true);
      setConnectionError(null);
    } catch (err) {
      setConnected(false);
      setConnectionError(err instanceof ApiError ? err.message : 'Could not reach the API');
    } finally {
      setLoadedOnce(true);
    }
  }, []);

  useEffect(() => {
    if (!apiKey) {
      setLoadedOnce(false);
      return;
    }
    refresh();
    const id = window.setInterval(refresh, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [apiKey, refresh]);

  async function handleSubmitTestEvent(e: React.FormEvent) {
    e.preventDefault();
    if (!apiKey) {
      setSubmitError('Enter an API key above first.');
      return;
    }
    setSubmitting(true);
    setSubmitMessage(null);
    setSubmitError(null);
    try {
      const result = await submitTestEvent(apiKey, form);
      setSubmitMessage(
        `Accepted: ${result.event.event_type} on ${result.event.camera_id}. Refreshing table...`,
      );
      await refresh();
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : 'Failed to submit test event');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>Vision Platform Admin Dashboard</h1>
        <p>Live view of recently normalized detection events and the active delivery plugins.</p>
      </header>

      <section className="card connection-bar">
        <label htmlFor="api-key">X-API-Key</label>
        <input
          id="api-key"
          type="password"
          placeholder="Paste a dev API key minted via scripts/create_api_key.py"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          autoComplete="off"
        />
        {loadedOnce &&
          (connected ? (
            <span className="status-pill ok">
              <span className="status-dot" /> Connected
            </span>
          ) : (
            <span className="status-pill error">
              <span className="status-dot" /> {connectionError ?? 'Not connected'}
            </span>
          ))}
        {!apiKey && <span className="status-pill off">No key set</span>}
      </section>

      <div className="grid">
        <div className="stack">
          <section className="card">
            <div className="card-heading-row">
              <h2>Recent events</h2>
              <span className="muted">
                {events.length} shown{stats ? ` of ${stats.total_events} total` : ''}
              </span>
            </div>

            {stats && (
              <div className="stats-row">
                <div className="stat-tile">
                  <div className="value">{stats.total_events}</div>
                  <div className="label">Total logged</div>
                </div>
                <div className="stat-tile">
                  <div className="value">{Object.keys(stats.events_by_camera).length}</div>
                  <div className="label">Cameras seen</div>
                </div>
                <div className="stat-tile">
                  <div className="value">{Object.keys(stats.events_by_type).length}</div>
                  <div className="label">Event types</div>
                </div>
              </div>
            )}

            {events.length === 0 ? (
              <div className="empty-state">
                {apiKey
                  ? 'No events logged yet. Send one with the test form, or a real vendor payload.'
                  : 'Enter an API key above to load events.'}
              </div>
            ) : (
              <table className="events-table">
                <thead>
                  <tr>
                    <th>Camera</th>
                    <th>Event type</th>
                    <th>Confidence</th>
                    <th>Detected at</th>
                    <th>Logged at</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((event, idx) => (
                    <tr key={`${event.camera_id}-${event.timestamp}-${idx}`}>
                      <td className="camera-id">{event.camera_id}</td>
                      <td>{event.event_type}</td>
                      <td>
                        <ConfidenceBar value={event.confidence} />
                      </td>
                      <td>{formatTimestamp(event.timestamp)}</td>
                      <td className="muted">{formatTimestamp(event.received_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </div>

        <div className="stack">
          <section className="card">
            <h2>Enabled plugins</h2>
            {plugins.length === 0 ? (
              <div className="empty-state">
                {apiKey ? 'No plugins configured.' : 'Enter an API key to load config/plugins.yaml.'}
              </div>
            ) : (
              <ul className="plugin-list">
                {plugins.map((plugin) => (
                  <li className="plugin-row" key={plugin.name}>
                    <div>
                      <span className="plugin-name">{plugin.name}</span>
                      <span className="plugin-module">
                        {plugin.module}.{plugin.class_name}
                      </span>
                    </div>
                    <span className={`status-pill ${plugin.enabled ? 'ok' : 'off'}`}>
                      <span className="status-dot" /> {plugin.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="card">
            <h2>Send a test event</h2>
            <p className="muted" style={{ marginBottom: 12 }}>
              POSTs to <code>/webhooks/events?adapter=generic_json</code> so you can watch it
              appear in the table above once the dispatch queue logs it.
            </p>
            <form className="test-event-form" onSubmit={handleSubmitTestEvent}>
              <div className="form-grid">
                <div className="form-row">
                  <label htmlFor="camera_id">Camera ID</label>
                  <input
                    id="camera_id"
                    type="text"
                    value={form.camera_id}
                    onChange={(e) => setForm({ ...form, camera_id: e.target.value })}
                    required
                  />
                </div>
                <div className="form-row">
                  <label htmlFor="event_type">Event type</label>
                  <select
                    id="event_type"
                    value={form.event_type}
                    onChange={(e) => setForm({ ...form, event_type: e.target.value })}
                  >
                    {EVENT_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="form-row">
                  <label htmlFor="confidence">Confidence (0-1)</label>
                  <input
                    id="confidence"
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={form.confidence}
                    onChange={(e) => setForm({ ...form, confidence: Number(e.target.value) })}
                    required
                  />
                </div>
                <div className="form-row">
                  <label htmlFor="zone">Zone (metadata)</label>
                  <input
                    id="zone"
                    type="text"
                    value={form.zone}
                    onChange={(e) => setForm({ ...form, zone: e.target.value })}
                  />
                </div>
              </div>
              <button className="primary" type="submit" disabled={submitting || !apiKey}>
                {submitting ? 'Sending...' : 'Send test event'}
              </button>
              {submitMessage && <div className="banner success">{submitMessage}</div>}
              {submitError && <div className="banner error">{submitError}</div>}
            </form>
          </section>
        </div>
      </div>

      <footer className="dashboard-footer">
        Vision Platform Integration API - admin dashboard. Polls every {POLL_INTERVAL_MS / 1000}s
        while an API key is set.
      </footer>
    </div>
  );
}

export default App;
