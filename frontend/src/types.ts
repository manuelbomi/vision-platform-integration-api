/**
 * TypeScript mirrors of the backend's Pydantic models
 * (see `src/api/models.py` and the new response models in `src/api/main.py`).
 *
 * Field names and shapes are kept in exact sync with the Python side so a
 * change to the API contract shows up here as a type error, not a runtime
 * surprise.
 */

/** Mirrors `api.models.BoundingBox`. */
export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Mirrors `api.models.VisionEvent`, the normalized event shape. */
export interface VisionEvent {
  camera_id: string;
  event_type: string;
  confidence: number;
  bounding_box: BoundingBox | null;
  /** ISO 8601 timestamp string, as returned by FastAPI/Pydantic JSON encoding. */
  timestamp: string;
  metadata: Record<string, unknown>;
}

/**
 * Mirrors `api.main.RecentEvent`: a `VisionEvent` as read back from the
 * `sql_logger` audit table by `GET /events/recent`.
 */
export interface RecentEvent extends VisionEvent {
  /** When the sql_logger plugin persisted this row (SQLite `datetime('now')`). */
  received_at: string;
}

/** Mirrors `api.main.EventStats`, returned by `GET /events/stats`. */
export interface EventStats {
  total_events: number;
  events_by_type: Record<string, number>;
  events_by_camera: Record<string, number>;
}

/** Mirrors `api.main.PluginInfo`, returned by `GET /plugins`. */
export interface PluginInfo {
  name: string;
  module: string;
  class_name: string;
  enabled: boolean;
}

/** Shape of the `{"status": "accepted", "event": {...}}` response from POST /webhooks/events. */
export interface WebhookAcceptedResponse {
  status: string;
  event: VisionEvent;
}
