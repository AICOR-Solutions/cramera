# Asking a recorded robot run in the entity query language

This guide sets up the viewer on the recorded Tracy shape-sorting episode and walks
through asking it questions in the entity query language's match syntax:

- hints while a query is written,
- any class of CRAM's semantic digital twin, asked of the world as it was at the paused
  frame,
- each answer lit up in the 3D view.

## One command

Once the stack is installed (steps 1 and 2), this starts everything:

```bash
~/Projects/cramera/scripts/eql_demo.sh
```

It starts the viewer and rebuilds the world Tracy's run was recorded in, so the first
question answers at once. Then it opens the browser on the Tracy episode, where queries
are asked of that world at the frame the timeline shows. Ctrl+C in the terminal stops
the viewer.

A scene's name after `cramera` opens the browser on it, so with the demo scenes set this
starts the viewer on the Tracy episode:

```bash
CRAMERA_SCENES=~/Projects/cramera/demo cramera tracy_shape_sorting
```

## Asking the running program

To ask the real program, with its semantic digital twin, MuJoCo and giskard running, run
a demo live and let the viewer follow it:

```bash
CRAMERA_SCENES=~/Projects/cramera/demo cramera --live
```

`--live` opens the browser following the live publisher on this machine, the one
`cramera-live demo.py` starts. While the viewer shows that run, the EQL panel sends
every query, hint and plain-language question to the publisher, which answers from the
running process's own world, held still while the query is answered. The line under
the query box says so, and the ready-made questions that need a live run are offered.
Try, while Tracy lifts a piece:

```python
piece = a(Body).from_(domain=scene_object)
piece.where(piece.global_pose.z > 0.92)
```

Hints after a dot follow the whole path, as in `body.global_pose.position.`, a pattern,
as in `a(Arm).end_effector.`, and a variable the query assigns, as in `piece.`.

## Asking a recording of a live run

A run recorded live and saved from the viewer keeps the world it ran in: the bundle's
`world_history.json.gz` holds the CRAM world's modification blocks and the value of every
degree of freedom at every frame. Asking such a scene rebuilds that very world, with the
same bodies, robot, arms, grippers and annotations, and moves it to the frame the
viewer shows. It is answered by the same desk as the live run: the same variables,
classes, ready-made questions and hints. The query above, asked of the recording at a
frame where Tracy lifts a piece, answers that piece, and nothing at a frame where every
piece lies on the table.

Scenes recorded without a world, such as converted stages and older recordings, are
still asked through their recorded knowledge, and through a Paused World rebuilt from
the recorded poses.

## 1. Check out the two branches

The viewer comes from this repository. The query language comes from the CRAM
monorepo checkout next to it.

```bash
cd ~/Projects
git clone git@github.com:AICOR-Solutions/cramera.git          # if not cloned yet
git -C cramera fetch origin && git -C cramera checkout eql-demo

# CRAM: the integration branch, in a worktree of your CRAM checkout
cd ~/Projects/cognitive_robot_abstract_machine
git fetch origin
git worktree add ~/Projects/cram-eql-demo eql-cramera-demo   # or: git checkout eql-cramera-demo
git -C ~/Projects/cram-eql-demo submodule update --init --recursive
```

## 2. Install the stack into its own environment

```bash
cd ~/Projects/cramera
git submodule update --init
python3 scripts/install_stack.py --cram ~/Projects/cram-eql-demo --venv ~/.virtualenvs/cramera-eql --dev
source ~/.virtualenvs/cramera-eql/bin/activate
pip install ruff playwright        # ruff for krrood's tests, playwright for the walkthrough
```

## 3. Start the viewer

```bash
cd ~/Projects/cramera
cramera --demo-scenes demo --port 8722
```

Open <http://127.0.0.1:8722/>. In **Task** choose **tracy_shape_sorting**.

## 4. Ask the recorded scene

The Tracy episode was recorded live from the MuJoCo demo and keeps the world it ran in
(see "Asking a recording of a live run" above). The **EQL** box at the top right holds
the query, and every query is asked of that world, rebuilt and moved to the frame the
timeline shows: Tracy's own robot, arms, grippers, table and pieces, as the classes of
CRAM's semantic digital twin.

Hints appear as you type. Arrow keys choose a hint, and **Tab** or **Enter** takes it.
**Ctrl+Space** lists every name, and **Ctrl+Enter** runs the query. After `a(Arm)(`, the
hints are the fields of `Arm` that the pattern may constrain. After a dot, they are the
attributes of the name before it.

Try these:

```python
an(Arm)                                                     # both arms light up
an(EndEffector)(fingers=none_is(TracyRightGripperLeftFinger))   # the left gripper only
an(Arm)(end_effector=an(EndEffector)(fingers=a(TracyRightGripperLeftFinger)))
a(Tracy)(left_arm=an(Arm)(end_effector=a(TracyLeftGripper)))
a(ShapeSortingPiece)                                        # the four pieces
an(entity(surface))                                         # the table
```

The variables are the live run's: `body`, `scene_object`, `annotation`, `handle`,
`surface`, `robot`, `arm` and `world`.

### Pause and ask: the world changes over the run

Drag the timeline (or pause the replay) and ask the same query again. The line under
the query box says which frame it is asked at:

```python
piece = a(Body).from_(domain=scene_object)
piece.where(piece.global_pose.z > 0.92)
```

| Frame | `piece.global_pose.z > 0.92` |
| --- | --- |
| 800 | nothing: every piece lies on the table |
| 1200 | `square_piece`, lifted by Tracy |
| 2000 | nothing: the square piece is in its hole |
| 2400 | `circle_piece` |
| 3600 | `rectangle_piece` |
| 5600 | `triangle_piece` |

## 5. Replay the walkthrough automatically

With the viewer running:

```bash
python -m playwright install ffmpeg      # once, for the video
python scripts/eql_demo_walkthrough.py /tmp/eql-demo
```

It saves a screenshot of every step and a `.webm` video of the whole walk to
`/tmp/eql-demo`.

## What is known not to work yet

- The pieces are `ShapeSortingPiece` only. The cylinder, cube and prism classes arrive
  when the Montessori shape vocabulary (#488) lands.
- `an(Arm | EndEffector)` repeats some of its answers.
- Reading an attribute of a `the(...)` query, as in `the(...).global_pose`, answers the
  expression instead of its value. Select the attribute inside the query instead.
