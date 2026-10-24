## 1. Backend
- [x] 1.1 `cm/__main__.py` entrypoint with SIGTERM drain
- [x] 1.2 `cm/api/web.py` SPA fallback, cache headers, host middleware; wire in `cm/api/main.py`
- [x] 1.3 `CM_COOKIE_DOMAIN`, Secure on prod in `cm/core/config.py`, `cm/api/routers/auth.py`
## 2. Web and image
- [x] 2.1 `web/src/api/http.ts` same-origin base (vitest 115 pass)
- [x] 2.2 `Dockerfile`, `.dockerignore`, `.env.example`
## 3. Verification
- [x] 3.1 `tests/integration/test_web_serving.py` (8 pass)
- [x] 3.2 `docker build -t caremem-prod:test .` and run against caremem_test: healthz, /, /doctor, openapi, /auth/me, cache headers, host 400, SIGTERM exit 0
