SITE ?= site1.localhost

.PHONY: setup lint test check

setup:
	pre-commit install
	npm install

lint:
	pre-commit run --all-files

test:
	bench --site $(SITE) run-tests --app connect_diagnostics_core

check: lint test
