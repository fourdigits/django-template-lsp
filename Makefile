ENV = env
BIN = $(ENV)/bin
PYTHON = $(BIN)/python
CODE_LOCATIONS = djlsp setup.py tests

clean:
	rm -rf $(ENV)
	rm -rf build
	rm -rf dist
	rm -rf *.egg
	rm -rf *.egg-info
	find | grep -i ".*\.pyc$$" | xargs -r -L1 rm

$(ENV):
	python3 -m venv $(ENV)

develop: $(ENV)
	$(PYTHON) -m pip install --upgrade pip setuptools wheel twine
	$(PYTHON) -m pip install -e .[dev]

fix-codestyle:
	$(BIN)/black $(CODE_LOCATIONS)
	$(BIN)/isort $(CODE_LOCATIONS)

lint:
	$(BIN)/black --check $(CODE_LOCATIONS)
	$(BIN)/isort --check-only $(CODE_LOCATIONS)
	$(BIN)/flake8 $(CODE_LOCATIONS)

test: lint
	$(BIN)/tox run

.PHONY: build
build:
	$(PYTHON) setup.py sdist bdist_wheel
	$(BIN)/twine check dist/*

upload:
	$(BIN)/twine upload --skip-existing dist/*
