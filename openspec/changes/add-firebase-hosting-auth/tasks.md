# Tasks: add-firebase-hosting-auth

Sizes: S under 1 h, M 1 to 2 h. Stage 1 = default `*.web.app` URLs; stage 2 = custom domain.

## 0. Design (this change)
- [x] 0.1 Write `docs/deploy/FIREBASE_PLAN.md` (lane I, S)

## 1. Hosting config (lane I, stage 1)
- [ ] 1.1 `firebase.json` with targets doctor/patient/family/demo, API rewrites to `cm-api` (asia-south1), SPA fallback, headers (S). Test: `firebase hosting:channel:deploy preview` serves deep links and `/healthz` via rewrite
- [ ] 1.2 `.firebaserc` targets; `infra/firebase/README.md` runbook (S)
- [ ] 1.3 `infra/env/api.env.yaml`: `AUTH_MODE=firebase`, `FIREBASE_PROJECT_ID`, `CORS_ORIGINS`, `CM_ALLOWED_HOSTS`; `infra/60_deploy.sh` cm-api `--timeout=3600` (S)

## 2. Backend (lane G, stage 1)
- [ ] 2.1 `cm/api/firebase_auth.py`: pure `verify_firebase_token` + securetoken key fetcher (M). Test: `tests/api/test_firebase_auth.py` with a local RSA key (good token, bad alg, unknown kid, wrong aud, wrong iss, expired, empty sub)
- [ ] 2.2 `cm/api/deps.py`: `AUTH_MODE` branch; firebase path cross-checks `pid`, `role`, `tv`, `active` (M). Test: `tests/api/test_deps_firebase.py` (retired user 401, role mismatch 401, stale tv 401, no claims 403); existing local tests unchanged
- [ ] 2.3 `cm/api/routers/auth.py`: `/auth/login` returns 404 `use_firebase` in firebase mode; logout no-op 204 (S). Test in `tests/api/test_auth.py`
- [ ] 2.4 `cm/api/main.py`: `Cache-Control: private, no-store` on API responses; `allow_credentials=False` in firebase mode (S)
- [ ] 2.5 Lane A: `cm/core/config.py` reads `AUTH_MODE`, `FIREBASE_PROJECT_ID`; refuses firebase mode without project id (S)

## 3. Web (lane H1, stage 1)
- [ ] 3.1 `web/package.json` add `firebase`; `web/src/auth/firebase.ts` init from `VITE_FIREBASE_*` (S)
- [ ] 3.2 `web/src/auth/session.tsx`: `signIn`/`signOut` via SDK when `VITE_AUTH_MODE=firebase`, username to email suffix (M). Test: `session.test.tsx` with a fake auth
- [ ] 3.3 `web/src/api/http.ts` + `uploadDocument.ts`: bearer from `getIdToken()`, 401 retry with forced refresh, `credentials: "omit"` (M). Test: `edge.test.ts`
- [ ] 3.4 `web/src/realtime/sse.ts`: `VITE_LIVE=poll` (S, stage 1); fetch-based SSE reader with bearer to `VITE_STREAM_BASE` (M, stage 1b). Test: `sse.test.ts`

## 4. Demo accounts (lane I, stage 1)
- [ ] 4.1 `scripts/firebase_users.py` (+ `firebase-admin` in `requirements-dev.txt`): idempotent create/update of dr.rao, admin.demo, demo.pt0906, demo.pt0960, ravi.pt0142, lakshmi.s01 with claims `role`, `pid`, `tv`; `--dry-run`, `--revoke`; never prints passwords (M). Test: unit test with a fake admin client

## 5. Rollout
- [ ] 5.1 Owner console steps (enable email/password, disable sign-up, authorized domains, web app) and `firebase login` (owner, S)
- [ ] 5.2 Deploy per FIREBASE_PLAN.md section 6; smoke per site (I + integration, M)
- [ ] 5.3 Stage 2: custom domains `doctor.`, `patient.`, `family.<domain>`; DNS; authorized domains; env update (I + owner, S + cert wait)
- [ ] 5.4 Optional lane A: migration adding nullable `auth_credentials.firebase_uid`, checked against `sub` (S)
- [ ] 5.5 Update `docs/deploy/DEPLOY_PLAN.md` to point at FIREBASE_PLAN.md for the superseded LB/cookie sections (I, S)
