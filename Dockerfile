# One image for every service and job.
# CM_ROLE=api|worker|job, CM_JOB=nightly|sweeper|seed|eval|migrate (jobs only).
# Needs web/ (Vite app) and cm/ from the other lanes.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web .
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=Asia/Kolkata PORT=8080
# UNVERIFIED tag: pin an exact uv version after checking ghcr.io/astral-sh/uv
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /app
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt
COPY cm cm
COPY models models
COPY data data
COPY fixtures/cassettes fixtures/cassettes
COPY fixtures/eval fixtures/eval
COPY --from=web /web/dist web/dist
USER 1000
ENTRYPOINT ["python", "-m", "cm"]
