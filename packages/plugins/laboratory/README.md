# cramera-laboratory

**Medical lab** is a dedicated page in cramera's top bar, with its own 3D view,
controls and playback timeline. It opens the compact AICOR workbench with the
real PR2, runs the complete vessel-transfer demo locally, follows its live motion
and replays its recording. The small scene and five device bundles are shipped;
the expanded room is excluded.

## Local PR2 setup

The robot preview and demo require the full CRAM workspace, `cramera-bridge`,
ROS 2 Jazzy and its robot descriptions, including `iai_pr2_description`. From the
cramera repository root, after building the ROS workspace described in the
[local setup guide](../../../docs/local-medical-lab.md):

```bash
source /opt/ros/jazzy/setup.bash
source "$HOME/ros_ws/install/setup.bash"  # adjust to your ROS workspace
python3 scripts/install_stack.py --venv "$PWD/.venv"
source .venv/bin/activate
cramera --no-browser --keep-running
```

Open [Medical lab](http://127.0.0.1:8711/plugins/laboratory/laboratory.html).
**Run the demo** starts a fresh local transfer, follows it live and opens its
recording on completion. Further runs preserve previous recordings under unused
names. **Open the recording** and the timeline provide replay; **Show lab and PR2**
returns to the initial pose. **End the run** stops the active process.

The plan picks a vessel from A1, lifts it and places it in A3. It uses CRAM's
kinematic simulation and saves the recording only after its action, motion and
contact checks succeed. The manual MuJoCo simulation is a separate mode.
The current APIs were verified with
[CRAM e69fee4](https://github.com/cram2/cognitive_robot_abstract_machine/commit/e69fee4d14589c0a32826fcd54b42a1c6818d185).

The plugin's `[bridge]` extra installs only `cramera-bridge`; the full-stack
installer adds the native workspace packages. Missing native dependencies leave
the small workbench available with setup help. No CRAM package is imported by
this plugin: paths and protocol documents cross the bridge boundary. The viewer
owns the transfer process and stops it on shutdown.

`cramera-laboratory-transfer --recording my_new_run --port 0` runs the same task
from a terminal in the full environment. Use an unused name for each CLI run;
the page chooses these names automatically.

## Manual MuJoCo contact simulation

From the repository root in the viewer's environment:

```bash
python -m pip install -e './packages/plugins/laboratory[physics]'
```

Restart the viewer and choose **Simulate with contact physics** on the Medical
lab page. **Set up MuJoCo contact physics** explains installation into the same
environment; its help remains available after installation. This mode needs
neither CRAM nor ROS. Without MuJoCo the workbench still opens, and simulation
routes report the missing dependency with status 503. The
[official Python package](https://mujoco.readthedocs.io/en/stable/python.html#installation)
includes the engine.

All compact workbench controls remain available:

- Pulling and releasing vessels and the stopper with a bounded spring; only reset
  writes poses directly.
- Filling, sloshing, pouring, catching and spilling liquid, with volume accounting.
- Scale readings from contact load, with taring.
- A centrifuge with a driven lid and rotor, sample clamps, load balance checks,
  operating manuals and evaluated start requirements.
- Force-limited refrigerator and drawer drives and storage contents.
- Two dispenser reservoirs and dosing into an upright, open, aligned vessel.

The liquid is a reduced free-surface model; pressure, wetting and chemistry are
not modelled. The scale filters contact load. The centrifuge secures vessels only
when seated and still; starting requires a closed lid and the manual's sample
and balance requirements. Dosing stops if the vessel leaves its receiving
position. The viewer owns one simulation shared by browser clients and closes it
at shutdown.

## Assets

`resources/aicor_medical_lab` holds the compact scene. The independent centrifuge,
dual dispenser, scale, tube rack and refrigerator are under
`resources/laboratory_devices`; the centrifuge manuals are under
`resources/centrifuge_manuals`.

These assets use `LicenseRef-AICOR-Laboratory-Assets`, separately from the software
licence. Keep `LICENSE.txt`, `NOTICE.md` and `rights.json` with every authorized
copy. Installing the scene preserves these files; the PR2 preview also preserves
the robot resources' source manifests and available licence notices.

## Tests

```bash
python -m pytest -q packages/plugins/laboratory/test
```

Physics tests need `[physics]`. The bridge owns native CRAM integration tests;
the plugin's tests exercise the page, controls, process lifecycle, reruns, live
proxy and missing-dependency behavior without CRAM.
