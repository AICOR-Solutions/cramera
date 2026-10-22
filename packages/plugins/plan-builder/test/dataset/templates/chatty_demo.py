"""
A stand-in for the generated demo of ${name} (${file_name}) that writes more output than
the log keeps.
"""

import sys

DEMO = r"""
${demo}
"""

LINES = 2000
"""

How many lines the demo writes.
"""

if __name__ == "__main__":
    for number in range(LINES):
        print(f"line {number:05d}")
    sys.stdout.flush()
