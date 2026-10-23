# Architecture

cramera shows what a CRAM robot does, recorded or live, in the browser, and lets
people ask the scene questions. Version 1 is a rewrite of the earlier single package
into independent packages that talk through one versioned protocol. The pre-v1 code
is kept on the branch `archive/pre-v1`.

## Model: publish, show, extend

Like ROS and RViz: CRAM publishes, cramera shows, and a versioned protocol sits in
between. The viewer never imports CRAM. Everything that needs CRAM, USD or a physics
engine lives in a package of its own and reaches the viewer through the protocol or
through a plugin.

```
                    cramera-protocol            (formats, routes, versions; stdlib only)
                   /        |         \
            cramera     cramera-usd    cramera-cram ──── CRAM workspace
           (viewer)    (USD import)   (live publisher, recording, questions, demos)
               |
     plugins: cramera-offline, cramera-plan-builder, ...
```

| Package | Import name | Depends on | Responsibility |
| --- | --- | --- | --- |
| `cramera-protocol` | `cramera_protocol` | standard library, `typing_extensions` | Scene bundle files, scene index, live messages, HTTP routes, capabilities, protocol version. The single definition both Python and the browser read. |
| `cramera` | `cramera` | `cramera-protocol` | The viewer: HTTP server, scene catalog, plugin loading, the browser application, screenshots. Installs and runs without CRAM. |
| `cramera-usd` | `cramera_usd` | `cramera-protocol`, `usd-core`, `numpy` | Converting a USD stage into a scene bundle, the export gate, the robot separation audit. |
| `cramera-cram` | `cramera_cram` | `cramera`, CRAM packages | The only package that imports the CRAM workspace: live publishing from a running plan, recording into bundles, demo onboarding, task demos, the question engine (`cramera_cram.questions`: queries in the entity query language about a live world or a recorded scene, presets, plain-language matching, graph views, `cramera-record-answers`), and the plan builder's CRAM side (`cramera_cram.plans`: the catalog of robots, objects, surfaces and native actions, and the demo a generated plan runs). |
| `cramera-questions` | `cramera_questions` | `cramera`; `cramera-cram` optionally | The questions plugin of the viewer: its browser module and its routes over recorded scenes, which hand each request to `cramera_cram.questions.scenes` and answer with the protocol documents it returns. Without `cramera-cram` and krrood the routes answer what is missing and the browser module shows the bundles' recorded answers. |
| `cramera-offline` | `cramera_offline` | `cramera` | The storyboard and bundle check routes, `cramera-check-bundle`, and `cramera-offline`, which prepares, checks, serves (optionally from a network namespace without routes) and exports a presentation of recorded bundles. |
| `cramera-plan-builder` | `cramera_plan_builder` | `cramera`; `cramera-cram` optionally | The Plan View panel and the builder page: the panel shows a replayed recording's plan as step cards with every recorded parameter and constraint; the page composes a robot plan by drag and drop from the native actions `cramera-cram` discovers in the CRAM workspace, each step's form built from its action's fields, places its robots, objects and targets over an environment bundle, compiles constraints written in plain language into live monitors, and generates, writes and runs the plan's demo, which `cramera-cram` performs, as an owned child process. It imports nothing of the CRAM workspace: the catalog arrives as protocol documents and the demo carries its plan as a `DemoDocument`. Without the CRAM workspace its catalog names the missing modules. |
| The other plugins | ... | `cramera`, and what the plugin itself needs | One self-contained feature each: its Python routes, its browser module, its assets. |

### CRAM boundary

