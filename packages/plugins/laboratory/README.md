# cramera-laboratory

The **Medical lab** tab in the cramera viewer: the compact AICOR workbench, its
five device bundles, and an optional MuJoCo simulation. The expanded laboratory is
not shipped or offered.

From the repository root, in the viewer's virtual environment:

```bash
python -m pip install -e ./packages/protocol -e ./packages/viewer \
  -e './packages/plugins/laboratory[physics]'
cramera --no-browser --keep-running
```

Open [the viewer](http://127.0.0.1:8711/?panel=laboratory) and choose **Medical lab**,
then **Open** or **Simulate with contact physics**. Without `[physics]`, the scene
still opens and the tab explains how to install MuJoCo into the same environment
and restart the viewer. The setup help is always available in the tab.

See [the local setup guide](../../../docs/local-medical-lab.md) for installation,
controls and troubleshooting.

## Contact simulation

The simulation preserves the compact lab's controls:

- Pulling and releasing vessels and the stopper with a bounded spring; only reset
  writes poses directly.
- Filling, sloshing, pouring, catching and spilling liquid, with volume accounting.
- Scale readings from contact load, with taring.
- A centrifuge with a driven lid and rotor, sample clamps, load balance checks,
  operating manuals and evaluated start requirements.
- Force-limited refrigerator and drawer drives and storage contents.
- Two dispenser reservoirs and dosing into an upright, open, aligned vessel.

The liquid is a reduced free-surface model; pressure, wetting and chemistry are not
modelled. The scale filters contact load. The centrifuge only secures a vessel
when it rests seated and still; starting requires a closed lid and the manual's
sample and balance requirements. A dispenser dose stops if the vessel leaves its
receiving position.

The viewer owns one simulation, shared by its browser clients, and closes it at
shutdown. The contact simulation needs neither CRAM nor ROS. MuJoCo is optional;
without it the controls report the missing dependency and simulation routes return
503. The [official Python package](https://mujoco.readthedocs.io/en/stable/python.html#installation)
includes the engine.

## PR2 vessel transfer

The optional `[bridge]` extra installs `cramera-bridge`. Its native world and
transfer implementation need the CRAM workspace and robot descriptions as well.
The transfer targets current CRAM APIs; see the setup guide for the verified revision.
The plugin passes the compact bundle path to the bridge, starts the plan in a
separate process and offers its state, stop control and recording in the tab.
No CRAM package is imported by this plugin.

`cramera-laboratory-transfer` is a wrapper for the same bridge task. The task picks
a vessel from A1, lifts it and places it into A3; it saves a recording only when
its action, motion and contact checks succeed. A missing CRAM installation is
reported before starting the native task.

## Assets

`resources/aicor_medical_lab` holds the compact scene. The independent centrifuge,
dual dispenser, scale, tube rack and refrigerator are under
`resources/laboratory_devices`; the centrifuge manuals are under
`resources/centrifuge_manuals`.

These assets use `LicenseRef-AICOR-Laboratory-Assets`, separately from the software
licence. Keep `LICENSE.txt`, `NOTICE.md` and `rights.json` with every authorized
copy. Installing the scene preserves these files.

## Tests

```bash
python -m pytest -q packages/plugins/laboratory/test
```

Physics tests need the `[physics]` extra. The bridge owns native CRAM integration
tests; the plugin's tests exercise the viewer, controls, process management and
missing-dependency behavior without CRAM.
