# Run the small medical lab and PR2 locally

**Medical lab** in the viewer's top bar opens a dedicated page with its own 3D
view, controls and playback timeline:
[/plugins/laboratory/laboratory.html](http://127.0.0.1:8711/plugins/laboratory/laboratory.html).
It loads the compact `aicor_medical_lab` workbench with the real PR2 in its starting
pose when the native runtime is installed. The rack and glassware, scale,
centrifuge, refrigerator, drawer and dispenser are included. Only the small lab is
shipped; its assets need no SSH copy.

## Install the full local PR2 runtime

Use a current cramera checkout, Python 3.12 and
[uv](https://github.com/astral-sh/uv). Install ROS 2 Jazzy and the ROS robot
resources described in CRAM's
[ROS workspace setup](https://github.com/cram2/cognitive_robot_abstract_machine#optional-setup-your-ros-workspace),
including `iai_pr2_description`. That guide's `scripts/setup_ros_workspace.sh`
builds the robot-resource workspace. The Python installer below installs the CRAM
packages; it does not replace that ROS setup.

From the cramera repository root, source ROS and your built ROS workspace, then
install the complete stack into a dedicated environment:

```bash
source /opt/ros/jazzy/setup.bash
source "$HOME/ros2_ws/install/setup.bash"  # CRAM's setup_ros_workspace.sh builds ~/ros2_ws
python3 scripts/install_stack.py --venv "$PWD/.venv"
source .venv/bin/activate
export CRAMERA_DATA="$HOME/.local/share/cramera-medical-lab"
cramera --no-browser --keep-running
```

The installer includes the viewer, laboratory plugin, bridge and CRAM workspace.
It clones CRAM when needed; `--cram /path/to/cram` selects an existing checkout.
The demo was verified against
[CRAM revision e69fee4](https://github.com/cram2/cognitive_robot_abstract_machine/commit/e69fee4d14589c0a32826fcd54b42a1c6818d185).
An older CRAM checkout may need updating. Installing only the plugin's `[bridge]`
extra does not install the native CRAM workspace or robot descriptions.

For later launches, source the same ROS setup files, activate `.venv`, set the same
`CRAMERA_DATA` and start `cramera` again. The browser and Python viewer can be
separate processes, but the demo runs on the machine hosting the Python viewer.

## Run, follow and replay

Open [Medical lab](http://127.0.0.1:8711/plugins/laboratory/laboratory.html), or
choose **Medical lab** in the top bar. Initial preparation loads the real PR2
meshes with its parked arms and raised torso beside the small workbench.

Choose **Run the demo**. A local CRAM process picks the vessel from rack slot A1,
lifts it and places it in A3. The page follows the live robot motion as soon as
the process is ready, then opens the completed recording in the same 3D view.
Use the timeline to play, pause and seek, or **Open the recording** to return to
it. **Show lab and PR2** restores the initial view. **End the run** stops an active
process; the page then reports the run as ended, not failed.

Every new run gets an unused recording name, so **Run the demo** remains available
after a successful run and preserves earlier recordings. A failed run reports
its error even if an older recording exists: how its process ended (the signal
that ended it, its exit code, or that it saved no recording), then the last lines
of its log. Recordings are saved in
`$CRAMERA_DATA/scenes`; the task log is under `$CRAMERA_DATA/laboratory`. Stopping
the viewer also stops a transfer process it owns.

### The longer PR2 lab workflow

**PR2 lab workflow (CRAM)** is a second demo on the same page, run, followed and
replayed like the transfer. The PR2 re-sorts the rack (A1 → A3, A2 → B2, B1 → A1),
drives to the sample refrigerator and opens and closes its door, then drives to the
centrifuge and opens and closes its lid, driving between its stands at the bench. The
lid's hinge sits too far back for the PR2 to open it fully by its handle from the
bench, so it pulls the lid to about 0.6 rad by the handle and pushes it on to 1.3 rad
from below, and closes it the same way in reverse. Only one PR2 demo runs at a time;
while one runs, the other offers no **Run the demo**.

The workflow measures every vessel it sets down (within a millimetre of its new
slot), that the door and the lid were opened and are closed again, and the same grasp
and collision checks as the transfer.

These robot demos use CRAM's **kinematic simulation**, including motion and grasp
checks. It is separate from the manual MuJoCo contact simulation below. Its saved
recording is produced by the local run and includes the PR2 model and trajectory.

The same native task can also run from a terminal in this environment:

```bash
cramera-laboratory-transfer --recording medical_lab_pr2_run_01 --port 0
```

Use a new recording name each time with the command-line tool. The page chooses
unused names automatically.

## Add MuJoCo for manual workbench controls

The page retains **Simulate with contact physics** and
**Set up MuJoCo contact physics**. Stop the viewer with Ctrl-C, then from the
repository root in the same virtual environment:

```bash
python -m pip install -e './packages/plugins/laboratory[physics]'
cramera --no-browser --keep-running
```

If the environment has no pip, run `python -m ensurepip --upgrade` first. Install
on the machine running the Python viewer and restart that viewer afterwards.
The official `mujoco` wheel includes the engine; no separate engine download is
needed. See the
[MuJoCo installation documentation](https://mujoco.readthedocs.io/en/stable/python.html#installation).

For the small workbench and manual controls alone, CRAM and ROS are unnecessary.
A separate Python 3.11-or-newer environment can install just these packages:

```bash
python3 -m venv .venv-workbench
source .venv-workbench/bin/activate
python -m pip install -e ./packages/protocol -e ./packages/viewer \
  -e './packages/plugins/laboratory[physics]'
cramera --no-browser --keep-running
```

In that environment the page shows the workbench and explains how to add the
full PR2 runtime. MuJoCo alone does not provide the PR2 preview or robot plan.

The manual simulation offers:

- Pull and release vessels and the stopper; gravity, friction and contacts
  determine their motion.
- Set vessel fills and inspect liquid volumes, pouring and spills.
- Read or tare the scale.
- Open and close the centrifuge, secure seated samples, read its manual and
  requirements, and start or stop a cycle.
- Open and close the refrigerator and drawer and inspect their contents.
- Fill dispenser reservoirs, dose into an aligned vessel, stop and resume.
- Reset or stop the simulation, and inspect the five device bundles and URDFs.

The simulation is shared by browsers connected to this viewer. Its generated
scene is `aicor_medical_lab_contact_physics`; starting a new simulation refreshes
that scene's assets. Original packaged assets stay unchanged. Keep `LICENSE.txt`,
`NOTICE.md` and `rights.json` with any copies.

## Troubleshooting

- **No Medical lab link:** activate the environment containing the plugin,
  restart `cramera`, and check that `/api/info` lists `laboratory`.
- **Workbench appears without PR2:** follow **Set up the local PR2 demo** on the
  page. Install the full stack, source ROS and the robot-resource workspace, and
  restart the viewer from that environment. The page reports preview errors.
- **MuJoCo still missing:** install `[physics]` using that environment's
  `python -m pip`, then restart the viewer.
- **Run fails:** read the error on the page and the task log under
  `$CRAMERA_DATA/laboratory`. Check the CRAM revision and sourced robot resources.
  A run ended by a signal such as `SIGKILL` was stopped from outside, for example
  when memory ran out; its log may show only harmless startup warnings.
- **Port already in use:** choose a free `--port` and open its matching URL;
  `--keep-running` preserves the other viewer.
- **No WebGL context:** use a browser with working WebGL. Python runs the demo,
  but rendering the models requires browser graphics support.
