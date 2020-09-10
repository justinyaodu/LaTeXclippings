#!/usr/bin/env python3

import re
import setuptools

with open("README.md") as f:
    long_description = f.read()

with open("latexclippings.py") as f:
    _source = f.read()
    version = re.search('__version__ = "(.*?)"', _source)[1]
    author = re.search('__author__ = "(.*?)"', _source)[1]

setuptools.setup(
    name="latexclippings",
    version=version,
    author=author,
    author_email="justinyaodu@gmail.com",
    description="Batch render LaTeX files to cropped SVG images",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/justinyaodu/LaTeXclippings",
    py_modules=["latexclippings"],
    entry_points={'console_scripts': ['latexclippings=latexclippings:_main']},
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Environment :: Console",
        "Topic :: Text Processing :: Markup :: LaTeX"
    ],
    python_requires='>=3.6'
)
