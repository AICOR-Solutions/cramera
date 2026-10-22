"""
A stand-in for a task demo that saves its recording into the viewer's local scenes.
"""

import json
import os
import sys
from pathlib import Path

from cramera.locations import DataLocations
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import SceneKey

scene = sys.argv[1]
directory = DataLocations.from_environment(os.environ, Path.home()).local_scenes / scene
directory.mkdir(parents=True)
(directory / BundleFile.SCENE).write_text(json.dumps({SceneKey.NAME: scene}))
