from setuptools import setup, find_packages

setup(
    name="als_finder",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "click",
        "requests",
        "geopandas",
        "shapely",
        "python-dotenv",
        "tqdm",
    ],
    entry_points={
        "console_scripts": [
            "als-finder=als_finder.cli:cli",
        ],
    },
)