`cramera-cram` is the only package that imports the CRAM workspace (`coraplex`,
`semantic_digital_twin`, `giskardpy`, `krrood`, `segmind`, ...), so a CRAM change only
needs that package to follow; `AGENTS.md` states the rule and
`packages/cram/test/test_cram_boundary.py` checks it. Other packages reach CRAM through
`cramera_cram` functions that take and return protocol documents, or through a child
process: the plan builder reads its catalog from `cramera_cram.plans.workspace` as
`RobotModel`, `ObjectModel` and `ActionCatalog` documents and writes demos that hand
their `DemoDocument` to `cramera_cram.plans.command`, started with the `DemoOption`s of
the protocol. Errors raised on the CRAM side are `ViewerError`s of
`cramera_cram.exceptions`, so they reach the HTTP routes with their own status and
message. The questions plugin works the same way: its routes parse the request and hand
the scene name and the protocol request to `cramera_cram.questions.scenes`, which
evaluates the query with krrood and returns `PresetCatalog`, `Vocabulary`, `Members`,
`GraphView`, `QueryAnswer` or `QuestionMatch` documents.

## Protocol

- Every fixed name that crosses a boundary is a `StrEnum` member in
  `cramera_protocol`: file names, JSON keys, routes, capabilities, environment
  variables.
- Every document is a dataclass that reads itself with `from_json` and writes itself
  with `to_json`. The field-to-key mapping is declared once per field.
- `formatVersion` is written into `scene.json` and `index.json`, and
  `protocolVersion` into the live `/info` answer. A document without a version is
  version 0 and still readable. An unknown major version is refused with
  `UnsupportedProtocolVersion`.
- The browser does not keep a second copy of these names. The viewer generates the
  ES module `protocol.js` from the Python enums, at request time when serving and at
  build time for the static demo site.

The protocol package does not use krrood's JSON serializer, which CRAM's own rules
prefer for CRAM classes. The protocol is a wire format shared with the browser and
must install without CRAM, so it follows the rule for data whose shape is fixed
outside the class: dataclasses with a `from_json` classmethod.

## Viewer

- A `ViewerServer` owns one `ThreadingHTTPServer` and stops it when its context
  ends. Routes are `Route` objects collected by a `Router`; plugins contribute routes
  of their own.
- Every request passes an `OriginPolicy`. The server binds to `127.0.0.1` by default
  and answers only requests whose origin is the local machine.
- A `SceneCatalog` merges several `SceneDirectory` instances: the shared folder, the
  local recordings and the demo scenes, each with the scenes directories nested in
  it, so a scenes repository cloned into one of them is found without being named. Every file request is confined to its bundle
  directory, including symbolic links and `..`.
- Plugins are found through the entry-point group `cramera.plugins`. Each one is a
  `ViewerPlugin` with a name, routes, a directory of browser modules, the
  capabilities it adds and, optionally, an entry in the top bar's navigation.

## Browser application

- Native ES modules, loaded through an import map. No build step and no network
  access at run time: three.js and the URDF loader are vendored with their licences.
- A small `Application` coordinates independent parts. Each part owns its DOM, its
  listeners and its cleanup: top bar, scene renderer, Layers overlay, timeline, scene
  picker, query slot, tabbed panels.
- The page keeps the original AICOR viewer's look: the AICOR logo and the plugins'
  pages in the top bar, the scene card with the 3D view and the playback controls on
  the left, the query slot and the tabs on the right; dark by default, light on
  request, both from one set of CSS variables.
- Parts talk through one typed `EventBus`. Event names come from `protocol.js`.
- Plugin modules are imported from the plugin list the server reports and receive the
  same registry the built-in parts use.

## Demo site

`https://aicor-solutions.github.io/cramera/` is rebuilt on every push to `main`. It serves the
viewer with the demo scenes under `demo/standard_scenes` and the questions plugin's browser
module, a status page with the version, commit and build time, a screenshot of the
viewer taken in that build, and the ontology page, which embeds cram_owlviz
(`https://sorynaryon.github.io/cram_owlviz/`). The site has no Python and no krrood, so the
questions plugin shows the answers and graph views each demo bundle carries in
`recorded_answers.json`, written by `cramera-record-answers` in a CRAM workspace.

## Rules

The code follows CRAM's `AGENTS.md` and the Code of Conduct in CRAM's `README.md`:
black and docformatter, 85 % coverage for new code, a failing test before every bug
fix, dataclasses, `StrEnum` for fixed strings, reStructuredText docstrings with one
docstring per field, `# %%` sections, absolute imports, no global state, no
`try`/`except` for control flow, no `getattr`, no abbreviations.
