from setuptools import setup, find_packages

setup(
    name="neuro-sim",
    version="1.0.0",
    description="Multi-user Neuro Memory simulation tool",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "locust>=2.20,<3.0",
        "requests>=2.31",
        "pyyaml>=6.0",
        "datasets>=2.16",
        "feedparser>=6.0",
    ],
    entry_points={
        "console_scripts": [
            "neuro-sim=neuro_sim:main",
        ],
    },
)
