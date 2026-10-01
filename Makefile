# Convenience targets (Linux/macOS/Git Bash). Windows PowerShell users: see README "Run".
PY ?= backend/.venv/bin/python

.PHONY: setup build test web up demo-offline docker

setup:
	python -m venv backend/.venv && $(PY) -m pip install -r backend/requirements.txt
	cd web && npm ci

build:
	cd backend && ../$(PY) -m ferot.cli build

test:
	cd backend && ../$(PY) -m pytest

web:
	cd web && npm run build

up: web
	cd backend && ../$(PY) -m uvicorn ferot.api.main:app --port 8000

# The whole demo runs with no network: the LLM provider stays offline (rules + templates).
demo-offline: web
	cd backend && FEROT_LLM_PROVIDER=offline ../$(PY) -m uvicorn ferot.api.main:app --port 8000

docker:
	docker build -t ferot . && docker run --rm -p 8000:8000 ferot
