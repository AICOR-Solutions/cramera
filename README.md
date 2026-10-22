# cramera

**Watch a CRAM robot run, recorded or live, in the browser, and ask the scene what happened.**

**[Open the demo](https://sunava.github.io/cramera/)** · [What is published right now](https://sunava.github.io/cramera/status.html) · [Architecture](docs/architecture.md) · [Changelog](CHANGELOG.md) · [Issues](https://github.com/sunava/cramera/issues)

[![The viewer as the latest build shows it](https://sunava.github.io/cramera/status/viewer.png)](https://sunava.github.io/cramera/)

The picture above is taken by every build of `main`: it always shows the newest
published viewer. The [status page](https://sunava.github.io/cramera/status.html)
names the version, the commit and the build time.

cramera is the viewer of the [CRAM](https://github.com/cram2/cognitive_robot_abstract_machine)
cognitive architecture. CRAM publishes what a robot does; cramera shows it:

- **Recorded.** A run becomes a self-contained scene bundle (URDFs, meshes and the
  recorded trajectory) that replays in any browser, without ROS, a simulator or
  Python. The demo site is exactly that: static files.
- **Live.** Attached to a running plan, the viewer follows the executing world.
- **Asked.** Questions in plain English or in CRAM's entity query language are
  answered over the recorded or running world.

## Version 1.0

Version 1.0 is a rewrite into independent packages that talk through one
versioned protocol, the way ROS and RViz do. The earlier single package is kept on
the branch [`archive/pre-v1`](https://github.com/sunava/cramera/tree/archive/pre-v1).

| Package | What it does | State |
| --- | --- | --- |
| [`cramera-protocol`](packages/protocol) | The formats and messages: scene bundles, the scenes index, live messages, routes, versions. Python and the browser read the same definitions. | done |
| [`cramera`](packages/viewer) | The viewer: HTTP server, scene catalog, plugins, the browser application, screenshots, the static site export. Runs without CRAM. | done |
| `cramera-usd` | Converting an Isaac Sim or USD stage into a scene bundle, with the export gate and the robot separation audit. | in progress |
| `cramera-cram` | Live publishing from a running plan, recording, onboarding demos, task demos. | in progress |
| `cramera-questions` | Questions in the entity query language over worlds and recordings. | in progress |
| laboratory, workshop, cable lab, scene and plan builder | One plugin package each. | planned |

Recordings made with earlier versions open unchanged: a document without a
`formatVersion` is read as version 0.

## Use the viewer

```bash
pip install ./packages/protocol ./packages/viewer
cramera                      # serves http://127.0.0.1:8711 and opens it
```

The viewer shows the bundles of three scenes directories; a bundle in an earlier
one hides a bundle of the same name in a later one:

| Directory | Set by |
| --- | --- |
| local recordings | `$CRAMERA_DATA/scenes`, by default `~/.cramera/scenes` |
| shared scenes | `$CRAMERA_SCENES`, and every `--scenes DIR` |
| demo scenes | `--demo-scenes DIR`, for example `demo/scenes` of this repository |

```bash
cramera --demo-scenes demo/scenes --port 8711 --no-browser
```

The page address names the shown bundle, `?scene=<name>`, so a view can be shared.
The server listens on `127.0.0.1` and answers only pages served from the same
machine.

### Commands

| Command | What it does |
| --- | --- |
| `cramera` | Serve the viewer. |
| `cramera-shot URL OUT.png` | Take a screenshot in headless Chrome (`--browser chrome`, needs `chromedriver`) or Firefox (`--browser firefox`, needs `geckodriver`) once the page reports its scene as shown; exits 1 when it fails. |
| `cramera-export-site OUT --scenes DIR` | Write the viewer and the bundles of a directory as a static site, for any web server. |
| `cramera-upgrade-bundle SRC DST` | Copy a bundle and rewrite its documents in the current format, optionally with new labels for the scene picker. |

## Develop

```bash
python3 -m venv ~/.virtualenvs/cramera-dev
~/.virtualenvs/cramera-dev/bin/pip install -e ./packages/protocol -e ./packages/viewer -r requirements-development.txt
cd packages/viewer && ~/.virtualenvs/cramera-dev/bin/python -m pytest -q --cov=cramera test
```

- Each package is tested on its own; CI requires 85 % coverage. The browser tests
  run in Node.js through `test_browser_modules.py`.
- Format with `python scripts/format_python.py` (black, then docformatter where
  black keeps its output). CI fails when it would change anything.
- `scripts/vendor_browser_libraries.py` updates three.js and urdf-loader, checked
  against the npm registry's integrity hashes.
- The code follows CRAM's
  [AGENTS.md](https://github.com/cram2/cognitive_robot_abstract_machine/blob/main/AGENTS.md)
  and the Code of Conduct in CRAM's README: dataclasses, one `StrEnum` for every
  fixed name, reStructuredText docstrings with one docstring per field, no
  `getattr`, no exception handling for control flow, a failing test before every
  fix.

The demo site is rebuilt by [`pages.yml`](.github/workflows/pages.yml) on every
push to `main`. A build whose viewer does not show its scene fails, so the site
keeps the last working build.

## Licence

cramera was developed by [Vanessa Hassouna](https://github.com/sunava) for AICOR
Solutions. Its licence is being changed to BSD-3-Clause (branch `license-bsd3`);
until that change lands, the code is distributed under GPL-3.0 as before. The
bundled three.js (MIT) and urdf-loader (Apache-2.0) keep their own licences, see
`packages/viewer/src/cramera/web/vendor`.
