from setuptools import setup, find_packages

setup(
    name="persona-cli",
    version="0.3.0",
    description="Enforce a Four-Persona Architecture for AI Agents.",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "persona=persona_cli.main:main",
        ],
    },
)
