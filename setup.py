from setuptools import setup, find_packages

setup(
    name="keeli",
    version="0.3.0",
    description="Keeli CLI — Enforce a Four-Persona Architecture for AI Agents.",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
    install_requires=[
        "mcp>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "keeli=keeli.main:main",
        ],
    },
)
