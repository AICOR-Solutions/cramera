"""
A stand-in for the generated demo of ${name} (${file_name}) that watches its owner's
pipe, as a generated demo does, and then ends on its own.
"""

import sys

from cramera_plan_builder.lifeline import Lifeline

DEMO = r"""
${demo}
"""

if __name__ == "__main__":
    Lifeline(sys.stdin.buffer).watch()
    print("performed", flush=True)
