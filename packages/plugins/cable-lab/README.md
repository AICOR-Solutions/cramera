# cramera-cable-lab

A plugin of the cramera viewer that simulates a composite cable in MuJoCo and lets a
force-limited parallel gripper pinch, lift and drop it. The **Cable lab** panel opens the
lab page, which builds a cable from its settings, sends gripper commands and shows the
measured capsules, pads, contacts and forces in 3D.

- The cable is MuJoCo's native `composite type="cable"`: rigid capsules joined by ball
  joints, with the `mujoco.elasticity.cable` plugin for bending and twisting. Its mass is
  the cable's total mass.
- Each capsule has a semantic point in a CRAM world, a body on a free connection below
  the world's root that follows the capsule's measured pose. The points add no second
  physical body; nothing moves a capsule from the semantic side.
- The pads hold the cable by friction alone: no welds, equality constraints or
  reparenting. A pinned cable keeps its first point on a ball joint; a loose one falls
  when the pads open.
- A cable MuJoCo cannot build is refused with MuJoCo's reason.

It needs MuJoCo and the CRAM workspace (`semantic_digital_twin`, `physics_simulators`);
without them the routes answer which modules are missing.

| Method | Route below `/api/plugins/cable-lab/` | Body |
| --- | --- | --- |
| GET | `state` | |
| POST | `start` | a cable configuration; `{}` builds the default cable |
| POST | `command` | `{"action": "pinch"}`, `release`, `lift`, `lower`, or `move` with a `position` |
| POST | `reset` | |
| POST | `stop` | |
