# UGREEN Trading Control Cloud – Cloudflare Free

Kostenarme/bei normaler persönlicher Nutzung kostenlose Read-only-Cloudansicht.

## Architektur
NAS -> HTTPS POST -> Cloudflare Worker -> KV -> Browser

## Sicherheit
- keine eingehende NAS-Freigabe
- keine Broker-/Order-Endpunkte
- Dashboard mit Basic Auth geschützt
- Upload mit separatem Bearer Token
- CLOUD_PASSWORD und INGEST_TOKEN als Cloudflare Secrets, niemals im GitHub-Repo
- V11 bleibt unverändert

## Cloudflare Setup
1. Worker/Pages Projekt aus diesem GitHub-Ordner `/cloudflare` deployen.
2. KV Namespace z.B. `ugreen-hotstocks-snapshot` erstellen.
3. Worker Binding `SNAPSHOT_KV` -> dieser Namespace.
4. Secrets setzen:
   - `CLOUD_PASSWORD`
   - `INGEST_TOKEN`
5. Variablen:
   - `CLOUD_USER=trading`
   - `STALE_MINUTES=10`
6. Healthcheck: `/health`
7. NAS sendet `hot_stocks_live.json` an `/api/ingest`.

Bei 5-Minuten-Sync entstehen ca. 288 KV-Schreibvorgänge pro Tag.
