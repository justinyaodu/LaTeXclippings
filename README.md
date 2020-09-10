# LaTeXclippings

_Batch render LaTeX files to cropped SVG images._

![Rendered LaTeX: I love LaTeX!](demo/latex.svg)

![Rendered LaTeX: sum from 1 to n](demo/summation.svg)

## Features

LaTeXclippings takes multiple LaTeX files, and an optional preamble, as input. Using your computer's LaTeX installation, it renders each input file as an SVG image or embeddable HTML `<img>` tag. All relevant LaTeX features are supported, including regular text, inline and display math, and tables.

Each rendered image is cropped, allowing it to be easily embedded in other content. When generating HTML `<img>` tags, additional CSS style rules are added, which adjust the SVG's scale and baseline to match the surrounding text. No more misaligned equations!

LaTeXclippings also parses the `pdflatex` log, matching up each input file with the corresponding log output. If any error messages are found, they are converted into informative Python exceptions, which identify the file and line responsible for an error.

## Installation

Install from [PyPI](https://pypi.org/project/latexclippings/):

```console
pip install latexclippings
```

Alternatively, simply download [latexclippings.py](latexclippings.py).

### Dependencies

LaTeXclippings requires Python 3.6+, and also uses:

* `pdflatex` to generate PDFs from LaTeX source
* `inkscape` for PDF cropping and SVG conversion

## Usage

### Command Line

The `latexclippings` command reads LaTeX files (or standard input) and outputs SVG or embeddable HTML. (If you did not install LaTeXclippings from PyPI, you can use `./latexclippings.py` or `python latexclippings.py` instead.)

Using standard input and output:

```console
$ # Kinetic energy formula (in classical mechanics).
$ echo '$ E_k = \frac{1}{2}mv^2 $' | latexclippings > kinetic-energy.svg
```

![Rendered LaTeX: kinetic energy](demo/kinetic-energy.svg)

Rendering multiple LaTeX files to HTML, using a custom preamble:

```console
$ latexclippings --format html --preamble my-preamble.tex \
>         apple.tex banana.tex grape.tex
$ ls
apple.html  banana.html  grape.html  my-preamble.tex
apple.tex   banana.tex   grape.tex
```

The contents of `apple.html` (note the inline CSS styles for scaling and alignment):

```html
<img style="display: inline-block; width: 21.38669ex;
height: 2.08727ex; vertical-align: -0.45000ex;"
alt="I enjoy eating apples." title="I enjoy eating apples."
src="data:image/svg+xml;base64, PHN2ZwogICB4bWxuczp...">
```

![Rendered LaTeX: apples](demo/apple.svg)

### Python API

For more sophisticated usage (e.g. integration into a static website generator), you can use the Python API.

```python
from latexclippings import LatexFile

lf = LatexFile([r"This is some \LaTeX code.", r"Math: $ \sin(x) $"])

c = lf.clippings[0]
print(f"The first clipping is {c.width} by {c.height} ex, "
        + f"with {c.depth} ex below the baseline.")

with open("math.svg", "w") as f:
    f.write(lf.clippings[1].svg)
```

## License

LaTeXclippings is licensed under the [MIT License](LICENSE.md).
