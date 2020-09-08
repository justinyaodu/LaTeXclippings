import itertools
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


class _LatexChunk:
    """Represent multiple lines of logically related LaTeX source code.
    """
    
    CHUNK_HEADER = r"\typeout{svgfromlatex chunk header}"

    _error_regex = ''.join([
        r"^! (?P<error_msg>.*)$",
        r"^l\.(?P<line_num>[0-9]+) (?P<line_contents>.*)$",
    ])

    def __init__(self, lines, offset):
        self.source_lines = lines
        self.lines = [__class__.CHUNK_HEADER, *lines, r"\newpage"]
        self.log = None
        self.offset = offset

    def __len__(self):
        return len(self.lines)

    def __str__(self):
        return '\n'.join(self.lines)

    def _parse_log(self, log):
        self.log = log

        match = re.match(__class__._error_regex, log, flags=re.MULTILINE)
        if match:
            groupdict = match.groupdict()

            line_num = int(groupdict["line_num"]) - self.offset - 1

            context_lines = []
            for i in range(len(self.source_lines)):
                if i == line_num:
                    prefix = "> "
                else:
                    prefix = "  "
                context_lines.append(prefix + self.source_lines[i])
            context = '\n'.join(context_lines)

            msg = f"Line {line_num}: {groupdict['error_msg']}\n{context}"
            raise ValueError(msg)


class LatexFile:
    """Represent the source of a LaTeX document."""

    def __init__(self, preamble, pages):
        self.chunks = []
        for chunk_lines in self._chunk_lines(preamble, pages):
            self.chunks.append(_LatexChunk(chunk_lines, len(self)))

    def __len__(self):
        # Linear time complexity is probably not a concern here.
        return sum(len(chunk) for chunk in self.chunks)

    def __str__(self):
        return '\n'.join(str(chunk) for chunk in self.chunks)

    def _chunk_lines(self, preamble, pages):
        yield [*preamble.split('\n'), r"\usepackage{trimclip}"]
        yield ['x']
        for page in pages:
            page_lines = page.split('\n')
            yield page_lines
            yield [
                r"\begin{clipbox}{0 0 0 {\height}}\vbox{",
                *page_lines,
                r"}\end{clipbox}",
            ]

    def _parse_log(self, log):
        log_sections = log.split(_LatexChunk.CHUNK_HEADER + '\n')

        # Skip the unneeded log section before the first header.
        log_sections = log_sections[1:]

        for chunk, log_section in zip(self.chunks, log_sections):
            chunk.parse_log(log_section)

    def _render(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)

            pdflatex_process = subprocess.run(
                ["pdflatex"],
                cwd=temp_dir,
                text=True,
                input=str(self),
                capture_output=True,
            )

            self._parse_log(pdflatex_process.stdout)
            try:
                pdflatex_process.check_returncode()
            except subprocess.CalledProcessError:
                raise ValueError(pdflatex_process.stdout)

            # TODO
            subprocess.run(["firefox", shlex.quote(str(temp_dir / "texput.pdf"))])
            input()
