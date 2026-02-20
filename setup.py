from setuptools import setup, find_packages

setup(
    name="persona-cli",
    version="0.1.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "persona=persona:main",
        ],
    },
    py_modules=["persona"],
)
