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
  folder it showed last, and loads a file as soon as it is picked; the path field with
  its **Load** button takes such a file's path too, such as
  `coraplex/resources/worlds/apartment.urdf`. `cramera-bridge` copies it with every mesh
  it names (`package://` references resolved) into a new bundle of the local scenes
  (`CRAMERA_DATA/scenes`), which the builder then offers and chooses. Meshes it cannot
  find are named in the page's message and left out.
- **Annotation fields** (a handle, a drawer, a door, …) offer a drop-down of the chosen
  environment's annotations of their class, as a plan run finds them, and the live
  world's surfaces while it runs. An environment without prim semantics, such as one
  loaded from a URDF, gets the annotations CRAM's `WorldReasoner` infers, each named
  after the body it is rooted in (`handle_cab1_top_door`).
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
  | `VolumetricBoundingBox` | region | the regions of the scene: the whole table, a zone of the profile, or the square around a marker |
  | `type[SemanticAnnotation]` | enum | the kinds of the plan's free objects (`object`, `block`) |

  `Optional[X]` is classified by `X`. A field of another type, or one whose type cannot
  be resolved, is left at its default and listed as hidden; without a default it makes
  the action unavailable, and the palette says why. A module that fails to import is
  named in the catalog with its error. Required fields come first in a step's form, the
  others fold under "More options". A robot is offered an action when every required
  enumeration has a member it allows.
- **Skills.** A robot profile with `skills` makes the palette offer those instead of
  the native actions, until "developer mode" is on. A step of a skill shows only the
  fields the skill names, all of them unfolded, and says under its name what the skill
  does, as the skill's documentation puts it (Park arms moves both arms, Pick picks with
  the arm that reaches); developer mode shows the action's every field again.
- **Poses** of robots, objects, targets and markers are edited in the world frame,
  whose origin is the environment's: x, y and z in metres, and the heading as
  "rotation (°)" around the vertical axis, 0° facing along the world's x axis. Each
  input says so as its tooltip.
- **The 3D view.** Pressing on a robot, object or target and dragging moves it over
  the horizontal plane through it, picked before or not; a click picks it and puts
  the handles on it, which move it (an object also in height) or turn it ("Turn"). Pressing beside
  every marker turns the camera. A label in its top left corner says what it shows:
  "Plan (not running)" (adding that the robot stands as the real robot does while
  the plan builder mirrors its posture), "Simulation (live)", "Simulation (live
  scene)" for a staged scene, or "Real robot (live)" during a run on the real robot.
  A folded legend in its top right corner names each kind of mark in its colour
  (`LEGEND` in `plan-scene.js`).
- **Composing.** An action clicked in the palette is added as the last step; one
  dropped on a step is inserted before it, one dropped on the place below the last
  step is added after it.
