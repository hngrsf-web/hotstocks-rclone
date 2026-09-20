const APP_VERSION = "1.0.0-cloudflare";

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store, max-age=0",
    },
  });
}

function unauthorized() {
  return new Response("Authentication required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="UGREEN Trading Control Cloud"' },
  });
}

function basicAuthOk(request, env) {
  if (!env.CLOUD_PASSWORD) return false;
  const header = request.headers.get("authorization") || "";
  if (!header.startsWith("Basic ")) return false;
  try {
    const decoded = atob(header.slice(6));
    const p = decoded.indexOf(":");
    if (p < 0) return false;
    const user = decoded.slice(0, p);
    const pass = decoded.slice(p + 1);
    return user === (env.CLOUD_USER || "trading") && pass === env.CLOUD_PASSWORD;
  } catch {
    return false;
  }
}

function sourceTime(snapshot) {
  const value =
    snapshot?.generated_at_utc ||
    snapshot?.endpoints?.health?.data?.server_time ||
    null;
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

function cloudMeta(snapshot, env) {
  const t = sourceTime(snapshot);
  const ageSeconds = t == null ? null : Math.max(0, Math.floor((Date.now() - t) / 1000));
  const staleMinutes = Number(env.STALE_MINUTES || "10");
  return {
    cloud_version: APP_VERSION,
    source_generated_at: t == null ? null : new Date(t).toISOString(),
    age_seconds: ageSeconds,
    stale: ageSeconds == null || ageSeconds > staleMinutes * 60,
    stale_after_minutes: staleMinutes,
    read_only: true,
    orders_enabled: false,
  };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      const raw = env.SNAPSHOT_KV ? await env.SNAPSHOT_KV.get("snapshot") : null;
      const snapshot = raw ? JSON.parse(raw) : null;
      return json({
        ok: true,
        app: "UGREEN Trading Control Cloud",
        version: APP_VERSION,
        snapshot_present: !!snapshot,
        kv_bound: !!env.SNAPSHOT_KV,
        cloud_password_configured: !!env.CLOUD_PASSWORD,
        ingest_token_configured: !!env.INGEST_TOKEN,
        ...cloudMeta(snapshot, env),
      });
    }

    if (url.pathname === "/api/ingest" && request.method === "POST") {
      if (!env.INGEST_TOKEN) return json({ ok: false, detail: "INGEST_TOKEN not configured" }, 503);
      if (!env.SNAPSHOT_KV) return json({ ok: false, detail: "SNAPSHOT_KV not bound" }, 503);
      const auth = request.headers.get("authorization") || "";
      if (auth !== `Bearer ${env.INGEST_TOKEN}`) return json({ ok: false, detail: "invalid ingest token" }, 401);

      const length = Number(request.headers.get("content-length") || "0");
      if (length > 20 * 1024 * 1024) return json({ ok: false, detail: "payload too large" }, 413);

      let payload;
      try {
        payload = await request.json();
      } catch {
        return json({ ok: false, detail: "invalid json" }, 400);
      }
      if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
        return json({ ok: false, detail: "json root must be object" }, 400);
      }
      if (!payload.endpoints || typeof payload.endpoints !== "object") {
        return json({ ok: false, detail: "missing endpoints" }, 400);
      }

      await env.SNAPSHOT_KV.put("snapshot", JSON.stringify(payload));
      await env.SNAPSHOT_KV.put("snapshot_received_at", new Date().toISOString());
      return json({
        ok: true,
        received_at: new Date().toISOString(),
        generated_at_utc: payload.generated_at_utc || null,
      });
    }

    if (!basicAuthOk(request, env)) return unauthorized();

    if (url.pathname === "/api/snapshot") {
      if (!env.SNAPSHOT_KV) return json({ ok: false, snapshot: null, cloud: cloudMeta(null, env), detail: "SNAPSHOT_KV not bound" });
      const raw = await env.SNAPSHOT_KV.get("snapshot");
      const snapshot = raw ? JSON.parse(raw) : null;
      return json({
        ok: !!snapshot,
        snapshot,
        cloud: cloudMeta(snapshot, env),
      });
    }

    const response = await env.ASSETS.fetch(request);
    const headers = new Headers(response.headers);
    headers.set("cache-control", "no-store, max-age=0");
    return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
  },
};
