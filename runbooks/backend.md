# Upstream backend unavailable
Symptoms: 5xx on /api/echo, logs "backend call failed" / "connection refused", backend Endpoints empty.
Fix: scale backend up, check Service selector, readiness probe.