- **Unsaved changes.** While the plan changed since it was last saved, opened or
  started, "New", opening a saved plan and starting from a template ask before they
  replace it, and the browser asks before the page is closed or left.
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
  names; never into a CRAM checkout. The command a written demo is reported to run
  with starts with the words `CRAMERA_PLAN_BUILDER_RUN_PREFIX` names, such as
  `docker compose exec viewer` when the viewer runs in a container. A demo carries its plan as JSON and runs it as
  `cramera_bridge.plans`' `RobotTaskDemo`: `python <demo>.py` performs the selected
  robot's steps, each built generically from its action's class and values, and saves
  the recording into the local scenes directory. Every grasp first detects its object
  (coraplex's `DetectBeforeGrasp`), whichever executor runs it. `--executor physics`
  performs the steps in a MuJoCo physics simulation instead of kinematically, both
  answering a detection from the simulated world as far as the robot's camera sees it;
  `--executor perceived_physics` does so answering every detection through RoboKudo
  (the analysis engine `CRAMERA_PERCEPTION_ENGINE` names, looking through the robot's
  simulated camera, hosted in the demo's process), `--stage` only publishes the
  world until it is stopped, `--port` chooses where it is published.
- **Replays.** When the viewer shows a recording with a plan, the panel comes to the
  front and lists the plan's steps as the builder's cards (`web/steps.css`, shared
  with the builder page): a plan's steps are its outermost actions, one list per
  recorded plan, titled with the robot that performed it. The step whose recorded
  frames hold the playhead is marked running and scrolled into sight; a click on a
  step asks the viewer for its first frame.
- **Runs.** "Run plan" performs the plan kinematically, "Dry-run in physics" in MuJoCo
  and "Run on robot" on the real robot; a robot profile's `executors` say which
  executor each run mode uses and which modes the robot offers at all (by default
  `perform` is kinematic and `simulate` physics; `robot` has no executor unless the
  profile names one). While the profile's `robot` mode runs on the real robot, a
  robot of the profile's model is the real robot: the page offers neither removing it
  nor a start pose for it, and its marker does not move, since it starts where it
  stands.
  The builder starts one demo at a time as a child process of the viewer, in
  its own process group, keeps the newest 64 KiB of its output, and stops it with its
  group. The demo ends by itself when the viewer goes away, since it watches the pipe
  the viewer holds open. Demos publish on the live publisher's port, or on
  `CRAMERA_PLAN_BUILDER_PORT`.
- **Validation.** "Validate" posts the plan to the `validate` route, which runs
  `cramera_bridge.plans.validating` as a child process: every step of the selected
  robot is tried one after another in a copy of the twin, kinematically, so nothing
  moves (coraplex's `PlanValidation`). Each step's card shows whether it is valid,
  assumed (a detection the camera does not see now, answered from the twin), failed
  with its reason (unreachable, collision, not perceived, ambiguous, a skill the
  profile does not offer) or unchecked after a failure. A step whose arm is
  `automatic` (the default of a profile's pick) is given the arm that reaches, shown on
  its card; the run grounds it the same way before it starts. "Run on robot" is enabled
  only for the plan as it passed its validation: any edit of the plan or its objects
  invalidates it, as does a live object found more than 2 cm from its pose in the
  plan (`SCENE_TOLERANCE`), until the plan is validated again; the `run` route refuses
  a robot run of any other plan unless the request overrides the gate, which developer
  mode does.
- **Detecting.** A step whose action looks in a region (Detect) starts looking at the
  whole table. A later step of the same robot can name what it finds in an object
  field, as `detected:<step id>`: when the plan is built, that is the one object of the
  plan the detection's query finds, which the detection perceives again when it runs.
  "Scan scene" in the objects list posts the plan to the `scan` route, which runs
  `cramera_bridge.plans.scanning` as a child process: the robot looks at the table live
  where its camera sees it, else the twin's objects are taken as assumed; a robot
  profile's `simulatedScene` names a plan file whose objects a simulated camera sees.
  Found objects move the plan's objects, and one the plan lacks becomes a copy of the
  library model of its type and the `color` its collection names.
- **Placing.** A field taking a surface (a place's `target_location`) also takes a
  zone of the robot profile (`zones`: named rectangles on the robot's table, in the
  frame of the robot's pose), on top of another object (one of the plan's or
  `detected:<step id>`), or a free-place marker. These are resolved when the plan is
  grounded, each in the copy of the twin as the steps before left it: a zone's free spot
  within reach nearest its centre (a grid one object and twice a 1 cm clearance apart),
  the top of the object below plus half the placed object's height, or the marker's
  position and heading resting on the surface below it. The run grounds the plan the
  same way before it starts and puts each object down at the pose found; the run
  measures where it ended (`placedPosition.<step>`). The 3D view shows the zones on the
  table. A marker slides over the surface below it (x, y and yaw only; the table's top,
  else the floor), stays in sync with its x, y and rotation fields, and turns green or red
  while dragged by a quick check against what the robot reaches: the `reach` route
  answers, once per robot model, a sphere around each arm's shoulder that its tool
  stays within (`cramera_bridge.plans.reaching`). Red is out of reach for certain;
  green may still fail the validation, which stays the gate.
- **Constraints** are compiled by the rule book `rules/constraints.json` into the
  monitor the live publisher observes (`VectorsAligned`, `HeightMonitor`,
  `DistanceMonitor`) and into switches of the step's own action: a rule's switch names
  a boolean field, which it turns on for every action that has it (looking at the
  operation site on a transport). The builder page attaches the monitors to the running
  plan's nodes through the live publisher's `/constraint` route, and moves objects
  through `/move`.
