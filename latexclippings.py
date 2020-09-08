import base64
import html
import itertools
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile


class LatexFile:
    """Represent a LaTeX document, composed of a preamble, clippings,
    and additional pages used for internal measurements.
    """

    def __init__(self, clippings, preamble=r"\documentclass{minimal}"):
        self.clippings = [LatexClipping(c) for c in clippings]
        self._init_chunks(preamble, clippings)
        self._render()

    def _init_chunks(self, preamble, clippings):
        self.chunks = []

        self.chunks.append(_LatexChunk(
            "preamble",
            [
                *preamble.split("\n"),
                r"\usepackage{trimclip}",
                r"\begin{document}",
            ]
        ))

        # Lowercase x, for measuring an ex with the current font.
        self.chunks.append(_LatexChunk("lowercase x", ["x"], True))

        for clipping, clipping_index in zip(clippings, itertools.count()):
            clipping_lines = clipping.split("\n")

            # Render clipping normally.
            self.chunks.append(_LatexChunk(
                f"clipping {clipping_index}",
                clipping_lines,
                True,
                clipping_index
            ))

            # Render portion of clipping below baseline to measure depth.
            self.chunks.append(_LatexChunk(
                "clipping {clipping_index} (below baseline only)",
                [
                    r"\begin{clipbox}{0 0 0 {\height}}\vbox{",
                    *clipping_lines,
                    r"}\end{clipbox}",
                ],
                True,
                clipping_index
            ))

        self.chunks.append(_LatexChunk("document end", [r"\end{document}"]))

    def __str__(self):
        return "\n".join(str(chunk) for chunk in self.chunks)

    def _render(self):
        """Render each clipping as a SVG."""

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            pdf_path = self._pdflatex(temp_dir)
            self._load_svgs_from_pdf(pdf_path)

    def _pdflatex(self, working_dir):
        """Convert this LaTeX document to a PDF. Raise LatexError if
        pdflatex is unsuccessful.
        """

        tex_file = working_dir / "clippings.tex"
        with open(tex_file, "w") as f:
            f.write(str(self))

        pdflatex_process = subprocess.run(
            [
                "pdflatex",
                "-halt-on-error",
                shlex.quote(str(tex_file))
            ],
            cwd=working_dir,
            text=True,
            capture_output=True,
        )

        self._parse_pdflatex_log(pdflatex_process.stdout)

        try:
            pdflatex_process.check_returncode()
        except subprocess.CalledProcessError as e:
            raise ValueError(pdflatex_process.stdout) from e

        return working_dir / "clippings.pdf"

    _pdflatex_error_regex = "".join([
        r"^! (?P<error_msg>.*)[\n]",
        r"l\.(?P<line_num>[0-9]+) (?P<line_contents>.*)$",
    ])

    def _parse_pdflatex_log(self, log):
        """Parse the pdflatex log, assigning log sections to the
        corresponding LatexClippings. Raise LatexError for any error
        messages encountered.
        """

        log_sections = log.split(_LatexChunk.CHUNK_HEADER + "\n")

        # Skip the initialization output (before start of preamble).
        log_sections = log_sections[1:]

        for _ in zip(self.chunks, log_sections, itertools.count()):
            chunk, log_section, chunk_index = _
            clipping = None

            if chunk.clipping_index is not None:
                clipping = self.clippings[chunk.clipping_index]

                # Only assign the log from rendering the full (not
                # cropped) clipping.
                if clipping.log is None:
                    clipping.log = log_section

            match = re.search(__class__._pdflatex_error_regex, log_section,
                    re.MULTILINE)
            if match:
                groupdict = match.groupdict()

                # Get zero-indexed line numbers.
                file_line_num = int(groupdict['line_num']) - 1
                chunk_line_num = (file_line_num
                        - sum(len(c) for c in self.chunks[:chunk_index]))

                context_lines = []
                context_dist = 2
                for i in range(
                        max(chunk.source_start, chunk_line_num - context_dist),
                        min(len(chunk), chunk_line_num + context_dist + 1)):
                    if i == chunk_line_num:
                        prefix = "> "
                    else:
                        prefix = "  "
                    context_lines.append(prefix + chunk.lines[i])
                context = "\n".join(context_lines)

                display_line_num = chunk_line_num - chunk.source_start + 1

                raise LatexError(chunk.clipping_index, chunk.name,
                        display_line_num, groupdict['error_msg'], context)

    def _load_svgs_from_pdf(self, pdf_path):
        """Load SVGs from the rendered PDF into the LatexClippings."""

        one_ex = _cropped_pdf_page(pdf_path, 1).height

        for clipping, index in zip(self.clippings, itertools.count(1)):
            image_full = _cropped_pdf_page(pdf_path, 2 * index)
            image_below_baseline = _cropped_pdf_page(pdf_path, 2 * index + 1)

            clipping.svg = image_full.source
            clipping.width = image_full.width / one_ex
            clipping.height = image_full.height / one_ex
            clipping.depth = image_below_baseline.height / one_ex


