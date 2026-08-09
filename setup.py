from setuptools import setup, find_packages

setup(
    name="score-ai",
    version="0.1.0",
    description="On-chain credit intelligence powered by AI",
    author="Dinky Coder",
    url="https://github.com/dinkycoder/SCORE",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.11",
)
