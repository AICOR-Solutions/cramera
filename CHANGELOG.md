# Changelog

What landed in cramera, by week and area. Entries are features, not commits; hashes
in entries up to week 43 point into the `cramera-port` branch of the CRAM fork, from
which this repository was mirrored until 22 Oct 2026.


## 1.0.0 · in progress since 22 Oct 2026

### Removed
- **The Tour, Knowledge, Steps, Plan tree and Chart states tabs.** The knowledge
  graph duplicated what EQL answers, the viewer's own plan tree and statechart tree
  duplicated the questions plugin's Plan and Statechart graphs, the timeline already
  marks the steps, and the Tour panel went with its browser module: `cramera-offline`
  keeps the storyboard and bundle check routes and its commands.
  `GraphViewName.KNOWLEDGE` stays in the protocol for the API.
- **The models panel, the laboratory, the workshop and the cable lab.**
  `cramera-models`, `cramera-laboratory`, `cramera-workshop` and `cramera-cable-lab`
  are gone with their panels and pages, their protocol modules
  `cramera_protocol.models`, `cramera_protocol.laboratory`,
  `cramera_protocol.workshop` and `cramera_protocol.cable_lab`, `PluginName.MODELS`
  and `PluginName.WORKSHOP`, and the vendored Plotly. The navigation group
  `laboratory` stays for plugins outside this repository; `cramera_protocol.rights`
  stays for the scene builder.

