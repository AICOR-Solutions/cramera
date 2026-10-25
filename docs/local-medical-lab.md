# Use the small medical lab

The **Medical lab** tab brings the compact `aicor_medical_lab` workbench into the
current viewer. It includes the rack and glassware, scale, centrifuge, sample
refrigerator, drawer and dispensing station. The expanded room is not included.
The plugin ships the small scene and its assets, so no SSH copy is needed.

## Install the tab

From a current cramera checkout, use Python 3.11 or newer and a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
unset PYTHONPATH PYTHONHOME
python -m pip install -e ./packages/protocol -e ./packages/viewer \
  -e ./packages/plugins/laboratory
cramera --no-browser --keep-running
```

Open [the viewer](http://127.0.0.1:8711/?panel=laboratory), select **Medical lab**
and choose **Open**. The tab is available even when the scene picker is empty.
The standard `scripts/install_stack.py` installer also installs this plugin,
including with `--viewer-only`.

## Add MuJoCo for the controls

Stop the viewer with Ctrl-C. In the same terminal and virtual environment, from
this repository's root:

```bash
python -m pip install -e './packages/plugins/laboratory[physics]'
cramera --no-browser --keep-running
```

Then choose **Simulate with contact physics** in **Medical lab**. The tab's
**Set up MuJoCo contact physics** help shows the installation command when physics
is unavailable. If the environment has no pip, run `python -m ensurepip --upgrade`
first.
Run it on the machine running the Python viewer; the browser uses the viewer's
simulation. Restart the viewer after installing.

The `physics` extra installs the official `mujoco` Python package. Its wheel
includes the MuJoCo library; there is no separate engine download. See the
[MuJoCo installation documentation](https://mujoco.readthedocs.io/en/stable/python.html#installation).
CRAM and ROS are not needed for the lab's contact simulation.

## Workbench controls

- Select a vessel or stopper, pull it or move its target, then release it. Gravity,
  friction and contacts determine its motion.
- Set a vessel's fill and inspect the liquid volumes, pouring and spills.
- Read or tare the scale.
- Open or close the centrifuge lid, secure or release seated samples, inspect its
  manual and requirements, and start or stop a cycle.
- Open or close the refrigerator and drawer and inspect their contents.
- Fill the dispenser reservoirs, dose into an aligned vessel, stop and resume.
- Reset the lab or stop the simulation. The device catalog offers the five
  workbench devices and their URDF files.

The simulation is shared by browsers connected to this viewer. A scene named
`aicor_medical_lab_contact_physics` holds its current view. Installed scenes and
recordings live in `$CRAMERA_DATA/scenes` (default `~/.cramera/scenes`); the original
packaged assets stay unchanged. Starting a new simulation refreshes that generated
scene's packaged assets so its visible models match the current physics geometry.
Keep their `LICENSE.txt`, `NOTICE.md` and
`rights.json` with any copies.

## Optional PR2 transfer

The transfer controls remain in the tab. They use `cramera-bridge` and the CRAM
workspace; without those dependencies the tab reports that the demo is unavailable.
MuJoCo alone enables the workbench simulation, not the robot plan.

The transfer uses current CRAM APIs and was verified against
[CRAM revision e69fee4](https://github.com/cram2/cognitive_robot_abstract_machine/commit/e69fee4d14589c0a32826fcd54b42a1c6818d185).
An older CRAM workspace may need updating before running it.

Install the full stack into the environment you will use for the viewer:

```bash
python3 scripts/install_stack.py --venv "$PWD/.venv"
source .venv/bin/activate
```

Follow the repository README's ROS 2 and robot-description setup before running a
robot demo. The transfer runs in a separate process through `cramera-bridge`, with
its state, log and saved recording available through the tab. Stopping the viewer
also stops its simulation and a transfer it owns.

## Troubleshooting

- **No Medical lab tab:** activate the environment where the plugin is installed,
  restart `cramera`, and check that `/api/info` lists `laboratory`.
- **MuJoCo still missing:** install the `physics` extra with that environment's
  `python -m pip`; restart the viewer. Installing a package in another Python
  environment does not add it to the running viewer.
- **Port already in use:** choose a free `--port` and open its URL;
  `--keep-running` preserves the other viewer.
- **No WebGL context:** use a browser with working WebGL. The simulation runs in
  Python, but displaying the scene still needs the browser's graphics support.
