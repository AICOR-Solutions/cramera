# cramera-scene-builder

A plugin of the cramera viewer that arranges independent copies of existing models
into scene drafts: furniture, objects, robot spawn poses and scanned rooms as point
cloud references. Editing a draft never changes an original URDF, mesh or recording,
and nothing is simulated.

Install it next to the viewer; the viewer finds it through the `cramera.plugins`
entry point and shows a **Scene builder** panel that opens the builder page.

```bash
pip install -e packages/plugins/scene-builder
cramera
```

- The resource library holds every model, mesh and point cloud of the viewer's
  scenes directories, and of the directories `CRAMERA_SCENE_BUILDER_LIBRARY` names
  (separated like `PATH`, each offered under its directory name).
- The library also offers primitive shapes under **Shapes**: a box, a cylinder and a
  sphere, one metre across, standing on their base, as stand-ins for objects still to
  be designed. Their scale fields read as their size in metres.
- Every placed instance has a name and an optional description: what it is, how it
  works, anything to remember when designing it later. Both are saved with the draft.
- Drafts are saved under `CRAMERA_DATA/scene-builder/drafts`, uploaded point clouds
  under `CRAMERA_DATA/scene-builder/point-clouds`.
- Point clouds are vertex-only PLY files or ASCII and uncompressed binary PCD files of
  up to 64 MiB and two million points; the builder shows a sample of at most 250,000.
