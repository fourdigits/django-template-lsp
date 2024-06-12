from setuptools import find_packages, setup

from djlsp import __version__


def readme():
    with open("README.md") as f:
        return f.read()


setup(
    name="django-template-lsp",
    version=__version__,
    description="Django template LSP",
    long_description=readme(),
    long_description_content_type="text/markdown",
    license="GPL3",
    packages=find_packages(include=["djlsp", "djlsp.*"]),
    package_data={"djlsp": ["scripts/*.py"]},
    entry_points={
        "console_scripts": [
            "djlsp = djlsp.cli:main",
            "django-template-lsp = djlsp.cli:main",
        ]
    },
    python_requires=">= 3.9",
    install_requires=[
        "pygls",
    ],
    extras_require={
        "dev": [
            "tox",
            "black",
            "isort",
            "flake8",
            "pytest",
            "pytest-check",
            "pytest-cov",
        ]
    },
)
