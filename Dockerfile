# One production image: FastAPI API + built web app. Same image for every service and job.
#   CM_ROLE=api|worker  serves the API and the web app on $PORT (default 8080)
#   CM_ROLE=job         runs `python -m cm.jobs.$CM_JOB` (nightly|sweeper|seed|eval|migrate)
# The web bundle is built with a RELATIVE API base (same origin), so it works on any hostname.
# No secrets or .env are baked in: all config comes from env at run time (see .dockerignore).

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web .
# VITE_API_BASE empty = same origin. VITE_USE_MOCK=false = talk to the real API.
ENV VITE_USE_MOCK=false VITE_API_BASE=
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=Asia/Kolkata PORT=8080 CM_ROLE=api CM_WEB_DIR=/app/web/dist
# UNVERIFIED tag: pin an exact uv version after checking ghcr.io/astral-sh/uv
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /app
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt
COPY cm cm
COPY data data
COPY fixtures/text_bank.json fixtures/text_bank.json
COPY --from=web /web/dist web/dist
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin cm
USER 10001
EXPOSE 8080
# Exec form: python is PID 1 and receives SIGTERM; uvicorn drains in-flight requests, then exits.
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=15s --timeout=4s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import os,sys,urllib.request as u; sys.exit(0 if u.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','8080'), timeout=3).status == 200 else 1)"]
ENTRYPOINT ["python", "-m", "cm"]