### Added
- **Primitive shapes in the scene builder.** The library's new **Shapes** category
  offers a box, a cylinder and a sphere (`primitives/box`, …), one metre across, so
  their size is set in metres. Every placed instance can carry a description of what
  it is and how it works, saved with the draft (`InstanceKey.DESCRIPTION`), so the
  object a shape stands for can be designed later.

  ![Placing, sizing and describing shapes](https://raw.githubusercontent.com/AICOR-Solutions/cramera/pr-media/issue-41/walkthrough.gif)
- **Objects of the meshes library in the plan builder.** `resources/private_meshes` is
  a submodule of [sunava/private_meshes](https://github.com/sunava/private_meshes), and
  the builder offers every model of it, and of any library `CRAMERA_OBJECT_LIBRARIES`
  names, beside the meshes of coraplex: its URDF is drawn in the 3D view and merged
  into the demo's world as a free, graspable object.

  ![A library object in the plan builder](https://raw.githubusercontent.com/AICOR-Solutions/cramera/pr-media/issue-17/builder.png)
- **A film of a recording.** The timeline's video button films the shown recording as a
  WebM with a cinematic camera: it cuts between wide shots and close-ups on every pick
  and place, slows down around them and saves the film when the recording ends; the
  layer *Cinematic camera* shows the same shots while playing.

  ![A filmed pick-up](https://raw.githubusercontent.com/AICOR-Solutions/cramera/pr-media/issue-13/film.gif)
- **The live view says what it is doing.** A badge in the top bar shows whether the
  viewer is off, connecting, live or has lost the publisher; the Live tab names what
  the publisher offers and whether it records, the timeline says whether it follows
  the run or waits for one, and an ended run offers *Save this run…*.

  ![The live view's states](https://raw.githubusercontent.com/AICOR-Solutions/cramera/pr-media/issue-15/states.gif)
- **The Perception tab.** Every perception step of the shown recording's plans, or of
  the live plan, with what it was asked (its action's parameters), how it ended, why
  it failed, and the objects it reported, which light up in the 3D view. The bridge
  records a step's reported objects (`perceived`) and any node's failure reason
  (`reason`) on the plan's nodes, and names a class parameter by its class.

  ![The Perception tab](https://raw.githubusercontent.com/AICOR-Solutions/cramera/pr-media/issue-25/perception.png)
- **What perception saw.** A perception step in the Perception tab shows the images of
  what it saw, also when it failed: in simulation the robot's camera view drawn from the
  world model, with the reported objects outlined, and its depth; on the real robot also
  every image RoboKudo's visualizer publishes on `<pipeline>/<annotator>/output_image`
  while the step runs. A live plan's node lists them in `images`, each served by the
  publisher's `/perception_image` route; a recording keeps them as PNG files in its
  `perception/` directory.

  ![What a perception step saw](https://raw.githubusercontent.com/AICOR-Solutions/cramera/pr-media/issue-25-images/perception_tab.png)
- **The Scene graph tab.** The scene page browses the shown world as a tree, the way
  the Ontology tab browses classes: its models with their links nested by joint, its
  free objects and the robot's part annotations. A node shows its fields, what it
  depends on and what refers to it, each a click away, and lights up in the 3D view;
  clicking a part in the 3D view chooses its node.

  ![Browsing the scene graph](https://raw.githubusercontent.com/AICOR-Solutions/cramera/pr-media/issue-24/walkthrough.gif)
- **Another logo in the top bar.** `cramera --logo FILE` (or `CRAMERA_LOGO`) and
  `cramera-export-site --logo FILE` show another image instead of the AICOR logo on
  every page, served at `/api/logo`; `--logo-text` says what it shows.

  ![Another logo in the top bar](https://raw.githubusercontent.com/AICOR-Solutions/cramera/pr-media/issue-27/custom_builder.png)
- **One command installs the whole stack.** `python3 scripts/install_stack.py` puts the
  viewer, every plugin, `cramera-bridge` and the CRAM workspace (cloned next to the
  checkout when missing) editable into one uv environment that sees ROS 2's Python
  packages, leaving out CRAM's own earlier `cramera` so this repository's viewer is
  installed. `--viewer-only`, `--with-usd`, `--dev` and `--dry-run` choose less or more.
- **End-to-end scenarios.** `tests/end_to_end` runs the whole stack with the CRAM
  workspace and ROS 2. A PR2 plan in the apartment is composed through the plan
  builder's routes, saved, exported, run and replayed. coraplex's apartment demo runs
  unchanged under `cramera-live`, is checked while it runs, then saved and replayed.
  CI skips the scenarios; `tests/end_to_end/README.md` says how to run them.

  ![The plan builder's run replayed](https://raw.githubusercontent.com/AICOR-Solutions/cramera/pr-media/issue-33/apartment_PR2_pr2_apartment_pick_85.png)
- **Recorded plans keep every step parameter and constraint.** Every plan node the
  live publisher describes renders each field of its designator by name
  (`LivePlanNodeKey.PARAMETERS`): an enumeration member by its name, an object by its
  key, a pose by its position, a switch as on or off, a nested description by its
  fields. A recording's plan tree stores them (`PlanNodeKey.PARAMETERS`) together
  with the constraints attached to each node and their last observation
  (`PlanNodeKey.CONSTRAINTS`, `PlanConstraintKey`). Recordings written before keep
  showing the arm and target they have.

- **Resizable panes and a foldable query slot.** A divider between the scene and
  the side column drags to give either side more width (a quarter to three quarters,
  double-click for halves), a divider below the query slot drags to give it more or
  less of the column, and the query slot's head has a button that folds it to its
  heading so the panels take the column. All three are remembered in the browser
  under `PageStorageKey.SPLIT`, `PageStorageKey.QUERY_SPLIT` and
  `PageStorageKey.QUERY_FOLDED`.
- **Scenes directories inside scenes directories.** A child of a scenes directory
  that is not a bundle but holds an `index.json` or bundles is a further scenes
  directory of the same source, and so on below it. The repository's own demo bundles
  moved to `demo/standard_scenes`; `cramera --demo-scenes demo` shows them with every
  scenes repository cloned next to them, which git ignores. The scene builder names
  such a nested library root `<source>-<directory>`.
- **A new viewer replaces the old one.** `cramera` started on a port another cramera
  viewer holds stops that viewer and takes the port; `--keep-running` keeps the
  earlier behaviour of failing with *address already in use*.

### Changed
- **The protocol names actions, robots and plan node kinds itself.** Plans name actions
  and robot models by snake_case identifiers (`pick_up`, `pr2`) and recordings name plan
  node kinds as `action`, `motion`, `sequence`, … instead of CRAM's class names.
  `cramera_bridge/names.py` is the one table between the two, so a rename in CRAM
  changes only that table. Plans are written in format 1.2; plans of 1.1, naming the
  class names, are translated through the names the catalog lists each identifier as
  having been saved under (`savedAs`), and earlier recordings' class names are read as
  their kinds.

  ![A plan sent with class names and saved with identifiers](https://raw.githubusercontent.com/AICOR-Solutions/cramera/pr-media/issue-49/saved_plan.png)
- **Things a robot takes hold of are objects from the start.** Every body that a
  semantic annotation of something with grasps describes (Milk, Bowl, Spoon, Cup, …) is
  published and recorded as an object, however the world attaches it. Parts of other
  things (handles, rims, doors, drawers, furniture) are not. A demo that fixes its
  objects to the environment, like coraplex's apartment demo, now shows them carried
  in the live view and the replay instead of standing still in the environment.

  ![Carrying the bowl in the replay](https://raw.githubusercontent.com/AICOR-Solutions/cramera/pr-media/issue-37/carrying.gif)
- **A sub-action is shown by what it matches.** A composite action's sub-action that
  coraplex leaves to be found, such as TransportAction's `pick_up`, shows as the
  action it matches and what it states about it (`MoveAndPickUpAction: navigate
  NavigateAction, …`) instead of the match's internal fields; a value left open shows
  as `any <type>`.

  ![A transport's sub-actions in the Plan View](https://raw.githubusercontent.com/AICOR-Solutions/cramera/pr-media/issue-38/after.png)
- **An action shows what its motions went through.** coraplex performs an action's
  motions without starting the action node itself, so recorded actions stayed
  `CREATED` and named no frames. An action coraplex left unstarted now shows the
  status of its motion that started last, running until its motions ran or the plan
  ended. Recordings then know when each step ran, and the Plan View follows the
  playhead again.

  ![The Plan View following the playhead](https://raw.githubusercontent.com/AICOR-Solutions/cramera/pr-media/issue-36/after.png)
- **The plan builder's environment and robots are clearer.** The builder has an
  Environment section and a Robots section with one card per robot; the card whose plan
  is edited is marked, picking a robot in the 3D view selects it, and every robot has
  its name above it.

  ![The builder's environment and robots](https://raw.githubusercontent.com/AICOR-Solutions/cramera/pr-media/issue-14/after.png)
- **The theme switch is in the top bar.** A Dark/Light switch beside the version
  replaces the View menu, which held only the theme.

  ![The theme switch in the top bar](https://raw.githubusercontent.com/AICOR-Solutions/cramera/pr-media/issue-26/after_light.png)
- **The plugins' extra is called `bridge`.** `cramera-questions[bridge]` and
  `cramera-plan-builder[bridge]` name what they install, `cramera-bridge`; the
  former `cram` extra is gone.
- **cramera-cram is cramera-bridge.** The package that connects cramera to CRAM is
  `cramera-bridge` now, imported as `cramera_bridge`, in `packages/bridge`; the
  plugins' `bridge` extra installs it, coraplex still finds its visualization as
  `cramera`, and the live publisher reports itself as `cramera-bridge`. An
  environment that still holds `cramera-cram` registers that visualization twice, so
  uninstall it (`pip uninstall cramera-cram`); `scripts/install_stack.py` does.
- **Scenes are drawn in colour.** Every model loaded from a URDF is lit like the
  scene's own objects:
  - its URDF and COLLADA materials become physically based ones, keeping their colour,
    texture and transparency;
  - lights a model file brings are removed, and blown-out whites are toned down;
  - a COLLADA mesh without materials takes its URDF colour, as STL and OBJ meshes do;
  - an environment part that its description leaves uncoloured gets the colour of what
    its link names (countertop, table, cabinet, handle, wall, …), for any environment;
    authored colours always win.

  The scene builder draws its URDFs the same way. The URDF colours of bare meshes need
  the semantic_digital_twin fix on `sunava/cognitive_robot_abstract_machine`, branch
  `fix/urdf-mesh-colors`.

  ![The apartment and the PR2 in colour](https://raw.githubusercontent.com/AICOR-Solutions/cramera/pr-media/colors/after_pick.png)
- **The Plan builder panel is the Plan View.** The viewer's panel of
  `cramera-plan-builder` is named Plan View and holds only the replayed recording's
  plan: its step cards now show every parameter the step was recorded with,
  labelled as the builder labels the field, and each constraint as a chip with its
  monitor and last observation. The panel's description and its links to the
  builder page are gone; the page stays at `/plugins/plan-builder/builder.html`.
- **Only cramera-bridge imports CRAM.** The plan builder's CRAM side (action
  discovery, steps, arms, world, surfaces, the generated demo's command) moved from
  `cramera_plan_builder.cram` to `cramera_bridge.plans` with its tests; the builder
  reads its catalog as protocol documents and its demos import
  `cramera_bridge.plans.command`. `DemoOption` moved into `cramera_protocol.plan_builder`,
  `Lifeline` into `cramera.lifeline`, and the errors the CRAM side raises into
  `cramera_bridge.exceptions` with their status and message unchanged. Demos generated
  before import the old module and have to be generated again.
- **The question engine moved into cramera-bridge.** Everything of `cramera-questions`
  that evaluates, words or lists queries with krrood, and what it needs (presets,
  matching, the recorded bundle reader, graph views, the workspace class index), is
  `cramera_bridge.questions` now, with `cramera_bridge.questions.live` for live worlds
  and `cramera_bridge.questions.scenes` answering the plugin's routes in protocol
  documents. `cramera-questions` keeps the plugin, its routes and its browser module,
  depends on `cramera-bridge` only through its `bridge` extra, and no longer is a
  dependency of `cramera-bridge`. `cramera-record-answers` is installed by
  `cramera-bridge`. A test of `cramera-bridge` fails on any CRAM import outside it.

### A rewrite into packages
- **One protocol for everything.** `cramera-protocol` defines scene bundles, the
  scenes index, live messages, routes and versions once; the browser reads the same
  names from a generated `protocol.js`. Every recording on the development machine
  (62 scenes) reads without error, including those written before versions existed.
- **A viewer without CRAM.** `cramera` serves the browser application, merges local,
  shared and demo scenes, loads plugins through entry points, and answers only pages
  of the same machine. The page is rebuilt as ES modules on three.js 0.186.1.
- **A demo site that shows what is published.** Every push to `main` rebuilds the
  site with three demo scenes, stamps it with the commit and takes a screenshot that
  the status page and the README show.
- **USD import without the viewer.** `cramera-usd` converts a USD stage into a scene
  bundle (`cramera-import`), gates and publishes a twin's environment by rename
  (`cramera-export`) and audits how a twin separates its robots
  (`cramera-audit-robots`). On the test stages its meshes, URDFs, semantics and
  residuals are byte for byte those of the earlier converter; every JSON file of a
  bundle is written through a protocol document.
- **Live mode.** `cramera-live` runs a CRAM demo and publishes its world; the viewer
  opened with `?live=` follows its joint states, plan and statecharts without a
  recorded scene, and the Live tab stops, saves and replays the recording.
- **Questions and graphs.** The `questions` plugin fills the query slot with the EQL
  card, which answers presets, plain English and entity queries with the question
  read back and a table whose entities light up in 3D, and adds Knowledge, Plan,
  Statechart and Kinematics tabs, which draw the scene's graphs as SVG with pan, zoom,
  fit, fullscreen and node details. The plugin loads without krrood and then answers
  that it is missing.
- **The original look.** The page is laid out as the original AICOR viewer was:
  dark, the AICOR logo and the plugins' pages in the top bar, the scene card with the
  Layers overlay and the playback controls with coloured step, pick and release marks
  on the left, the question card and the graph tabs on the right; a light theme is
  in the View menu. Plugins declare their top-bar entry (`ViewerPlugin.navigation()`),
  and the builder and cable lab pages carry the same bar.
- **The CRAM ontology in the top bar.** The last entry of the top bar, Ontology, opens
  a page of the viewer that embeds cram_owlviz, the browser of the CRAM workspace's
  classes, below the same bar, with a link that opens it in a tab of its own. The page
  is part of the demo site.
- **Recorded answers on the demo site.** `cramera-record-answers` writes a bundle's
  preset answers and graph views into `recorded_answers.json` in a CRAM workspace;
  the static site includes the questions plugin (`cramera-export-site --plugin`) and
  shows them read-only.
- **Plan builder.** `cramera-plan-builder` composes a plan from the robots, objects
  and environments the CRAM workspace offers, turns sentences such as "keep the milk
  upright" into constraint monitors, writes the plan as a CRAM demo and runs it live,
  with its constraints shown on the steps.
- **Every CRAM action in the plan builder.** The builder discovers the action
  dataclasses of coraplex's actions package (26 in the development checkout, 23 of
  them available) and builds each step's form from the action's typed fields:
  objects, annotated entities, the robot's enumeration choices, poses, a pose or a
  surface, numbers, switches and texts, with a derived grasp and optional fields
  under "More options". An action whose required field has no form control yet is
  listed with the reason, and an action module that fails to import is named. Steps
  store the action and its values; plans saved with the earlier six step kinds load
  as the actions those kinds stood for, and a step that no longer fits its action is
  refused, with the step and field named, before its demo is written or run.
- **The plan beside the replay.** A recording names the frames each node of its plan
  ran in (`start` and `end`, from the deepest running action of every frame), and a
  saved stretch of a run keeps them counted from its first frame. When a recording is
  replayed, the plan builder's panel comes to the front and shows its plan as the
  builder's step cards, one list per plan, with each step's arm and target: the step
  at the playhead is marked running and kept in sight while the recording plays or
  is scrubbed, finished steps show the state they ended in, and a click on a step
  jumps to its first frame. Recordings written before name no step frames; their
  steps are shown with the state they ended in.
- **Every robot's plan in one recording.** A run that performs several plans, such as
  one robot carrying totes and then another refilling them, keeps every plan instead
  of only the last: the recording holds one plan tree per plan, in the order they
  began, and each root names the robot that performed it (`robot`, the robot's display
  name). The first plan's nodes keep their identities (`plan_node_<index>`), a later
  plan's nodes are `plan_<number>_node_<index>`, so every frame's running step and
  every live constraint names exactly one node. The replay titles each plan's list
  with its robot, and plans recorded without one by their number.
- **One browser test kit for plugins.** `cramera.testing` runs a plugin's Node tests
  against the viewer's modules as the viewer serves them, with a shared fake DOM.
- **Tools.** `cramera-shot` (screenshots once the page is ready),
  `cramera-export-site` (static site), `cramera-upgrade-bundle` (rewrite a bundle in
  the current format).
- **The laboratory as a plugin.** `cramera-laboratory` ships the bench and the
  expanded AICOR laboratory and their twenty devices with their asset terms, runs
  their MuJoCo contact simulation behind a Laboratory panel (bounded pulling, liquid
  with pouring and spilling, scale, centrifuge with operating manuals, refrigerator,
  drawer, dispensing station, instruments), loads the laboratory into CRAM worlds
  and records a PR2 vessel transfer as a task demo.
- **The wood workshop as a plugin.** `cramera-workshop` ships the AICOR workshop bundle
  with its asset licence and notice, runs its MuJoCo contact world with the ideal screw
  thread behind a Workshop panel, records the PR2 screw insertion as a task demo,
  runs the two-handed assembly through all its stages (not yet recorded: its arms still
  penetrate the furniture while driving and putting the screwdriver down), and checks a recorded assembly before it is published
  (`cramera-workshop check-release`). A screw is grasped the same way however far it
  rolled in its box, and a recording's steps are the stages of its plan. The asset
  rights document is shared with the laboratory as `cramera_protocol.rights`.
- **The cable lab as a plugin.** `cramera-cable-lab` simulates a MuJoCo composite cable
  whose capsules semantic CRAM points follow, with a friction gripper, on a page of its
  own; it owns its session instead of reusing the laboratory's. A cable MuJoCo cannot
  build is refused instead of being kept as points without physics.
- **Plugins release what they own.** `ViewerPlugin.close()` is called once the viewer
  stops serving; `Request.document()` reads a request body as a protocol document.
- The earlier code is kept on the branch `archive/pre-v1`.

## Week 43 · 20 Oct 2026

### Repository
- **This repository is now the home of cramera.** The six-hourly sync from the CRAM
  fork is retired and its workflow removed; development, issues and pull requests
  happen here. Packaging metadata points at this repository.
- **The browser-side tests run here.** The 87 Node.js test files moved from the fork's
  `test/cramera_test/js` to `test/js` with the fixtures they read, and a `Tests`
  workflow runs them on every push and pull request. Five tests that had been failing
  on the fork are fixed.

### Isaac Sim import
- **Convert an Isaac Sim / USD stage into a scene bundle** with `cramera-import` (the
  `usd` extra): geometry, physics joints, OmniPBR, OmniSurface, OmniGlass and
  UsdPreviewSurface materials, lights and `sdt`/`ont` semantics, written into a shared
  `CRAMERA_SCENES` folder. See [Import an Isaac Sim / USD scene](README.md#import-an-isaac-sim--usd-scene).
- **Only the environment comes over**: robots the stage marks (Isaac Sim's
  `IsaacRobotAPI`, or `sdt:entityType` `Robot`) are left out together with the joints
  to them and listed in `conversion_report.json`. `--exclude` leaves out any other
  subtree, `--keep-robots` keeps the marked robots, and `--robot` keeps the one a
  recording replays. A `--prim` inside a left-out robot is refused, and the report and
  the terminal summary name the bodies that hung from a robot (`detached`) and the
  articulations kept in the environment (`articulations`), where a robot part or a
  robot the stage does not mark shows up.
- **Recorded motion plays back**: the stage's time samples or a recorded body trace
  (`--trace`) become joint values, a robot model (`--robot`), moving objects and step
  segments (`--record`), checked against the recording in `residuals.csv`.
- **An imported scene loads as a CRAM world** whose prims answer EQL questions:
  `python -m cramera.examples.usd_scene_world --scene <name> --live`.

### 3D scene
- **A bundle can bring its own lighting and view**: the stage's lights become the
  environment map and key light, the shadows fit the scene's bounds, the plank floor
  can be turned off, and the camera takes a field of view and a far plane.
- Scenes with ambient occlusion on render brighter: the occlusion pass now encodes its
  output for the screen.

## Week 36 · 31 Aug – 4 Sep 2026

### Plan Builder
- **A page that composes a plan and generates a runnable demo.** Drag steps into a
  plan, choose an environment, place the robot and the transport targets in the
  embedded live 3D scene, then generate a `RobotDemonstration` subclass in the
  output style you pick. The demo's run log is shown so a failure can be traced.
  (`205d79402`, `c47b507e1`, `caaa4bb67`, `89a9637a2`, `6261fb2c5`, `e86a79a04`, `3563737a0`)
- **Navigate steps show and capture the robot pose** as a ring and heading arrow on
  the floor. (`487bb1051`, `932644a4f`)
- **Transport steps know where they start and where they drop off**; a drop-off can
  be a semantic surface or container instead of coordinates.
  (`a18b55ebd`, `d522049af`, `6c86d9406`, `1226f653c`, `1890c9ad6`)
- **Objects are placed with sliders, numbers and "Drop to surface"**; new objects
  stage above the robot under a bobbing arrow. (`e3330c9bd`, `316bc29b1`, `92d74ec26`, `38ba4511c`, `520ee76cd`)
- **Every semantic_digital_twin robot and an all-STL industrial object set**; Garmi
  joins the list. (`40edf54b8`, `1827604c3`, `f55097eb4`, `52a548e19`, `18cd18b93`)
- Constraints in plain language on every plan step. (`d53f0aac0`)
- A big 3D scene with the controls in one dropdown; resizable columns; a reload
  button for the scene; visible feedback on Generate, Save and Download.
  (`2af538b25`, `805d8cbb9`, `2186d4121`, `3623aab48`, `ae75551a8`)

### Plan view
- **Plan steps read as a tree of phases with live status**; the graph view is gone,
  the step list is the Plan tab. (`e32c9ddf4`, `874eb01fc`, `0e8da5a51`, `52b2753b5`, `1ae600f4d`)
- **Constraints you type compile to giskardpy nodes against the live world**, from a
  palette inside the Steps view; the bridge accepts them while the plan runs.
  (`c67f5ce5c`, `1ba0b54a4`, `b0918c4eb`)
- The Plan tab attaches to the running bridge and shows motion-statechart rings.
  (`4dd70f65e`, `3e2d609b8`, `359422308`)
- More constraint goal types and a richer rule-based translation to English.
  (`896ccf0c6`, `8c74f6aea`)

### Questions
- **Ask the EQL console a question in English**: completion, matching to a preset,
  read-back and speech. (`b725dfa46`, `8d666e350`)
- **An answer says where it comes from and points at what it names**; a timestamped
  answer can replay its moment. (`62183bd31`, `241f6939e`, `bf25a199a`, `3714d66cc`)
- A query source can claim the bodies it describes under a prefix. (`8b7945244`)

### Recordings
- **Recordings carry the motion statecharts** (`statecharts.json`). (`c1d8fa054`)
- **Recordings carry what the detectors saw**: pick and place events from segmind,
  answerable from the saved scene without the detectors' package.
  (`932f187a6`, `08ec63b2e`, `1ba75a6b2`, `639acac4c`, `e97c698d8`, `479dd4820`)
- **A recording is saved by what it is** — robot, environment, task — and keeps the
  objects a run carried. (`47b156e63`, `3a2c114d4`, `120891514`)

### 3D scene
- The rectangle on the floor of every scene is gone: the SSAO pass no longer draws
  the scene background into its depth and normal buffers. (`993394afc`)
- A lone panel takes the whole window; overlays and question groups fold away.
  (`2eb61a848`, `c861b8299`, `10d050718`, `240f2f5ca`)
- The Teleoperation tab is now called Sandbox; the blue place target stays out of the
  embedded and live views. (`e63e0f917`, `98b1936a6`, `a141673a2`)

### Platform
- The browser no longer caches static assets; what the branch serves is tested. (`12deaee25`)
- A fresh checkout runs the generated demo without editing a venv path. (`f0741687a`)

## Week 34 · 17 – 18 Aug 2026

- Collada models load with their up axis normalized — contributed by Tigul (PR #38).
  (`d6cef3972`)

## Week 33 · 10 – 15 Aug 2026

### Recordings
- Replay a recorded run, with TF frames and keypoints; trim it before saving.
  (`2db5dd0de`, `1bd3a6fea`, `5438761d5`)
- Onboard demos whose worlds come from Gazebo/SDF or MJCF. (`d6d0ee546`, `cc6559743`)

### 3D scene
- ROS debug markers in the scene, with RViz-style settings. (`32fe7d1ff`, `3849c589f`)
- A View menu chooses which panels show and where; panels are draggable and the
  arrangement persists. (`2207d8c51`, `949829ebc`, `1841d1810`, `463991e6f`, `3a20488ea`)
- Loose objects spawned as primitive boxes are recorded and rendered; mesh rendering
  of bundled environments and multi-material robots is fixed. (`2c546d025`, `72bacdd6d`)

### Models
- The Models tab: the probabilistic-model workbench in the browser — Query,
  Posterior and Mode side by side, sliders for numeric constraints.
  (`de6d10091`, `c3b2c3d05`, `95ba8ef7f`, `aa756483f`, `d83816ac1`)

### Live view
- The live view is rebuilt on `WorldVisualization`; no more monkey patches.
  (`33ca53d4a`, `47700539a`, `6d6f543dd`, `f68daa892`)
- Worlds that are not fully XML can be viewed live. (`021c08f68`)

### Platform
- The cramera server opens the viewer; demos only connect to it. (`c1c07a398`)
- Several scenes per installation, selectable across backend and panels. (`4d2d025bb`, `0891832eb`)
- Graph panel: colors and groups, a plan legend, a four-level architecture scan.
  (`0f07103aa`, `1fa024a56`, `41a12b9f7`, `8696eac41`)
- Variable hints in the EQL query box; panels report their errors. (`7264cd6bc`, `ccdeea54a`)
- The project is named cramera. (`2851475ac`)
