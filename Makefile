.PHONY: help
help:
	@echo "Available commands:"
	@echo "  make up      - Start containers (build if needed)"
	@echo "  make down    - Stop and remove containers"
	@echo "  make logs    - View api logs"
	@echo "  make test    - Run tests inside the container"

# Targets
up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f api

test:
	docker compose exec api pytest