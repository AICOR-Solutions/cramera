# cramera-workshop

A plugin of the cramera viewer for the AICOR wood workshop, `aicor_workshop`: a
workbench with a drawer cabinet, shelves, boxes of loose screws and nails, a wooden
workpiece with a pilot hole and a screwdriver.

```bash
pip install -e 'packages/plugins/workshop[physics]'
cramera --scenes "$(cramera-workshop scenes-directory)"
```

## Workshop panel

On a scene that describes a workshop, the **Workshop** side panel starts a MuJoCo
contact world built from the bundle's URDF collision primitives and puts the measured
poses and drawer positions on the shown scene.

- Boxes, screws, nails, the workpiece and the screwdriver are independent rigid bodies
  under gravity, friction and contacts; contents are not parented to their box, so a
  tilted box spills them. The bench, shelves, vise and tool board are fixtures.
- **Grab selected** holds a body with a damped, force-limited spring (35 N, 1.2 N m) at
  its measured pose; the move buttons shift the spring's target by 2.5 cm and the tilt
  buttons turn it by 15°. **Release** lets gravity and contacts act. A body picked in
  the 3D view becomes the selected one.
- The drawer buttons set force-limited motor targets; an obstruction stops a drawer.
- **Screw driving**: **Position screw** carries the selected screw to the pilot hole
  through clearance waypoints and releases it there; the thread captures a screw whose
  tip is at the entrance on the pilot axis. **Align driver** seats the screwdriver's
  blade in the slot. **Drive in**, **Reverse** and **Stop** turn the held driver. An
  alignment stops at a waypoint the body does not reach.
- The thread is ideal: the driver's measured rotation advances the screw by the pitch
  (6 mm per turn), with equal and opposite reactions on screw and workpiece, and stops
  at the end of its travel. It simulates no wood cutting, damage, tightening torque or
  thread-flank contact.
- One world is shared by every browser. It pauses and lets go after 90 s without a
  browser asking for its state, and a solver that loses a valid state stops it until
  **Reset**.
- On a recording made in the workshop, the panel shows the assets' rights.

| Method | Route below `/api/plugins/workshop/` | Body |
| --- | --- | --- |
| GET | `state` | |
| POST | `command` | `{"action": "start"}`, `pause`, `reset`, `release`; `grab` with `object`; `move` with `object` and `pose`; `drawer` with `joint` and `position`; `drive` with `direction` (`forward`, `reverse`, `stop`) |

Without MuJoCo the state names the missing libraries and commands answer 503.

## PR2 demos

With `cramera-cram` and the CRAM workspace, the PR2 performs native CRAM plans in the
workshop; each run is published live, measured and saved as a scene bundle named
`aicor_workshop_pr2_<task>`.

```bash
cramera-workshop insertion          # fetch the screw box, insert a screw into the pilot hole
cramera-workshop assembly           # the whole two-handed assembly
cramera-workshop assembly --publish SHARED_SCENES
cramera-workshop check-release ~/.cramera/scenes/aicor_workshop_pr2_screw_assembly
```

The assembly's ten stages are: retrieve and place the screw box, pick up a screw,
move to the assembly station, pick up the screwdriver, stabilize the screw at the
pilot hole, align the screwdriver, engage it, release the supporting hand, drive the
screw, put the screwdriver down.
Each stage is one step of the saved recording.

The assembly runs every stage but is not saved yet: it fails the requirement that
nothing penetrates. While the screw is driven the left elbow drifts into the
furniture and the screw box, and while the screwdriver is put down the right arm
passes through the workbench's furniture; the seated blade also overlaps the
fingertips holding the screw by a few millimetres.

- The robot moves its base only along straight corridors with its heading kept, each
  checked against the collision shapes in a separate copy of the collision geometry.
- While the box is carried, its screws slide in a separate MuJoCo contact world whose
  box follows the native one, and their poses relative to it are put into the native
  box's frame; the coupling is one way. A run whose screws leave the box fails.
- The screw is grasped the same way however far it rolled about its shaft in the box.
- The thread is a native helical connection, installed only once the blade is measured
  seated in the slot and the screw's tip at the entrance on the pilot axis.
- A run is saved only when its measurements meet the requirements; the release check
  reads a saved assembly alone, without CRAM, before it is published.

## Asset rights

The workshop's original assets in `src/cramera_workshop/resources/aicor_workshop` are
not under the software's licence. They are `LicenseRef-AICOR-Workshop-Assets`:
reuse, modification and redistribution need prior written permission from Vanessa
Hassouna; see `LICENSE.txt` and `NOTICE.md` in that directory, which every copy must
keep. A saved recording carries both files, `rights.json` and the rights in its scene
description.
