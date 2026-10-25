# Run the wood workshop locally

There are two setups:

| Setup | What you get |
| --- | --- |
| Latest viewer + SSH bundles | The deployed `aicor_workshop` scene and the existing `aicor_workshop_pr2` recording, copied with all their assets. |
| Pinned historical viewer + workshop plugin | An interactive MuJoCo workshop, with the layout packaged at that revision. |

Current `main` no longer includes the workshop plugin or its protocol modules. Do
not install the historical plugin into a current viewer environment: those imports
fail even though both packages still have version `1.0.0`. Keep the two environments
separate. Neither setup below needs CRAM or ROS.

## Copy the deployed scenes and use the latest viewer

Run these commands locally in Bash. You need Git, Python 3.11 or newer with `venv`
and pip, SSH access to the deployment, and `rsync` on both machines. Substitute your
SSH login and identity file; the paths below use the deployed workshop's layout.
The host must already be in your verified SSH `known_hosts` file.

The workshop assets use `LicenseRef-AICOR-Workshop-Assets`, separately from the
software licence. Only copy them with the required permission, keep `LICENSE.txt`,
`NOTICE.md` and `rights.json`, and keep the downloaded assets out of Git and public
hosting. The commands copy each complete bundle into a new private directory.

```bash
SSH_HOST=user@your-server
SSH_IDENTITY="$HOME/.ssh/id_ed25519"
REMOTE_ROOT=/srv/cramera-workshop

umask 077
LOCAL_ROOT=$(mktemp -d "$HOME/cramera-workshop.XXXXXX")
printf 'Local setup: %s\n' "$LOCAL_ROOT"
unset PYTHONPATH PYTHONHOME  # avoid inheriting a sourced ROS/CRAM workspace

git clone --branch main https://github.com/AICOR-Solutions/cramera.git "$LOCAL_ROOT/source"
git -C "$LOCAL_ROOT/source" rev-parse HEAD > "$LOCAL_ROOT/viewer-revision.txt"
python3 -m venv "$LOCAL_ROOT/venv"
"$LOCAL_ROOT/venv/bin/python" -m pip install \
  "$LOCAL_ROOT/source/packages/protocol" \
  "$LOCAL_ROOT/source/packages/viewer" \
  "$LOCAL_ROOT/source/packages/plugins/offline"

# Resolve current once, so a deployment cannot change the source between copies.
REMOTE_RELEASE=$(ssh -i "$SSH_IDENTITY" -o IdentitiesOnly=yes \
  -o BatchMode=yes -o StrictHostKeyChecking=yes "$SSH_HOST" \
  "readlink -f '$REMOTE_ROOT/current'")
test -n "$REMOTE_RELEASE"
printf '%s\n' "$REMOTE_RELEASE" | tee "$LOCAL_ROOT/server-release.txt"

export CRAMERA_DATA="$LOCAL_ROOT/data"
export CRAMERA_SCENES="$LOCAL_ROOT/scenes"
mkdir -p "$CRAMERA_DATA" "$CRAMERA_SCENES"
printf -v SSH_COMMAND 'ssh -i %q -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes' "$SSH_IDENTITY"
rsync -a --protect-args -e "$SSH_COMMAND" \
  "$SSH_HOST:$REMOTE_RELEASE/scenes/aicor_workshop" "$CRAMERA_SCENES/"
rsync -a --protect-args -e "$SSH_COMMAND" \
  "$SSH_HOST:$REMOTE_RELEASE/scenes/aicor_workshop_pr2" "$CRAMERA_SCENES/"

"$LOCAL_ROOT/venv/bin/cramera-check-bundle" \
  "$CRAMERA_SCENES/aicor_workshop" \
  "$CRAMERA_SCENES/aicor_workshop_pr2"
```

Both checks must say `complete`. A missing file usually means an incomplete copy;
copy the whole directory again, including meshes, URDFs, trajectories and rights
files. This checks that references resolve, not that a robot plan passes collision
acceptance.

`aicor_workshop` is an authored scene with an initial-state trajectory;
`aicor_workshop_pr2` is an existing recorded PR2 run. The viewer discovers both
bundle directories without copying the server's shared `index.json`.

