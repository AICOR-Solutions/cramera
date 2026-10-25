# Working on cramera

See `README.md` for what the packages do and `docs/architecture.md` for how they fit
together.

## CRAM is reached through cramera-bridge only

`packages/bridge` (`cramera_bridge`) is the only package that imports the CRAM workspace:
`coraplex`, `semantic_digital_twin`, `giskardpy`, `krrood`, `segmind`, `robokudo`,
`physics_simulators`, `probabilistic_model` and `random_events`. When CRAM changes,
`cramera-bridge` is the only package that has to change with it.

Every other package, the plugins included, reaches CRAM through `cramera-bridge`'s API or
through the protocol (`cramera_protocol`):

- Do not add an `import` or `from ... import` of a CRAM package outside `packages/bridge`,
  in source or in tests, and not behind `TYPE_CHECKING` either.
- What a package outside `packages/bridge` needs from CRAM, such as a catalog of native
  actions, a world built from a plan or a plan run, is offered by `cramera-bridge` as data
  in the protocol's documents, or as a function of `cramera_bridge` that takes and returns
  such documents. Add it there; do not hand native CRAM objects across the boundary.
- A name CRAM defines, such as a status, an arm or an action field, crosses the boundary
  as the protocol's own name, translated inside `cramera-bridge` (as `PlanNodeStatus`
  translates coraplex's life cycle values), so a CRAM rename stays inside the package.
- Classes whose names a saved file or a check relies on (actions, robots, plan node
  kinds) are pinned in `cramera_bridge/names.py` to snake_case identifiers of the
  protocol's own. When CRAM renames or moves such a class, update its path there and
  keep its identifier. When CRAM adds one, pin it; `test/live/test_names.py` fails
  until every action and robot the workspace offers is pinned. Labels shown to people
  and EQL queries follow CRAM's names by design.

Check a change with:

```bash
grep -rnE --exclude-dir=build "^\s*(from|import) (coraplex|semantic_digital_twin|giskardpy|krrood|segmind|robokudo|physics_simulators|probabilistic_model|random_events)\b" packages --include=*.py | grep -v "^packages/bridge/"
```

which lists nothing. `packages/bridge/test/test_cram_boundary.py` runs the same check in
the test suite and fails on any such import.
