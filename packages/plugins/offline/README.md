# cramera-offline

A viewer plugin and two commands for presenting recorded CRAM runs without a robot or
a network:

- the plugin serves the storyboard of the scenes directories and the completeness
  check of a bundle, whether it holds every file it references;
- `cramera-check-bundle <bundle>...` follows every reference of a bundle, from
  `scene.json` through URDF models, meshes, material libraries and glTF buffers to
  textures, and reports each that is missing or leaves the bundle;
- `cramera-offline prepare|check|serve|export-site <presentation>` copies the bundles a
  storyboard shows into a new presentation directory, checks it, serves it with the
  viewer on this machine (with `--isolated`, from a process in a network namespace
  without routes) or exports it as a static site.
