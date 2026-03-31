import os
from pathlib import Path

from setuptools import find_packages, setup


def _externalized_version() -> str:
    root = Path(__file__).resolve().parent
    base = (root / "VERSION").read_text().strip()
    append = os.getenv("KEELI_VERSION_APPEND", "").strip()
    return f"{base}{append}" if append else base

setup(
    name="keeli",
    version=_externalized_version(),
    description="Keeli CLI — Enforce a Five-Persona Architecture for AI Agents.",
    license="MIT",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.12",
    install_requires=[
        "mcp>=1.0.0",
    ],
    classifiers=[
        "License :: OSI Approved :: MIT License",
    ],
    entry_points={
        "console_scripts": [
            "keeli=keeli.main:main",
        ],
    },
)
