# cramera-plan-builder

A plugin of the cramera viewer that composes a robot plan by drag and drop, places the
plan's robots, objects and targets in the 3D view of an environment, attaches
constraints written in plain language to its steps and runs the demo generated from it.

Install it next to the viewer; the viewer finds it through the `cramera.plugins` entry
point and shows a **Plan View** panel: the plan of a replayed recording as the builder's
step cards, each with every parameter and constraint it was recorded with, following the
playhead. The builder page itself is served at `/plugins/plan-builder/builder.html`.

```bash
pip install -e packages/plugins/plan-builder
cramera
```

- **Catalog.** Robots are the concrete robot annotations of the CRAM workspace with a
  model description; which arms and torso states a robot offers is read from the parts
  its annotation declares. Objects are the meshes beside coraplex and the models of
  every object library, surface types the native annotation classes with a supporting
  surface. Environments are the viewer's bundles without a robot model. Without the
  CRAM workspace the catalog names the missing modules and offers environments only.
- **A URDF as the environment.** The Environment section's **Browse…** opens a picker
  of the viewer's machine's folders and their URDF and xacro files, reopening on the
  folder it showed last; its path field takes such a file's path too, such as
  `coraplex/resources/worlds/apartment.urdf`. `cramera-bridge` copies it with every mesh
  it names (`package://` references resolved) into a new bundle of the local scenes
  (`CRAMERA_DATA/scenes`), which the builder then offers and chooses. Meshes it cannot
  find are named in the page's message and left out.
- **Object libraries** are directories with an `objects` folder of models, each a
  `model.urdf` with its meshes beside it, named by the library's `collection.json`
  where it has one. The repository's `resources/` holds `private_meshes`
  ([sunava/private_meshes](https://github.com/sunava/private_meshes)) as a git
  submodule (`git submodule update --init`); further libraries are named in
  `CRAMERA_OBJECT_LIBRARIES`, separated like `PATH`. A library model is identified as
  `<library>/<path of its URDF>`, drawn with its links in the 3D view, and merged into
  the demo's world free to move and graspable, its links named below the object's
  identity. Its environments, such as `environments/aicor_medical_lab`, become plan
  environments when the viewer is given that directory with `--scenes`.
- **CRAM** is reached through `cramera-bridge` only (the `bridge` extra); the plugin
  imports nothing of the CRAM workspace. `cramera_bridge.plans.workspace` hands the
  catalog over as the protocol's `RobotModel`, `ObjectModel` and `ActionCatalog`
  documents, and a generated demo hands its plan as a `DemoDocument` to
  `cramera_bridge.plans.command`, which builds the world, turns the steps into native
  actions and performs or stages them. A step the CRAM side refuses (an arm the robot
  lacks, an object without a grasp, an annotation or surface the world lacks, an
  unknown action) is answered with the same status and message as before, raised as
  a `cramera_bridge.exceptions` error.
- **Actions** are discovered, not listed by hand: every module below
  `coraplex.robot_plans.actions` is imported on its own, and every concrete action
  dataclass defined there becomes a schema (`cramera_bridge.plans.actions`). Each init field is
  resolved in the class that declares it and mapped to a kind by an ordered list of
  type rules:

  | Field type | Kind | Form control |
  | --- | --- | --- |
  | `Body` | body | the plan's objects |
  | a semantic annotation class, such as `Tool` (not a robot part) | annotation | the live world's entities of that class, else the name typed |
  | an enumeration | enum | the members; `Arms` and `TorsoState` as the robot's parts allow |
  | `Pose` | pose | the pose editor and a handle in the 3D view; `target_location` of an action acting on an object also takes a surface |
  | `Pose \| Iterable[Pose]` | pose or surface | a pose, or a surface sampled when the step runs |
  | `float`, `int`, `bool`, `str` | number, integer, boolean, text | inputs, the default as placeholder |
  | `GraspDescription` | grasp | none: derived from the action's arm and object |

  `Optional[X]` is classified by `X`. A field of another type, or one whose type cannot
  be resolved, is left at its default and listed as hidden; without a default it makes
  the action unavailable, and the palette says why. A module that fails to import is
  named in the catalog with its error. Required fields come first in a step's form, the
  others fold under "More options". A robot is offered an action when every required
  enumeration has a member it allows.
- **Plans** are saved under `CRAMERA_DATA/plan-builder/plans`. A step names its action
  by class name and gives its fields' values by field name (format 1.1). A plan saved
  with the step kinds of format 1.0 loads as the actions they stood for: `park_arms` as
  `ParkArmsAction`, `move_torso` as `MoveTorsoAction`, `navigate` as `NavigateAction`,
  `transport` as `TransportAction`, `pick_up` as `PickUpAction`, `place` as
  `PlaceAction`. A step whose action the workspace no longer offers, or whose values
  no longer fit the action, loads and shows why on its card; writing or running its
  demo is refused with the step and field named.
- **Demos** are generated from `templates/plan_demo.py` and written to
  `CRAMERA_DATA/plan-builder/demos`, or to the directory `CRAMERA_PLAN_BUILDER_OUTPUT`
  names; never into a CRAM checkout. A demo carries its plan as JSON and runs it as
  `cramera_bridge.plans`' `RobotTaskDemo`: `python <demo>.py` performs the selected
  robot's steps, each built generically from its action's class and values, and saves
  the recording into the local scenes directory, `--stage` only publishes the world
  until it is stopped, `--port` chooses where it is published.
- **Replays.** When the viewer shows a recording with a plan, the panel comes to the
  front and lists the plan's steps as the builder's cards (`web/steps.css`, shared
  with the builder page): a plan's steps are its outermost actions, one list per
  recorded plan, titled with the robot that performed it. The step whose recorded
  frames hold the playhead is marked running and scrolled into sight; a click on a
  step asks the viewer for its first frame.
- **Runs.** The builder starts one demo at a time as a child process of the viewer, in
  its own process group, keeps the newest 64 KiB of its output, and stops it with its
  group. The demo ends by itself when the viewer goes away, since it watches the pipe
  the viewer holds open. Demos publish on the live publisher's port, or on
  `CRAMERA_PLAN_BUILDER_PORT`.
- **Constraints** are compiled by the rule book `rules/constraints.json` into the
  monitor the live publisher observes (`VectorsAligned`, `HeightMonitor`,
  `DistanceMonitor`) and into switches of the step's own action: a rule's switch names
  a boolean field, which it turns on for every action that has it (looking at the
  operation site on a transport). The builder page attaches the monitors to the running
  plan's nodes through the live publisher's `/constraint` route, and moves objects
  through `/move`.
