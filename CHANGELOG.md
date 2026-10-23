# Changelog

What landed in cramera, by week and area. Entries are features, not commits; hashes
in entries up to week 43 point into the `cramera-port` branch of the CRAM fork, from
which this repository was mirrored until 22 Oct 2026.


## 1.0.0 · in progress since 22 Oct 2026

### Removed
- **The models panel, the laboratory, the workshop and the cable lab.**
  `cramera-models`, `cramera-laboratory`, `cramera-workshop` and `cramera-cable-lab`
  are gone with their panels and pages, their protocol modules
  `cramera_protocol.models`, `cramera_protocol.laboratory`,
  `cramera_protocol.workshop` and `cramera_protocol.cable_lab`, `PluginName.MODELS`
  and `PluginName.WORKSHOP`, and the vendored Plotly. The navigation group
  `laboratory` stays for plugins outside this repository; `cramera_protocol.rights`
  stays for the scene builder.

### Added
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
