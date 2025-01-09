ENV = env
BIN = $(ENV)/bin
PYTHON = $(BIN)/python
CODE_LOCATIONS = djlsp tests

clean:
	rm -rf $(ENV)
	rm -rf build
	rm -rf dist
	rm -rf *.egg
	rm -rf *.egg-info
	find | grep -i ".*\.pyc$$" | xargs -r -L1 rm

$(ENV):
	python3 -m venv $(ENV)
	$(PYTHON) -m pip install --upgrade pip setuptools wheel twine
	$(PYTHON) -m pip install -e .[dev]

develop: $(ENV)

fix-codestyle:
	$(BIN)/black $(CODE_LOCATIONS)
	$(BIN)/isort $(CODE_LOCATIONS)

lint:
	$(BIN)/black --check $(CODE_LOCATIONS)
	$(BIN)/isort --check-only $(CODE_LOCATIONS)
	$(BIN)/flake8 $(CODE_LOCATIONS)

test: lint
	$(BIN)/tox run

django-env:
	python3 -m venv tests/django_test/env
	tests/django_test/env/bin/python -m pip install django~=4.2.0

helix: $(ENV) django-env
	touch tests/django_test/django_app/templates/test.html
	. $(ENV)/bin/activate; hx --working-dir tests/django_test tests/django_test/django_app/templates/test.html

install-ci: $(ENV)
	$(PYTHON) -m pip install --upgrade pip setuptools wheel twine build .

.PHONY: build
build:
	$(PYTHON) -m build
	$(BIN)/twine check dist/*

upload:
	$(BIN)/twine upload --skip-existing dist/*

build-vscode-extension:
	npm --prefix ./vscode/ run compile
	npm --prefix ./vscode/ run vsce-package
