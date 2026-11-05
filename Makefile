VENV := .venv
BIN := $(VENV)/bin
# Navigateurs de Playwright rangés dans l'environnement virtuel, pour ne rien écrire ailleurs.
export PLAYWRIGHT_BROWSERS_PATH := $(abspath $(VENV)/navigateurs)

.PHONY: demo installer navigateur test e2e lint types verifier verrou

demo: $(VENV)/.installe
	$(BIN)/routeur-ia demo

installer: $(VENV)/.installe

# Utilise uv s'il est présent, sinon python3.12 et pip. Les deux installent le fichier verrouillé.
$(VENV)/.installe: requirements.lock pyproject.toml
	if command -v uv >/dev/null 2>&1; then \
		uv venv --allow-existing --python 3.12 $(VENV) && \
		uv pip install --python $(BIN)/python --require-hashes -r requirements.lock && \
		uv pip install --python $(BIN)/python --no-deps -e . ; \
	else \
		python3.12 -m venv $(VENV) && \
		$(BIN)/pip install --require-hashes -r requirements.lock && \
		$(BIN)/pip install --no-deps -e . ; \
	fi
	touch $@

navigateur: $(VENV)/.installe
	$(BIN)/playwright install chromium

lint: $(VENV)/.installe
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

types: $(VENV)/.installe
	$(BIN)/mypy

test: $(VENV)/.installe
	$(BIN)/pytest -m "not navigateur" --cov --cov-report=term-missing --cov-fail-under=90

e2e: navigateur
	$(BIN)/pytest -m navigateur $(OPTIONS_E2E)

verifier: lint types test e2e

# Recalcule requirements.lock depuis pyproject.toml (nécessite uv).
verrou:
	uv pip compile pyproject.toml --extra dev --universal --python-version 3.12 \
		--generate-hashes --no-header --output-file requirements.lock
