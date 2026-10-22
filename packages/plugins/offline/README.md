# cramera-offline

A viewer plugin and a command for presenting recorded CRAM runs without a robot:

- the Tour side panel steps through a storyboard of chapters, each showing a bundle
  from a frame, opening a side panel and playing the recording, and shows whether the
  shown bundle holds every file it references;
- `cramera-check-bundle <bundle>...` follows every reference of a bundle, from
  `scene.json` through URDF models, meshes, material libraries and glTF buffers to
  textures, and reports each that is missing or leaves the bundle.
