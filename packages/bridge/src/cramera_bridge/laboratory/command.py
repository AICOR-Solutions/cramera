"""
The laboratory's process boundary: bundle paths enter, preview and recorded scene
references come back.

Dependency discovery imports no CRAM modules.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from argparse import ArgumentParser
from pathlib import Path

from typing_extensions import List, Optional, Sequence

from cramera_protocol.laboratory.runs import TransferOption
from cramera_protocol.live_messages import SavedScene

CRAM_PACKAGES = (
    "semantic_digital_twin",
    "coraplex",
    "giskardpy",
    "krrood",
    "segmind",
)
"""
The workspace libraries the transfer and the live recording need.
"""


def missing_libraries() -> List[str]:
    """
    :return: The missing workspace modules, without importing native classes.
    """
    return [name for name in CRAM_PACKAGES if importlib.util.find_spec(name) is None]


def run_transfer(
    bundle: str,
    arguments: Sequence[str],
    recording: Optional[str] = None,
    live_url_file: Optional[str] = None,
) -> SavedScene:
    """
    :param bundle: The caller's laboratory bundle directory.
    :param arguments: The transfer's remaining command-line options.
    :param recording: A recording name for this run, or the demo's default name.
    :param live_url_file: Where to announce the run's local live server, if requested.
    :return: The saved or published scene, as a protocol document.
    """
    from cramera_bridge.laboratory.transfer import VesselTransferDemo
    from cramera_bridge.robot_task import TaskCommand

    fields = {}
    if recording is not None:
        fields["name"] = recording
    if live_url_file is not None:
        fields["live_url_file"] = Path(live_url_file)
    return TaskCommand(VesselTransferDemo.at_the_bench(Path(bundle), **fields)).main(
        arguments
    )


def prepare_preview(bundle: str, scenes: str) -> SavedScene:
    """
    Prepare the actual PR2 and the compact lab without starting any motion.

    :param bundle: The caller's compact laboratory bundle directory.
    :param scenes: The viewer's local scenes directory.
    :return: The initial-state scene, as a protocol document.
    """
    from cramera_bridge.laboratory.preview import LaboratoryPreview

    return LaboratoryPreview(Path(bundle), Path(scenes)).prepare()


def main(arguments: Optional[Sequence[str]] = None) -> None:
    """
    :param arguments: The command arguments, or this process's arguments by default.
    """
    parser = ArgumentParser(description="Run the laboratory's PR2 vessel transfer.")
    parser.add_argument(TransferOption.BUNDLE, required=True, type=Path)
    parser.add_argument(
        TransferOption.PREVIEW,
        type=Path,
        help="prepare an initial PR2 laboratory scene in this scenes directory",
    )
    parser.add_argument(
        TransferOption.RECORDING, help="the recording name for this run"
    )
    parser.add_argument(
        TransferOption.LIVE_URL_FILE,
        type=Path,
        help="announce the local live server URL in this file once it is ready",
    )
    options, remaining = parser.parse_known_args(
        sys.argv[1:] if arguments is None else list(arguments)
    )
    missing = missing_libraries()
    if missing:
        parser.error("The PR2 transfer needs the CRAM workspace: " + ", ".join(missing))
    if options.preview is not None:
        if (
            remaining
            or options.recording is not None
            or options.live_url_file is not None
        ):
            parser.error("The PR2 preview takes no transfer options.")
        saved = prepare_preview(str(options.bundle), str(options.preview))
        print(json.dumps(saved.to_json()))
        return
    fields = {}
    if options.recording is not None:
        fields["recording"] = options.recording
    if options.live_url_file is not None:
        fields["live_url_file"] = str(options.live_url_file)
    run_transfer(str(options.bundle), remaining, **fields)


if __name__ == "__main__":
    main()
