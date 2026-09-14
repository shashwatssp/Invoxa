-- 0007: agent accounting
-- gemini_usage: one row per IST day, counts Gemini calls spent by the agent layer.
-- agent_audit: append-only trail of agent events (ask/explain, caps, quota stops).

CREATE TABLE IF NOT EXISTS gemini_usage (
  day date PRIMARY KEY,
  calls integer NOT NULL DEFAULT 0,
  updated_at timestamptz
);

CREATE TABLE IF NOT EXISTS agent_audit (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  user_id text,
  event text NOT NULL,
  detail jsonb
);

ALTER TABLE gemini_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_audit ENABLE ROW LEVEL SECURITY;
