# Inference-only image: serving bundle + demo state + demo world (about 9 MB) and the web UI, never the 680k-row dataset.
# Python 3.12 to match the environment the artifacts were pickled in.
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements-serve.txt .
RUN pip install --no-cache-dir -r requirements-serve.txt
COPY config.yaml .
COPY src ./src
COPY artifacts/serve_bundle.joblib artifacts/demo_state.joblib artifacts/demo_world.joblib ./artifacts/
# federated slip costs and results, amount habits (thresholds + last-30 histories), the judges' test numbers
COPY artifacts/portable/slip_costs.json artifacts/portable/federated.json artifacts/portable/amount_habits.json      artifacts/portable/amount_profiles.npz artifacts/portable/test_kit.json ./artifacts/portable/
COPY ui ./ui
ENV PROHORI_ARTIFACTS=/app/artifacts \
    PROHORI_LLM=offline \
    PYTHONUNBUFFERED=1
# Render and most hosts set $PORT; Hugging Face Spaces uses app_port from the Space README (8000 here).
EXPOSE 8000
CMD ["sh", "-c", "uvicorn src.serve.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
