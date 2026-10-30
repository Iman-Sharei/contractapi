.PHONY: db install test studio api doctor examples

db:
	docker compose up -d db

install:
	python -m venv .venv
	. .venv/bin/activate && pip install -U pip && pip install -e "./backend[dev]"
	cd apps/web && npm install

test:
	. .venv/bin/activate && cd backend && \
	  JWT_SECRET=dev-jwt-secret-change-me-please-32chars \
	  STUDIO_API_KEY=dev-studio-key-change-me \
	  DATA_API_KEYS=dev-data-key \
	  pytest -q
	cd apps/web && npm test && npm run typecheck

api:
	. .venv/bin/activate && \
	  STUDIO_API_KEY=dev-studio-key-change-me \
	  DATA_API_KEYS=dev-data-key \
	  CORS_ORIGINS=http://localhost:3000 \
	  dataapi serve --host 127.0.0.1 --port 8000

studio:
	cd apps/web && npm run dev

doctor:
	. .venv/bin/activate && dataapi doctor --url postgresql://postgres:postgres@localhost:5433/app

examples:
	. .venv/bin/activate && \
	  dataapi validate backend/examples/dataapi.yaml && \
	  dataapi validate backend/examples/jwt_write.yaml --no-check-db && \
	  dataapi validate backend/examples/sql_metrics.yaml --no-check-db && \
	  dataapi validate backend/examples/webhooks.yaml --no-check-db
