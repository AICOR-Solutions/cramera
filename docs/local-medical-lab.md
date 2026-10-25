# Run the medical laboratory locally

The compact bench (`aicor_medical_lab`) and expanded room
(`aicor_medical_lab_large`) on the SSH server are complete scene bundles. Current
cramera can display local copies without ROS, CRAM or MuJoCo. Their interactive
liquid, scale, centrifuge and instrument controls belong to the earlier laboratory
plugin, removed from `main` on 23 October 2026. The second setup below runs that
plugin in its own pinned environment.

Use Bash on Linux, Python 3.11 or newer with `venv` and pip, Git, OpenSSH and rsync.
The examples create new directories under your home folder. Choose unused names;
stop if a directory already exists. Keep the two Python environments separate.

## View the server's laboratories with current cramera

### Install the viewer

```bash
git clone https://github.com/AICOR-Solutions/cramera.git "$HOME/cramera-lab-viewer"
cd "$HOME/cramera-lab-viewer"
unset PYTHONPATH PYTHONHOME
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ./packages/protocol ./packages/viewer ./packages/plugins/offline
git rev-parse HEAD
```

The last command records the version you installed. The commands were checked
against `5d157e7` on 25 October 2026. Installing the viewer and offline checker alone
does not require the CRAM workspace or the object-library submodules.

### Copy the complete bundles from SSH

Set your authorized SSH account and key. The source paths below are the existing
laboratory deployment layout; adjust `LAB_REMOTE_RESOURCES` if yours differs.
The SSH host must already be in your verified `known_hosts` file.

```bash
export LAB_SSH_HOST='user@your-server'
export LAB_SSH_IDENTITY="$HOME/.ssh/your-key"
export LAB_REMOTE_RESOURCES='/srv/cramera-laboratory/cramera/src/cramera/resources'
export LAB_LOCAL="$HOME/cramera-medical-lab-local"
umask 077
mkdir "$LAB_LOCAL"
mkdir "$LAB_LOCAL/scenes" "$LAB_LOCAL/viewer-data"
printf -v LAB_SSH_COMMAND 'ssh -i %q -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes' "$LAB_SSH_IDENTITY"
rsync -a --protect-args -e "$LAB_SSH_COMMAND" \
  "$LAB_SSH_HOST:$LAB_REMOTE_RESOURCES/aicor_medical_lab" \
  "$LAB_SSH_HOST:$LAB_REMOTE_RESOURCES/aicor_medical_lab_large" \
  "$LAB_LOCAL/scenes/"
cramera-check-bundle \
  "$LAB_LOCAL/scenes/aicor_medical_lab" \
  "$LAB_LOCAL/scenes/aicor_medical_lab_large"
```

Both checks must report `complete`. Copy the whole directories, including meshes,
textures, `LICENSE.txt`, `NOTICE.md` and `rights.json`; the asset terms are separate
from the software licence. Keep these copies outside the source repository. Only
the scene bundles are needed; the server's Python environment, authentication
files and service configuration are not part of the local setup.

### Start and check the local viewer

```bash
CRAMERA_DATA="$LAB_LOCAL/viewer-data" CRAMERA_SCENES="$LAB_LOCAL/scenes" \
  cramera --host 127.0.0.1 --port 8871 --keep-running --no-browser
```

Open the [expanded laboratory](http://127.0.0.1:8871/?scene=aicor_medical_lab_large)
or [compact bench](http://127.0.0.1:8871/?scene=aicor_medical_lab).
The scene picker should list both. Inspect and select the instruments in the 3D
view; this setup displays their saved state. It does not start the server's
simulation. After copying and installing, viewing needs no SSH connection.

`CRAMERA_DATA` uses a fresh directory because local recordings take precedence
over shared scenes with the same name. `--keep-running` makes an occupied port an
error instead of stopping another viewer. Stop this viewer with Ctrl-C. To reopen
it in a new terminal, activate `$HOME/cramera-lab-viewer/.venv/bin/activate`, set
`LAB_LOCAL` again, run `unset PYTHONPATH PYTHONHOME` and repeat the launch command.

## Run the existing interactive laboratory

This uses the last local v1 plugin checkout verified for this setup, commit
`875161779bbd6c87bfd5f687ee02e20a301ed94d`. Its packaged laboratory scenes match the
server's scene descriptions. It is a historical runtime, separate from current
cramera; installing its plugin into the current viewer fails because the
laboratory protocol modules were also removed.

In a new terminal:

```bash
git clone https://github.com/AICOR-Solutions/cramera.git "$HOME/cramera-lab-interactive"
cd "$HOME/cramera-lab-interactive"
git checkout --detach 875161779bbd6c87bfd5f687ee02e20a301ed94d
unset PYTHONPATH PYTHONHOME
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ./packages/protocol ./packages/viewer \
  './packages/plugins/laboratory[physics]'
export LAB_INTERACTIVE_DATA="$HOME/cramera-medical-lab-interactive-data"
mkdir "$LAB_INTERACTIVE_DATA"
CRAMERA_DATA="$LAB_INTERACTIVE_DATA" CRAMERA_SCENES="$LAB_INTERACTIVE_DATA/scenes" \
  cramera --host 127.0.0.1 --port 8872 --no-browser
```

Use a free port: this historical viewer does not offer `--keep-running`.
Open [the local interactive viewer](http://127.0.0.1:8872/) and choose **Laboratory**
in the top bar. Each laboratory offers **Open** to install and show its scene and
**Simulate with contact physics** to start its simulation. The plugin creates a
local `<laboratory>_contact_physics`
bundle and follows the simulation. MuJoCo provides the contacts; CRAM and ROS are
not needed for these controls. The plugin's
[pinned README](https://github.com/AICOR-Solutions/cramera/blob/875161779bbd6c87bfd5f687ee02e20a301ed94d/packages/plugins/laboratory/README.md)
describes the liquid model and the scale, centrifuge and instrument controls.

Stop with Ctrl-C. For later runs, activate this checkout's `.venv`, set
`LAB_INTERACTIVE_DATA` to the existing directory, run `unset PYTHONPATH PYTHONHOME`
and repeat only the launch command. Do not reinstall into the current viewer's
environment. PR2 transfer
plans additionally need the historical CRAM integration and are outside this
contact-simulation setup.

## Troubleshooting

- **No scenes:** check that `scenes/aicor_medical_lab*/scene.json` exists and that
  the launch command uses absolute paths. A missing scenes directory is skipped.
- **Wrong laboratory:** use the fresh `CRAMERA_DATA` above; an older local bundle
  can hide a shared bundle of the same name.
- **No Laboratory link:** the current viewer has no laboratory plugin. In the
  historical environment, `/api/info` must list `laboratory`; restart after
  installing it and check which `cramera` executable the shell resolves.
- **Simulation unavailable:** install the `[physics]` extra into that same
  historical environment. Loading the scene alone does not install MuJoCo.
- **Missing mesh or texture:** repeat the complete bundle copy into a new
  directory and run `cramera-check-bundle` before opening it.
- **No WebGL context:** use a local browser with working WebGL. A successful
  bundle check verifies the files; it does not verify the browser's graphics
  support. Some embedded browsers cannot create the required context.
