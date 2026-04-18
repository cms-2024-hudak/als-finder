from setuptools import setup, find_packages

setup(
    name="als-finder",
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    description="A high-performance, cloud-native CLI engine for discovering and parsing raw LiDAR point cloud metadata.",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Jonathan Greenberg",
    author_email="jgreenberg@unr.edu",
    url="https://github.com/cms-2024-hudak/als-finder",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "click",
        "requests",
        "geopandas",
        "shapely",
        "pyproj",
        "python-dotenv",
        "tqdm",
        "pyogrio",
    ],
    extras_require={
        "dev": ["pytest", "setuptools_scm", "build"],
        "pdal": ["pdal"],
        "all": ["pdal"]
    },
    entry_points={
        "console_scripts": [
            "als-finder=als_finder.cli:cli",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
)
