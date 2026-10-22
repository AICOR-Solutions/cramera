# cramera-laboratory

A cramera viewer plugin for the AICOR laboratory: the laboratory as scene bundles, its
independent devices, its MuJoCo contact simulation operated from the viewer's
**Laboratory** panel, and the laboratory as a CRAM world.

```bash
pip install ./packages/protocol ./packages/viewer './packages/plugins/laboratory[physics]'
cramera
```

Open the **Laboratory** tab, install a laboratory or start its contact simulation. The
viewer then shows the bundle `<laboratory>_contact_physics` in its local scenes and
follows the simulation.

## Laboratories and devices

| Laboratory | What it holds |
| --- | --- |
| `aicor_medical_lab` | The bench: rack with six slots, four vessels, stopper, drawer, scale, centrifuge, dispensing station and sample refrigerator. |
| `aicor_medical_lab_large` | The bench in a room with five workstations and fifteen more instruments with moving parts. |

The twenty device folders under `resources/laboratory_devices` each load on their own
with CRAM's URDF parser (`DeviceShelf().folder("centrifuge").description`), and
`DeviceFolder.copy_to` copies a whole folder with its terms.

**Asset terms.** Every asset folder carries `LICENSE.txt`, `NOTICE.md` and
`rights.json`: the assets are `LicenseRef-AICOR-Laboratory-Assets`, and reuse,
modification or redistribution needs the owner's prior written permission. Installing
a laboratory copies these files with it; it leaves out only the Blender sources.

## Contact simulation

Needs MuJoCo (the `physics` extra); without it the panel says so and the simulation
routes answer 503. One simulation runs at a time, stepped in real time on a worker
thread; every command waits for the step in progress.

- **Pulling.** A person moves a free object by pulling it towards a target with a
  bounded spring (at most 0.6 N, gravity compensation included). Only a reset writes
  poses; gravity, friction and contacts decide where an object goes.
- **Liquid.** A reduced free-surface model per vessel follows the measured motion,
  sloshes, pours over the lowest rim point, flies, is caught by other vessels or
  spills into puddles; every millilitre is accounted for. The liquid's mass is added
  to the vessel. Pressure, wetting and chemistry are not modelled.
- **Scale.** Reads the vertical contact load on its pan and holder, filtered like a
  balance's display; it tares once the reading settled.
- **Centrifuge.** A force-limited lid and rotor drive. A vessel can be secured only
  when it is measured to rest seated and still on a holder's floor; the clamp is
  anchored where it rests. A run needs a closed lid, a balanced load (opposite masses
  within 0.25 g) and as many secured samples as the manual it follows asks for. The
  manual is a small Markdown file (`resources/centrifuge_manuals`); another one can be
  given, and its revisions and the evaluated start requirements are reported.
- **Refrigerator, drawer, instruments.** Force-limited drives move the door, the
  drawer (at most 40 N) and the expanded room's instrument joints; storage positions
  report the vessels the cabinet carries.
- **Dispensing station.** Two reservoirs dose into the vessel standing upright, open
  and aligned beneath the nozzle; a dose stops and says why when that no longer holds.

The routes lie below `/api/plugins/laboratory/` and are named by
`cramera_protocol.laboratory.physics.LaboratoryRoute`; every simulation route answers
a `SimulationAnswer`.

| Route | Method | Body |
| --- | --- | --- |
| `laboratories` | GET | |
| `install` | POST | `LaboratoryChoice` |
| `devices`, `device-files/<device>/<file>` | GET | |
| `physics/state` | GET | |
| `physics/start` | POST | `LaboratoryChoice` |
| `physics/stop`, `physics/reset`, `physics/release`, `physics/scale/tare` | POST | `{}` |
| `physics/target` | POST | `TargetRequest` |
| `physics/liquid` | POST | `LiquidRequest` |
| `physics/centrifuge` | POST | `CentrifugeRequest` |
| `physics/manual` | POST | `ManualRequest` |
| `physics/refrigerator`, `physics/drawer` | POST | `OpeningRequest` |
| `physics/dispenser` | POST | `DispenserRequest` |
| `physics/instrument` | POST | `InstrumentRequest` |

## The laboratory as a CRAM world

Needs the CRAM workspace and cramera-cram (the `cram` extra).
`LaboratoryEnvironment` builds on `cramera_cram.scenes.BundleEnvironment`: the
environment with its joints, the vessels and the stopper from their own URDFs with
collision shapes and inertia, the closed cabinet panels, and a `Handle` annotation on
every handle bar. Loading starts no motion and no simulation.

```python
from semantic_digital_twin.api import RobotSpecification
from semantic_digital_twin.robots.pr2 import PR2

from cramera_laboratory.world import LaboratoryEnvironment

laboratory = LaboratoryEnvironment()
world = laboratory.create_world(robots=[RobotSpecification(semantic_annotation_type=PR2)])
target = laboratory.slot_pose("A3", world)
```

`LaboratoryEnvironment(allow_support_contacts=True)` leaves out the contacts between
the vessels and the rack they rest in, and nothing else.

### PR2 vessel transfer

`cramera-laboratory-transfer` runs a `RobotTaskDemo`: a PR2 at the bench picks the
vessel in A1 with CRAM's pickup, closing its fingers only until both pads reach the
glass, lifts it 16 cm and places it into A3. The run is published while it runs and
saved as `aicor_medical_lab_pr2_transfer` with its measurements; it fails unless both
actions succeed, the vessel was carried and lifted, ends within a millimetre of A3,
nothing else moved and the pads never cut into the glass. `--publish DIR` copies the
saved recording into a shared scenes directory.

## Tests

```bash
python -m pytest packages/plugins/laboratory/test
```

The simulation's tests need MuJoCo and the CRAM world's tests the CRAM workspace;
where either is missing they are skipped.
