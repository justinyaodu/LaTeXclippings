import itertools
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import textwrap


class _LatexChunk:
    """Represent a section of logically related LaTeX source code."""
    
    # Precedes the log output for each chunk.
    CHUNK_HEADER = "SVGFROMLATEX CHUNK HEADER"

    def __init__(self, name, lines, new_page=False, page_num=None):
        self.name = name
        self.page_num = page_num

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


class LatexError(Exception):
    """Raised when an error occurs while rendering LaTeX."""

    def __init__(self, page_num, location, line_num, error_msg, context):
        # Zero-indexed page number.
        self.page_num = page_num

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


class LatexPage:
    """Represent a page of rendered LaTeX output."""

    def __init__(self, latex):
        self.latex = latex
        self.log = None


class LatexFile:
    """Represent the source of a LaTeX document."""

    _error_regex = "".join([
        r"^! (?P<error_msg>.*)[\n]",
        r"l\.(?P<line_num>[0-9]+) (?P<line_contents>.*)$",
    ])

    def __init__(self, preamble, pages):
        self.pages = [LatexPage(page) for page in pages]
        self._init_chunks(preamble, pages)

    def _init_chunks(self, preamble, pages):
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

        for page, page_num in zip(pages, itertools.count()):
            page_lines = page.split("\n")

            # Render page normally.
            self.chunks.append(_LatexChunk(
                f"page {page_num}",
                page_lines,
                True,
                page_num
            ))

            # Render portion of page below baseline to measure depth.
            self.chunks.append(_LatexChunk(
                "page {page_num} (clipped)",
                [
                    r"\begin{clipbox}{0 0 0 {\height}}\vbox{",
                    *page_lines,
                    r"}\end{clipbox}",
                ],
                True,
                page_num
            ))

        self.chunks.append(_LatexChunk("document end", [r"\end{document}"]))

    def __str__(self):
        return "\n".join(str(chunk) for chunk in self.chunks)

    def _parse_log(self, log):
        log_sections = log.split(_LatexChunk.CHUNK_HEADER + "\n")

        # Skip the initialization output (before start of preamble).
        log_sections = log_sections[1:]

        for _ in zip(self.chunks, log_sections, itertools.count()):
            chunk, log_section, index = _
            page = None

            if chunk.page_num is not None:
                page = self.pages[chunk.page_num]

                # Only assign the log of the first chunk with this page
                # number (the second chunk is the clipped page).
                if page.log is None:
                    page.log = log_section

            match = re.search(__class__._error_regex, log_section, re.MULTILINE)
            if match:
                groupdict = match.groupdict()

                # Get zero-indexed line numbers.
                file_line_num = int(groupdict['line_num']) - 1
                chunk_line_num = (file_line_num
                        - sum(len(c) for c in self.chunks[:index]))

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

                raise LatexError(index, chunk.name, display_line_num,
                        groupdict['error_msg'], context)

    def _render(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)

            tex_file = temp_dir / "pages.tex"

            with open(tex_file, "w") as f:
                f.write(str(self))

            pdflatex_process = subprocess.run(
                [
                    "pdflatex",
                    "-halt-on-error",
                    shlex.quote(str(tex_file))
                ],
                cwd=temp_dir,
                text=True,
                capture_output=True,
            )

            self._parse_log(pdflatex_process.stdout)

            try:
                pdflatex_process.check_returncode()
            except subprocess.CalledProcessError as e:
                raise ValueError(pdflatex_process.stdout) from e

            # TODO
            subprocess.run(["firefox", shlex.quote(str(temp_dir / "pages.pdf"))])
            input()
