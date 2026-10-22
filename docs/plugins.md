# Writing a plugin

A plugin is a Python package that extends the viewer. It can add HTTP routes, a
browser module with side panels or pages, and capabilities. The viewer finds
installed plugins through the entry-point group `cramera.plugins`; nothing in the
viewer names a plugin.

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
| `close()` | Releases what the plugin owns, such as a simulation its routes started; called once the viewer has stopped serving. Does nothing by default. |

Handlers take a `cramera.http.messages.Request` and return a `Response`
(`Response.of_json`, `Response.of_file`, ...). Raise a `cramera.exceptions.ViewerError`
subclass for a request that cannot be served; its `status()` becomes the answer's
HTTP status. Every request has passed the viewer's origin policy before it reaches a
plugin.

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
| `panels` | The `PanelHost`; `add(new SidePanel(identifier, title, element))` adds a tab. |
| `api` | The `ViewerApi`; `api.url('/api/plugins/<name>/<route>')` gives a route's URL below the page's base. |
| `view` | The `SceneView`: `scene`, `content`, `camera`, `renderer`, `requestRender()`. |

Rules for browser modules:

- Import the viewer's modules and `protocol.js` by relative paths
  (`../../protocol.js`), never by absolute ones, so the plugin also works when the
  viewer is served below a path, as on the demo site.
- `three` and `three/addons/...` resolve through the page's import map.
- Use the protocol's names for every key and event; add new names to
  `cramera-protocol` rather than spelling them in the plugin.
- Use the CSS variables of `styles/viewer.css` (`--surface`, `--text`, `--accent`,
  ...), so the plugin follows the light and dark themes.
- Own your elements and listeners and remove them when a scene is replaced, by
  subscribing to `ViewerEvent.SCENE_LOADING`.
- Insert user and scene text as `textContent`, never as HTML.

A plugin may also ship pages of its own in its web directory, for example a builder
that needs the whole window; link to them from a panel with a relative URL.

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
