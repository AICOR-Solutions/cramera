# Writing a plugin

A plugin is a Python package that extends the viewer. It can add HTTP routes, a
browser module with side panels or pages, and capabilities. The viewer finds
installed plugins through the entry-point group `cramera.plugins`; nothing in the
viewer names a plugin.

This also means a plugin is only there once its package is installed into the same
environment as `cramera`: `pip install ./packages/viewer` brings no page but the
scene page. The pages of this repository (Models, Plan Builder, Scene Builder, Cable
Lab, Laboratory, Workshop, the Tour, the questions column) are installed with
`pip install ./packages/questions ./packages/plugins/*`; optional extras such as
`[physics]`, `[circuits]` and `[cram]` add what a plugin needs beyond the viewer. The
README's section *Install the pages and panels* lists them. The viewer's `/api/info`
answer names the plugins it has loaded, which is the first thing to check when a
page is missing from the top bar.

## Python side

```toml
# pyproject.toml of the plugin package
[project.entry-points."cramera.plugins"]
laboratory = "cramera_laboratory.plugin:LaboratoryPlugin"
```

The entry point names a callable that returns a `cramera.plugins.ViewerPlugin`:

| Method | Returns |
| --- | --- |
| `name()` | The plugin's name: lowercase letters, digits and `-`. It is also its route segment. |
| `version()` | The plugin's version. |
| `capabilities()` | The `cramera_protocol.live.Capability` members it adds. |
| `routes(context)` | `PluginRoute(method, path, handler)` objects, served at `/api/plugins/<name>/<path>`, and `PluginPrefixRoute(method, prefix, handler)` objects, which answer every path below `/api/plugins/<name>/<prefix>` and hand the rest of the path to the handler. `context.catalog` is the viewer's `SceneCatalog`, `context.locations` its `DataLocations`. |
| `web_directory()` | The directory of the plugin's browser files, served at `/plugins/<name>/`. |
| `module()` | The plugin's browser module, relative to `web_directory()`. |
| `navigation()` | The plugin's entry in the top bar, or None (the default) for a plugin that only adds to the scene page: `PageEntry(title, group, page)` links a page of the plugin's own (`page` relative to `web_directory()`), `PanelEntry(title, group)` shows the plugin's panel, whose identity must be the plugin's name, on the scene page. |
| `close()` | Releases what the plugin owns, such as a simulation its routes started; called once the viewer has stopped serving. Does nothing by default. |

Handlers take a `cramera.http.messages.Request` and return a `Response`
(`Response.of_json`, `Response.of_file`, ...); `request.document(Document)` reads a
JSON body as a protocol document and refuses a body that is no JSON with 400. Raise a
`cramera.exceptions.ViewerError` subclass for a request that cannot be served; its
`status()` becomes the answer's HTTP status. Every request has passed the viewer's origin policy before it reaches a
plugin.

### Navigation

The top bar of every page lists the scene page and one link per installed plugin
with a navigation entry; nothing in the viewer names a plugin, so an uninstalled
plugin simply has no link. The viewer's information reports each entry as the
plugin's `navigation`: a `title`, a `group` and, for a page, its `page` route. The
`NavigationGroup` orders the links: `analysis` (such as Models), `builder` (Plan
Builder, Scene Builder), `laboratory` (Laboratory, Workshop); within a
group they are ordered by title.

```python
from cramera.plugins import PageEntry, PanelEntry
from cramera_protocol.viewer import NavigationGroup

def navigation(self):
    return PageEntry("Plan Builder", NavigationGroup.BUILDER, "builder.html")
```

A page of the plugin's own shows the same top bar by marking an element and loading
the viewer's header module:

```html
<script type="module" src="../../app/site-header-main.js"></script>
...
<header class="topbar" data-site-header data-page="plan-builder"></header>
```

`data-page` is the plugin's name, so its link is marked as the current page.

## Browser side

The viewer imports each plugin's module and calls its `register` function with a
`PluginContext`:

```js
// web/index.js of the plugin, served at /plugins/<name>/index.js
import { ViewerEvent, SelectionKey } from '../../protocol.js';
import { SidePanel } from '../../panels/panel-host.js';

export function register(context) {
  const element = document.createElement('section');
  context.panels.add(new SidePanel('laboratory', 'Laboratory', element));
  context.bus.subscribe(ViewerEvent.ENTITY_SELECTED, (selection) => {
    element.textContent = selection ? selection[SelectionKey.NAME] : '';
  });
}
```

| Context field | What it is |
| --- | --- |
| `bus` | The application's `EventBus`; event names are the members of `ViewerEvent`. Publish `SCENE_REQUESTED` (a bundle name), `FRAME_REQUESTED` (a frame number) or `PLAYBACK_REQUESTED` (whether to play) to steer the application. |
| `panels` | The `PanelHost` of the right column; `add(new SidePanel(identifier, title, element))` adds a tab. Plugins without a navigation entry register first, so their tabs come first. |
| `query` | The `QuerySlot` above the tabs; one plugin may `fill(new SlotPanel(identifier, title, element, aside))` it, which shows it as a card. Empty, it is hidden. |
| `info` | The viewer's information; `info[ViewerInfoKey.SERVING]` is `Serving.STATIC` on a static site, where plugin routes do not exist. |
| `api` | The `ViewerApi`; `api.url('/api/plugins/<name>/<route>')` gives a route's URL below the page's base. |
| `view` | The `SceneView`: `scene`, `content`, `camera`, `renderer`, `requestRender()`. |

Rules for browser modules:

- Import the viewer's modules and `protocol.js` by relative paths
  (`../../protocol.js`), never by absolute ones, so the plugin also works when the
  viewer is served below a path, as on the demo site.
- `three` and `three/addons/...` resolve through the page's import map.
- Use the protocol's names for every key and event; add new names to
  `cramera-protocol` rather than spelling them in the plugin.
- Use the CSS variables of `styles/viewer.css` (`--surface`, `--surface-raised`,
  `--text`, `--text-muted`, `--border`, `--accent`, `--control`, `--radius`, `--font`,
  ...), so the plugin follows the dark theme, which is the default, and the light
  theme a person may choose in the View menu (`:root[data-theme="light"]`).
- Own your elements and listeners and remove them when a scene is replaced, by
  subscribing to `ViewerEvent.SCENE_LOADING`.
- Insert user and scene text as `textContent`, never as HTML.

A plugin may also ship pages of its own in its web directory, for example a builder
that needs the whole window; declare a `PageEntry` so the top bar links to it.

On a static site (`cramera-export-site --plugin NAME`) the plugin's browser files are
copied, but its routes do not exist. A plugin that wants to show something there
reads files instead, as the questions plugin reads each bundle's
`recorded_answers.json`.

## Testing the browser side

`cramera.testing` runs a plugin's Node tests against the viewer's modules, resolved
as the viewer serves them:

```python
# test/test_browser_modules.py of the plugin
from pathlib import Path
from cramera.testing.browser_tests import PluginBrowserTests

def test_the_browser_modules_pass_their_tests():
    result = PluginBrowserTests(
        plugin_web=Path(__file__).parent.parent / "src" / "cramera_laboratory" / "web",
        tests=Path(__file__).parent / "js",
    ).run()
    assert result.returncode == 0, result.stdout + result.stderr
```

Tests import the viewer's modules as `cramera-viewer/...` and the shared fake DOM as
`cramera-testing/fake-document.mjs`, and the plugin's own modules by their path. Put
a `package.json` with `"type": "module"` in the plugin's web directory, so Node reads
its files as ES modules.
