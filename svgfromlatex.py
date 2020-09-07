"""
Dependencies: pdflatex, inkscape
"""

import base64
import html
import itertools
import re
from pathlib import Path
import shlex
import subprocess
import tempfile
import textwrap

__all__ = ['RenderResult', 'LatexSVG', 'render']


class LatexSVG:
    """Represents an SVG rendered from LaTeX source."""

    def __init__(self, latex, svg, width, height, depth):
        # LaTeX source.
        self.latex = latex

        # SVG source.
        self.svg = svg

        # Width of the SVG, in ex.
        self.width = width

        # Height of the SVG, in ex.
        self.height = height

        # Height of the portion of the SVG below the baseline, in ex.
        self.depth = depth

    def __str__(self):
        return self.svg

    def css(self):
        """Return CSS styles which can be used on an <img> tag. These
        rules will align the baseline with the surrounding text and
        scale the image appropriately.
        """

        return ' '.join([
            f"display:inline-block;",
            f"width:{self.width}ex;",
            f"height:{self.height}ex;",
            f"vertical-align:{-self.depth}ex;",
        ])

    def embeddable(self):
        """Return a string representing a self-contained HTML <img> tag,
        which can be used to display the rendered LaTeX inline.
        """

        svg_without_prolog = '\n'.join(self.svg.split('\n')[1:])
        base64_encoded = base64.b64encode(svg_without_prolog.encode("utf-8")).decode("utf-8")
        escaped_latex = html.escape(self.latex).replace('\n', '&#13;&#10;')

        return ' '.join([
            f'<img style="{self.css()}"',
            f'src="data:image/svg+xml;base64, {base64_encoded}"',
            f'alt="{escaped_latex}" title="{escaped_latex}">',
        ])


class RenderResult:
    """Contains the rendered SVGs and command-line logs."""

    def __init__(self, rendered, pdflatex_log):
        self.rendered = rendered
        self.pdflatex_log = pdflatex_log


def render(sources, preamble=r'\documentclass{minimal}'):
    """Given an array of LaTeX source code strings, render each LaTeX
    string on a separate page, convert them to SVG, and return them in
    a RenderResult.
    """
    
    latex_pages = _get_pages(sources)
    latex = _assemble_latex(latex_pages, preamble)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        pdf, pdflatex_output = _pdflatex(latex, temp_dir)
        svg_pages = [_inkscape(pdf, i) for i in range(len(latex_pages))]

    one_ex = svg_pages[0].height

    latex_svgs = []
    for i in range(len(sources)):
        svg_page_full = svg_pages[2 * i + 1]
        svg_page_below_baseline = svg_pages[2 * i + 2]
        latex_svgs.append(LatexSVG(
            sources[i],
            svg_page_full.svg,
            svg_page_full.width / one_ex,
            svg_page_full.height / one_ex,
            svg_page_below_baseline.height / one_ex))

    return RenderResult(latex_svgs, pdflatex_output)


def _get_pages(sources):
    """Given an array of LaTeX source strings, return a transformed
    array of source strings where each element corresponds to a page
    in the rendered document. Page 0 containts a letter 'x', page 2n+1
    contains sources[n], and page 2n+2 contains the portion of
    sources[n] below the baseline.
    """

    pages = ['x']

    for source in sources:
        # Render normally.
        pages.append(source)

        # Render only the part below the baseline.
        pages.append('\n'.join([
                r'\begin{clipbox}{0 0 0 {\height}}\vbox{%',
                textwrap.indent(source, "  ") + '%',
                r'}\end{clipbox}']))

    return pages

    
def _assemble_latex(pages, preamble):
    """Return a string representing a LaTeX source file, where page 0
    contains a letter 'x', page 2n+1 contains sources[n], and page 2n+2
    contains the portion of sources[n] below the baseline.
    """

    preamble += '\n' + r'\usepackage{trimclip}'

    return '\n'.join([
            preamble,
            "",
            r'\begin{document}',
            "",
            ("\n\n" + r"\newpage" + "\n\n").join(pages),
            "",
            r'\end{document}'])


def _pdflatex(latex, working_dir):
    """Render LaTeX source to a PDF in the working directory, returning
    the path of the rendered PDF and the output of pdflatex.
    """

    completed_process = subprocess.run(["pdflatex"],
            cwd=working_dir,
            input=latex.encode(),
            capture_output=True)

    pdflatex_output = completed_process.stdout.decode("utf-8")

    try:
        completed_process.check_returncode()
    except subprocess.CalledProcessError as e:
        raise ValueError('\n'.join([
            f"pdflatex failed (exit status {completed_process.returncode}).",
            "LaTeX source:",
            textwrap.indent(latex, "  " * 4),
            "pdflatex log:",
            textwrap.indent(pdflatex_output, " " * 4),
        ])) from e

    return (working_dir / "texput.pdf", pdflatex_output)


class _InkscapeSVG:
    """Represents a cropped SVG generated by Inkscape."""

    def __init__(self, width, height, svg):
        # Width, in px.
        self.width = width

        # Height, in px.
        self.height = height

        # SVG source.
        self.svg = svg


def _inkscape(pdf, page):
    """Convert a (zero-indexed) page of the specified PDF to a cropped
    SVG. Returns a dict {width, height, svg}.
    """

    output = subprocess.run(
            [
                "inkscape",
                "--pdf-poppler",
                f"--pdf-page={page + 1}",
                "--query-width",
                "--query-height",
                "--export-plain-svg",
                "--export-area-drawing",
                "--export-filename=-",
                shlex.quote(str(pdf))
            ],
            capture_output=True,
            check=True).stdout

    lines = output.decode('utf-8').split('\n')
    return _InkscapeSVG(float(lines[0]), float(lines[1]), '\n'.join(lines[2:]))
