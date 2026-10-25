"""
A native command stand-in that announces its live address and saves a named recording.
"""

import argparse
import json
import os
import time
from pathlib import Path

from cramera.locations import DataLocations
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import SceneKey
from cramera_protocol.laboratory.runs import TransferOption

# %% command

parser = argparse.ArgumentParser()
parser.add_argument(TransferOption.RECORDING, required=True)
parser.add_argument(TransferOption.LIVE_URL_FILE, required=True, type=Path)
parser.add_argument("--port", required=True, type=int)
parser.add_argument("--failure", action="store_true")
parser.add_argument("--waiting", action="store_true")
options = parser.parse_args()
assert options.port == 0
options.live_url_file.write_text("http://127.0.0.1:8765")
if options.waiting:
    time.sleep(60)
if options.failure:
    raise SystemExit("the vessel is still held")
directory = (
    DataLocations.from_environment(os.environ, Path.home()).local_scenes
    / options.recording
)
directory.mkdir(parents=True)
(directory / BundleFile.SCENE).write_text(
    json.dumps({SceneKey.NAME: options.recording})
)
