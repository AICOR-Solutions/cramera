"""
A stand-in for the generated demo of ${name} (${file_name}) that fails.
"""

import sys

DEMO = r"""
${demo}
"""

if __name__ == "__main__":
    print("Traceback (most recent call last):", flush=True)
    sys.exit(1)
