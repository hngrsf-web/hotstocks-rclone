# UGREEN Trading Control Cloud

Read-only remote dashboard for the UGREEN Hot-Stocks research system.

## Security model
- NAS is never exposed inbound to the Internet.
- NAS sends an outbound JSON snapshot to /api/ingest.
- Dashboard is protected with HTTP Basic Auth.
- Ingest uses a separate Bearer token.
- No broker/order/control endpoints exist in this cloud service.
- Frozen strategy logic is not hosted or changed here.

## Railway
Root directory: /cloud
Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
Health check: /health
