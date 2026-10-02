# One image serves the web app and the API from the same URL.

# ---- web build ----
FROM node:22-alpine AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- runtime ----
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY config config
COPY sop sop
COPY reports reports
COPY backend backend
COPY --from=web /app/web/dist web/dist
# upay-style wallet pages, served at /upay/ and wired to the API
COPY ["upay frontend clone", "upay frontend clone"]

# Size of the synthetic world: 2500 customers fits a 512 MB host (~390 MB); 4000 needs ~450 MB.
ARG FEROT_CUSTOMERS=2500
ENV FEROT_CUSTOMERS=${FEROT_CUSTOMERS} \
    FEROT_ROOT=/app \
    FEROT_DB_PATH=/app/backend/ferot.db \
    FEROT_LLM_PROVIDER=offline \
    PYTHONUNBUFFERED=1
WORKDIR /app/backend
# Build the synthetic world, train the models and run the simulation at image build time.
RUN python -m ferot.cli build
EXPOSE 8000
CMD ["sh", "-c", "uvicorn ferot.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
