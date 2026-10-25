# AICOR dual dispenser

**Principal author:** Vanessa Hassouna · **Institution:** AICOR Institute.
Original laboratory assets require prior written permission for reuse; see
[LICENSE.txt](LICENSE.txt) and [NOTICE.md](NOTICE.md). Keep these notices with
authorized copies. Existing permissions and third-party rights are preserved.

For authorized reuse, load `model.urdf` independently or copy the complete folder
into another project.
All visual files and artwork are included under `assets/`.

The root `laboratory_pipetting_station` is at the platform centre on its support
surface. Coordinates are metres, with Z up and the front toward negative Y.
The visual contains both reservoirs, supply tubes, nozzles and instrument screen.
Separate collision primitives preserve the open receiving area and front grasp
approach. The original laboratory placement is recorded in `metadata.json`.

The receiving guides leave an 18.5 mm opening around the 18 mm sample vessel.
Their 0.25 mm side clearance limits leaning after the vessel is released; the
front stays open for horizontal loading. The visible guides and collision boxes
have the same dimensions. This is a receiving support, not a retention clamp;
the simulation still checks the measured vessel pose before dispensing.

The model is stationary and has no moving joints. Dosing, reservoir inventory,
liquid transfer and the live screen require the laboratory simulation controller.
