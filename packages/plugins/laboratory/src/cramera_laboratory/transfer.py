"""
Run the optional PR2 transfer through cramera-bridge with the packaged bench's path.
"""

from __future__ import annotations

import importlib.util
import sys

from typing_extensions import Optional, Sequence

from cramera_laboratory.resources import RESOURCES_DIRECTORY, LaboratoryResource
from cramera_protocol.laboratory.runs import TransferOption


def main(arguments: Optional[Sequence[str]] = None) -> None:
    """
    :param arguments: The transfer options, or this process's arguments by default.
    """
    if importlib.util.find_spec("cramera_bridge") is None:
        raise SystemExit(
            "The PR2 transfer needs cramera-laboratory[bridge] and the CRAM workspace."
        )
    if importlib.util.find_spec("cramera_bridge.laboratory") is None:
        raise SystemExit("Update cramera-bridge to install the laboratory transfer.")
    from cramera_bridge.laboratory.command import main as transfer_main

    transfer_main(
        [
            TransferOption.BUNDLE.value,
            str(RESOURCES_DIRECTORY / LaboratoryResource.BENCH),
            *(sys.argv[1:] if arguments is None else arguments),
        ]
    )


if __name__ == "__main__":
    main()
