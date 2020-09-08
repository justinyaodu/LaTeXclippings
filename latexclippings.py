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


class LatexError(Exception):
    """Raised when an error occurs while rendering LaTeX."""

    def __init__(self, clipping_index, location, line_num, error_msg, context):
        # Index of the clipping this error occurred in.
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


class LatexClipping:
    """Represent a rendered LaTeX clipping."""

    def __init__(self, latex):
        self.latex = latex
        self.log = None


class LatexFile:
    """Represent the source of a LaTeX document."""

    _error_regex = "".join([
        r"^! (?P<error_msg>.*)[\n]",
        r"l\.(?P<line_num>[0-9]+) (?P<line_contents>.*)$",
    ])

    def __init__(self, preamble, clippings):
        self.clippings = [LatexClipping(c) for c in clippings]
        self._init_chunks(preamble, clippings)

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

    def _parse_log(self, log):
        log_sections = log.split(_LatexChunk.CHUNK_HEADER + "\n")

        # Skip the initialization output (before start of preamble).
        log_sections = log_sections[1:]

        for _ in zip(self.chunks, log_sections, itertools.count()):
            chunk, log_section, index = _
            clipping = None

            if chunk.clipping_index is not None:
                clipping = self.clippings[chunk.clipping_index]

                # Only assign the log from rendering the full (not
                # cropped) clipping.
                if clipping.log is None:
                    clipping.log = log_section

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

            tex_file = temp_dir / "clippings.tex"

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
            subprocess.run(["firefox", shlex.quote(str(temp_dir / "clippings.pdf"))])
            input()