```bash
"$LOCAL_ROOT/venv/bin/cramera" --host 127.0.0.1 --port 8873 \
  --keep-running --no-browser --scenes "$CRAMERA_SCENES"
```

Open [the workshop](http://127.0.0.1:8873/?scene=aicor_workshop) or
[the PR2 recording](http://127.0.0.1:8873/?scene=aicor_workshop_pr2).
Stop the viewer with Ctrl-C. `--keep-running` makes an occupied port an error;
choose another unused port and adjust the links if needed.

Keep the printed `LOCAL_ROOT` path to start it again. In a new terminal, set
`LOCAL_ROOT` to that path and restore both `CRAMERA_DATA="$LOCAL_ROOT/data"` and
`CRAMERA_SCENES="$LOCAL_ROOT/scenes"` with `export` before starting the viewer.
Run `unset PYTHONPATH PYTHONHOME` again in that terminal.
An existing bundle in `$CRAMERA_DATA/scenes` takes precedence over `--scenes`, so
using an isolated data directory prevents an older local copy from hiding this one.

## Run the historical interactive workshop

Use a second checkout and environment pinned to
`875161779bbd6c87bfd5f687ee02e20a301ed94d`, which contains matching protocol, viewer
and workshop packages. This starts the plugin's packaged workshop. Its tool cradle
and assembly layout differ from the deployed scene copied above.

```bash
umask 077
INTERACTIVE_ROOT=$(mktemp -d "$HOME/cramera-workshop-interactive.XXXXXX")
printf 'Interactive setup: %s\n' "$INTERACTIVE_ROOT"
unset PYTHONPATH PYTHONHOME

git clone https://github.com/AICOR-Solutions/cramera.git "$INTERACTIVE_ROOT/source"
git -C "$INTERACTIVE_ROOT/source" checkout --detach \
  875161779bbd6c87bfd5f687ee02e20a301ed94d
python3 -m venv "$INTERACTIVE_ROOT/venv"
"$INTERACTIVE_ROOT/venv/bin/python" -m pip install \
  "$INTERACTIVE_ROOT/source/packages/protocol" \
  "$INTERACTIVE_ROOT/source/packages/viewer" \
  "$INTERACTIVE_ROOT/source/packages/plugins/workshop[physics]"

export CRAMERA_DATA="$INTERACTIVE_ROOT/data"
export CRAMERA_SCENES="$("$INTERACTIVE_ROOT/venv/bin/cramera-workshop" scenes-directory)"
mkdir -p "$CRAMERA_DATA"
"$INTERACTIVE_ROOT/venv/bin/cramera" --host 127.0.0.1 --port 8874 \
  --no-browser --scenes "$CRAMERA_SCENES"
```

Open [the interactive workshop](http://127.0.0.1:8874/?scene=aicor_workshop&panel=workshop),
then use the **Workshop** panel to start physics, grab and release objects, move
drawers, and pause or reset the world. If the panel reports missing physics
libraries, rerun the install command with `[physics]` in this environment and
restart the viewer. All browsers connected to this viewer share one simulation.
This revision has no `--keep-running` option and fails if its port is occupied.
Stop with Ctrl-C. For a later run, set `INTERACTIVE_ROOT` to its printed path,
restore `CRAMERA_DATA` and `CRAMERA_SCENES` with the exports above, and repeat only
the viewer command after `unset PYTHONPATH PYTHONHOME`. No reinstallation or SSH
connection is needed.

This historical setup was checked with Python 3.12: the plugin loaded without CRAM
or ROS, and start, state (18 object poses) and pause succeeded. It is not a complete
robot-task acceptance test. The historical `insertion` and `assembly` CLI commands
need the corresponding CRAM stack; the full PR2 assembly is documented as failing
collision acceptance and is not saved as a passing recording. Viewing the existing
SSH recording does not establish that the newer assembly passes.

For the controls, physical simplifications and asset terms, see the
[workshop README at the pinned revision](https://github.com/AICOR-Solutions/cramera/blob/875161779bbd6c87bfd5f687ee02e20a301ed94d/packages/plugins/workshop/README.md).

If the browser reports that it cannot create a WebGL context, use a local browser
with working WebGL. The bundle check verifies file completeness, not graphics
support; some embedded browsers cannot render the scene.
