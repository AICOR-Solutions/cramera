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
     plugins: cramera-laboratory, cramera-workshop, cramera-cable-lab, cramera-builders
```

| Package | Import name | Depends on | Responsibility |
| --- | --- | --- | --- |
| `cramera-protocol` | `cramera_protocol` | standard library, `typing_extensions` | Scene bundle files, scene index, live messages, HTTP routes, capabilities, protocol version. The single definition both Python and the browser read. |
| `cramera` | `cramera` | `cramera-protocol` | The viewer: HTTP server, scene catalog, plugin loading, the browser application, screenshots. Installs and runs without CRAM. |
| `cramera-usd` | `cramera_usd` | `cramera-protocol`, `usd-core`, `numpy` | Converting a USD stage into a scene bundle, the export gate, the robot separation audit. |
| `cramera-cram` | `cramera_cram` | `cramera`, CRAM packages | Live publishing from a running plan, recording into bundles, questions in the entity query language, demo onboarding, task demos. |
| `cramera-laboratory` and the other plugins | `cramera_laboratory`, ... | `cramera`, and what the plugin itself needs | One self-contained feature each: its Python routes, its browser module, its assets. |

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
  local recordings and the demo scenes. Every file request is confined to its bundle
  directory, including symbolic links and `..`.
- Plugins are found through the entry-point group `cramera.plugins`. Each one is a
  `ViewerPlugin` with a name, routes, a directory of browser modules and the
  capabilities it adds.

## Browser application

- Native ES modules, loaded through an import map. No build step and no network
  access at run time: three.js and the URDF loader are vendored with their licences.
- A small `Application` coordinates independent parts. Each part owns its DOM, its
  listeners and its cleanup: scene renderer, timeline, scene picker, question panel,
  graph panel, layout.
- Parts talk through one typed `EventBus`. Event names come from `protocol.js`.
- Plugin modules are imported from the plugin list the server reports and receive the
  same registry the built-in parts use.

## Demo site

`https://sunava.github.io/cramera/` is rebuilt on every push to `main`. It serves the
viewer with the demo scenes under `demo/scenes`, a status page with the version,
commit and build time, and a screenshot of the viewer taken in that build.

## Rules

The code follows CRAM's `AGENTS.md` and the Code of Conduct in CRAM's `README.md`:
black and docformatter, 85 % coverage for new code, a failing test before every bug
fix, dataclasses, `StrEnum` for fixed strings, reStructuredText docstrings with one
docstring per field, `# %%` sections, absolute imports, no global state, no
`try`/`except` for control flow, no `getattr`, no abbreviations.
