"""
Format Python files with black, then with docformatter where black keeps its output.

docformatter and black disagree on a few blank lines after attribute docstrings; a file
whose docformatter output black changes again keeps the plain black output, so
formatting always converges.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from typing_extensions import List, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
"""
The repository whose ``pyproject.toml`` configures both tools.
"""

DOCSTRING_QUOTES = '"""'
"""
The quotes that open and close a docstring.
"""


@dataclass
class AttributeDocstringSpacing:
    """
    Puts a blank line after every attribute docstring that is directly followed by code,
    which docformatter removes in some class bodies.
    """

    def apply(self, source: str) -> str:
        """
        :param source: Python source.
        :return: The source with a blank line after each attribute docstring.
        """
        lines = source.splitlines(keepends=True)
        result: List[str] = []
        opening = None
        for index, line in enumerate(lines):
            result.append(line)
            stripped = line.strip()
            if opening is None and stripped.startswith(DOCSTRING_QUOTES):
                if not (len(stripped) > 3 and stripped.endswith(DOCSTRING_QUOTES)):
                    opening = index
                continue
            if opening is None or stripped != DOCSTRING_QUOTES:
                continue
            if self.documents_an_attribute(lines, opening) and self.code_follows(
                lines, index
            ):
                result.append("\n")
            opening = None
        return "".join(result)

    @staticmethod
    def documents_an_attribute(lines: List[str], opening: int) -> bool:
        """
        :param lines: The source lines.
        :param opening: The line that opens a docstring.
        :return: Whether the docstring follows an attribute rather than opening a
            module, class or function body.
        """
        previous = lines[opening - 1].rstrip() if opening > 0 else ""
        return (
            bool(previous) and not previous.endswith(":") and not previous.endswith("(")
        )

    @staticmethod
    def code_follows(lines: List[str], closing: int) -> bool:
        """
        :param lines: The source lines.
        :param closing: The line that closes a docstring.
        :return: Whether the next line is code at the docstring's indentation.
        """
        if closing + 1 >= len(lines):
            return False
        following = lines[closing + 1]
        indentation = len(lines[closing]) - len(lines[closing].lstrip())
        return (
            bool(following.strip())
            and len(following) - len(following.lstrip()) == indentation
        )


@dataclass
class PythonFormatter:
    """
    Formats Python files in place with the repository's black and docformatter settings.
    """

    configuration: Path = REPOSITORY_ROOT / "pyproject.toml"
    """
    The file holding the tools' settings.
    """

    def format_source(self, source: str) -> str:
        """
        :param source: The content of a Python file.
        :return: The formatted content: black and docformatter when a second pass
            leaves it unchanged, otherwise black alone.
        """
        black_output = self.black(source)
        documented = self.documented(black_output)
        return documented if self.documented(documented) == documented else black_output

    def documented(self, source: str) -> str:
        """
        :param source: Python source formatted by black.
        :return: The source after docformatter, attribute spacing and black.
        """
        return self.black(AttributeDocstringSpacing().apply(self.docformatter(source)))

    def black(self, source: str) -> str:
        """
        :param source: Python source.
        :return: The source as black formats it.
        """
        return self.run(
            [
                sys.executable,
                "-m",
                "black",
                "--quiet",
                "--config",
                str(self.configuration),
                "-",
            ],
            source,
            accepted_codes=(0,),
        )

    def docformatter(self, source: str) -> str:
        """
        :param source: Python source.
        :return: The source with docstrings as docformatter formats them.
        """
        return self.run(
            [
                sys.executable,
                "-m",
                "docformatter",
                "--config",
                str(self.configuration),
                "-",
            ],
            source,
            accepted_codes=(0, 3),
        )

    @staticmethod
    def run(command: List[str], source: str, accepted_codes: Sequence[int]) -> str:
        """
        :param command: A formatter reading the source from standard input.
        :param source: Python source.
        :param accepted_codes: The exit codes that mean the formatter succeeded.
        :return: The formatter's output.
        :raises subprocess.CalledProcessError: When the formatter fails.
        """
        result = subprocess.run(
            command, input=source, capture_output=True, text=True, check=False
        )
        if result.returncode not in accepted_codes:
            raise subprocess.CalledProcessError(
                result.returncode, command, result.stdout, result.stderr
            )
        return result.stdout

    def format_file(self, path: Path) -> bool:
        """
        :param path: A Python file.
        :return: Whether the file changed.
        """
        source = path.read_text(encoding="utf-8")
        formatted = self.format_source(source)
        if formatted == source:
            return False
        path.write_text(formatted, encoding="utf-8")
        return True


def main(arguments: Sequence[str]) -> int:
    """
    Format the given files, or every Python file of the repository without arguments.

    :param arguments: The files to format.
    :return: The process exit code.
    """
    paths = [Path(argument) for argument in arguments] or sorted(
        path for path in REPOSITORY_ROOT.glob("**/*.py") if ".git" not in path.parts
    )
    formatter = PythonFormatter()
    changed = [path for path in paths if formatter.format_file(path)]
    for path in changed:
        print(f"formatted {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