class LatexClipping:
    """Represent a rendered LaTeX clipping."""

    def __init__(self, latex):
        # LaTeX source.
        self.latex = latex

        # pdflatex log from generating this clipping.
        self.log = None

        # Image measurements in ex. Depth is the height of the portion
        # of the image below the baseline.
        self.width = None
        self.height = None
        self.depth = None

        # SVG source.
        self.svg = None

    def css(self):
        """Return CSS styles which can be applied to an inline <img> tag
        containing this clipping's SVG. These rules will align the
        baseline and scale the image to match the surrounding text.
        """

        return " ".join([
            "display: inline-block;",
            f"width: {self.width}ex;",
            f"height: {self.height}ex;",
            f"vertical-align: {-self.depth}ex;"
        ])

    def embeddable(self):
        """Return a string representing a HTML <img> tag, which contains
        the base64-encoded SVG and CSS rules for inline display.
        """

        svg_without_prolog = "\n".join(self.svg.split("\n")[1:])
        base64_encoded = (base64.b64encode(svg_without_prolog.encode("utf-8"))
                .decode("utf-8"))
        escaped_latex = html.escape(self.latex).replace("\n", "&#13;&#10;")

        return " ".join([
            f'<img style="{self.css()}"',
            f'alt="{escaped_latex}" title="{escaped_latex}"',
            f'src="data:image/svg+xml;base64, {base64_encoded}">',
        ])


class LatexError(Exception):
    """Raised when an error occurs while rendering LaTeX."""

    def __init__(self, clipping_index, location, line_num, error_msg, context):
        # Index of the clipping this error occurred in, or None if the
        # error occurred elsewhere (e.g. in the preamble).
        self.clipping_index = clipping_index

        # Human-readable chunk name.
        self.location = location

        # One-indexed line number of the error.
        self.line_num = line_num

        self.error_msg = error_msg

        # Point out the error line and show a few adjacent lines.
        self.context = context

        super().__init__(str(self))

    def __str__(self):
        return "".join([
            f"{self.location}, line {self.line_num}: {self.error_msg}\n",
            self.context,
        ])


class _LatexChunk:
    """Represent a section of logically related LaTeX source code."""

    # Precedes the log output for each chunk.
    CHUNK_HEADER = "SVGFROMLATEX CHUNK HEADER"

    def __init__(self, name, lines, new_page=False, clipping_index=None):
        self.name = name
        self.clipping_index = clipping_index

        self.lines = [r"\typeout{" + __class__.CHUNK_HEADER + "}"]
        self.source_start = 1
        if new_page:
            self.lines.append(r"\newpage")
            self.source_start += 1
        self.lines.extend(lines)

    def __len__(self):
        return len(self.lines)

    def __str__(self):
        return "\n".join(self.lines)


class _SVG:
    """Represent an SVG image with dimension information."""

    def __init__(self, width, height, source):
        # Width, in px.
        self.width = width

        # Height, in px.
        self.height = height

        # SVG data.
        self.source = source


def _cropped_pdf_page(pdf_path, page):
    """Extract a page of the specified PDF as an _SVG."""

    lines = subprocess.run(
        [
            "inkscape",
            "--pdf-poppler",
            f"--pdf-page={page}",
            "--query-width",
            "--query-height",
            "--export-plain-svg",
            "--export-area-drawing",
            "--export-filename=-",
            shlex.quote(str(pdf_path))
        ],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.split('\n')

    return _SVG(float(lines[0]), float(lines[1]), '\n'.join(lines[2:]))


def _main(args):
    pass


if __name__ == "__main__":
    _main(sys.argv)
