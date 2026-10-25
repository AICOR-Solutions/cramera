# AICOR laboratory devices

**Principal author:** Vanessa Hassouna · **Institution:** AICOR Institute.
Original laboratory assets require written permission for reuse. Every device
folder includes `LICENSE.txt`, `NOTICE.md` and `rights.json`; keep them with
authorized copies. Existing permissions and third-party rights are preserved.

Each subdirectory is a self-contained device model. For an authorized reuse, copy
the entire device folder: `model.urdf` refers only to relative files under
`assets/`, and the GLB files embed their material images. Coordinates are metres with Z up.

The five instruments extracted from the assembled laboratory are:

| Directory | Model | Root frame |
| --- | --- | --- |
| `centrifuge` | Housing, articulated lid, continuous rotor and four open sample sleeves | Base centre at the support surface |
| `dual_dispenser` | Dual reservoirs, nozzles, display and receiving cradle | Platform centre at the support surface |
| `scale` | Housing, weighing pan and open sample support collisions | Centre of the weighing pan |
| `tube_rack` | Two rows of three open positions | Base centre at the support surface |
| `refrigerator` | Compact cabinet, articulated glass door and six sample holders | Base centre at floor level |

These five models retain the laboratory's link names, contact geometry and
joint limits. Their `metadata.json` records the original placement in the
assembled laboratory. The room, workbench and robot are not included.

Use the installed plugin's device catalog to locate or copy a complete model:

```python
from pathlib import Path

from cramera_laboratory.devices import DeviceShelf, LaboratoryDevice

centrifuge = DeviceShelf().folder(LaboratoryDevice.CENTRIFUGE)
print(centrifuge.description)
centrifuge.copy_to(Path("my_devices"))
```

The copy keeps the URDF, referenced meshes, metadata and permission notices.
`DeviceShelf().entries()` lists these five devices. A URDF loader can read each
`model.urdf` independently; choose a distinct instance prefix when loading more
than one copy into the same world.

These URDFs supply appearance, articulation and collision geometry. The Medical
lab tab's MuJoCo simulation provides the controllers, scale readings, liquid
handling, centrifuge interlocks and reduced refrigerator temperature model.
Loading a URDF alone does not run those behaviors. Nominal masses and inertias
are model parameters, not calibrated manufacturer data. Open sleeves use
segmented wall colliders so their insertion axes remain accessible.
