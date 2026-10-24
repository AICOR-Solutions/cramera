# End-to-end scenarios

These scenarios run the whole stack the way a person uses it, against the real CRAM
workspace and ROS 2. They catch what the package tests cannot see: a viewer that starts
without its plugins, a plan the builder writes that does not run, a recording that is
saved but does not replay.

| Scenario | What happens | Checked |
| --- | --- | --- |
| `test_plan_builder.py` | A viewer starts with every plugin and coraplex's apartment as an environment. A PR2 plan (park the arms, raise the torso, drive to the counter, pick the milk up) is composed through the plan builder's routes, saved, exported as a demo and run from the builder. | The builder offers the PR2, the apartment, the milk and the actions. The plan is saved and its demo file is written. The run ends with code 0. The saved recording is listed, its plan succeeded, the milk ends higher than it started, and the viewer serves every file the replay loads. |
| `test_cram_demo.py` | coraplex's own apartment demo (`coraplex_bullet_world_demo`, the place setting) runs unchanged under `cramera-live`. Its recording is saved through the live routes and then opened in a viewer. | The world and plan are published while it runs. The plan succeeds. The recording is finalized, saved and listed. The saved scene has the environment, the robot, the plan and every frame, and the viewer serves every file the replay loads. |

Tests marked `xfail(strict=True)` describe what is still broken, each naming its issue:

- [#36](https://github.com/AICOR-Solutions/cramera/issues/36): recorded action nodes stay `CREATED` and get no frames.
- [#37](https://github.com/AICOR-Solutions/cramera/issues/37): objects a coraplex demo fixes to the world are not tracked, so they don't move in the replay.

Once a fix lands, its test passes, `strict` turns that pass into a failure, and the mark
has to be removed.

## Running them

Install the whole stack and source ROS 2 first:

```bash
python3 scripts/install_stack.py --dev
source /opt/ros/jazzy/setup.bash
```

Then, from the repository root, inside that environment:

```bash
python -m pytest -q -rxX tests/end_to_end
```

The scenarios take about six minutes, most of it the two robot runs. They are skipped
where the CRAM workspace, the bridge, the plan builder or ROS 2 is missing, so CI
(which installs neither) does not run them. `cramera-live` publishes on the fixed
port 8765, so stop any other live publisher first.
