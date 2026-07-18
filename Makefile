.PHONY: bootstrap test demo up down
bootstrap:
	python scripts/bootstrap.py
test:
	python -m pytest -q
up: bootstrap
	docker compose up -d --build
demo:
	./scripts/demo.sh
down:
	docker compose down
