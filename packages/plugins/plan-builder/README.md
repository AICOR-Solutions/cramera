# cramera-plan-builder

A plugin of the cramera viewer that composes a robot plan by drag and drop, places the
plan's robots, objects and targets in the 3D view of an environment, attaches
constraints written in plain language to its steps and runs the demo generated from it.

Install it next to the viewer; the viewer finds it through the `cramera.plugins` entry
point and shows a **Plan builder** panel that opens the builder page.

```bash
pip install -e packages/plugins/plan-builder
cramera
```

- **Catalog.** Robots are the concrete robot annotations of the CRAM workspace with a
  model description; which steps and arms a robot offers is read from the parts its
  annotation declares. Objects are the meshes beside coraplex, torso states and surface
  types the native enumerations and annotation classes. Environments are the viewer's
  bundles without a robot model. Without the CRAM workspace the catalog names the
  missing modules and offers environments only.
- **Plans** are saved under `CRAMERA_DATA/plan-builder/plans`.
- **Demos** are generated from `templates/plan_demo.py` and written to
  `CRAMERA_DATA/plan-builder/demos`, or to the directory `CRAMERA_PLAN_BUILDER_OUTPUT`
  names; never into a CRAM checkout. A demo carries its plan as JSON and runs it as a
  `RobotTaskDemo`: `python <demo>.py` performs the selected robot's steps and saves the
  recording into the local scenes directory, `--stage` only publishes the world until it
  is stopped, `--port` chooses where it is published.
- **Runs.** The builder starts one demo at a time as a child process of the viewer, in
  its own process group, keeps the newest 64 KiB of its output, and stops it with its
  group. The demo ends by itself when the viewer goes away, since it watches the pipe
  the viewer holds open. Demos publish on the live publisher's port, or on
  `CRAMERA_PLAN_BUILDER_PORT`.
- **Constraints** are compiled by the rule book `rules/constraints.json` into the
  monitor the live publisher observes (`VectorsAligned`, `HeightMonitor`,
  `DistanceMonitor`) and into switches of the step's own action (looking at the
  operation site on a transport). The builder page attaches the monitors to the running
  plan's nodes through the live publisher's `/constraint` route, and moves objects
  through `/move`.
