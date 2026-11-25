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

It starts the viewer and builds Tracy's paused world in the background, so the first
question answers at once. Then it opens the browser on the Tracy episode. Choose
**Paused World** in the drop-down next to **Ask** and write queries. Ctrl+C in the
terminal stops the viewer.

A scene's name after `cramera` opens the browser on it, so with the demo scenes set this
starts the viewer on the Tracy episode:

```bash
CRAMERA_SCENES=~/Projects/cramera/demo cramera tracy_shape_sorting
```

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

The **EQL** box at the top right holds the query. The drop-down next to **Ask** chooses
what the query ranges over:

| Scope | What it asks |
| --- | --- |
| Current State Queries | The recording's own summary: its robot, arms, grippers, objects, steps, joints and plan nodes. An object's `position` is where it is at the shown frame, and its `spawn_position` is where it started. |
| Paused World (any CRAM class, at the shown frame) | The scene rebuilt as a CRAM world, with Tracy's joints and the free objects where they are at the frame the timeline shows. Every class of the semantic digital twin can be named. |

Hints appear as you type. Arrow keys choose a hint, and **Tab** or **Enter** takes it.
**Ctrl+Space** lists every name, and **Ctrl+Enter** runs the query. After `a(Arm)(`, the
hints are the fields of `Arm` that the pattern may constrain. After a dot, they are the
attributes of the name before it.

Try these, in **Paused World**:

```python
an(Arm)                                                     # both arms light up
an(EndEffector)(fingers=none_is(TracyRightGripperLeftFinger))   # the left gripper only
an(Arm)(end_effector=an(EndEffector)(fingers=a(TracyRightGripperLeftFinger)))
a(Tracy)(left_arm=an(Arm)(end_effector=a(TracyLeftGripper)))
a(ShapeSortingPiece)                                        # the four pieces
```

The run itself is in the same scope: its steps, its plan and its actions, which piece a
gripper holds and from when to when, and what of it is under way at the shown frame.

| Variable | What it ranges over |
| --- | --- |
| `piece` | the four pieces, as `ShapeSortingPiece` |
| `holding` | every holding of a piece by a gripper, as `Holding(gripper, piece, step, grasped_at_frame, released_at_frame)` |
| `step`, `plan_node`, `action` | the run's steps, the executed plan's nodes and its actions |
| `held_piece`, `holding_now`, `step_now` | the same, under way at the shown frame |

```python
a(Holding)(gripper=a(TracyLeftGripper)).from_(domain=holding_now)   # held now? lights gripper and piece
an(entity(held_piece))
an(entity(step_now))
an(RecordedPlanNode)(kind=PlanNodeKind.ACTION, target="cylinder 1")
an(RecordedPlanNode)(label="PickUpAction")
```

### Pause and ask: the world changes over the run

Drag the timeline (or pause the replay) and ask the same query again. The line under
the query box says which frame it is asked at:

```python
piece = a(Body).from_(domain=scene_object)
piece.where(piece.global_pose.z > 0.92)
```

| Frame | `piece.global_pose.z > 0.92` | `held_piece` | `step_now` |
| --- | --- | --- | --- |
| 100 | nothing: every piece lies on the table | nothing | `run` |
| 400 | `cylinder 1` | `cylinder 1`, in the left gripper | `move_cylinder 1` |
| 600 | `cylinder 1`, put down on the board | nothing | `move_cylinder 1` |

In **Current State Queries** the objects are the recording's own `RecordedObject`s, not
CRAM bodies, so the same question is asked of their `position`:

```python
an(entity(arm))                                             # the recorded arms, lit up
a(RecordedObject)(height_metres=0.03)
lifted = a(RecordedObject).from_(domain=scene_object)
lifted.where(lifted.position.z > 0.92)                      # cylinder 1 from frame 268 on
```

A query naming a class its domain never holds, such as `a(Body).from_(domain=scene_object)`
here, does not answer an empty list. It answers an error that names both types and says to
choose **Paused World**.

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
- The recording does not say when each plan node ran, so `step_now` comes from the
  run's segments, not from the plan's actions.
- `an(Arm | EndEffector)` repeats some of its answers.
- Reading an attribute of a `the(...)` query, as in `the(...).global_pose`, answers the
  expression instead of its value. Select the attribute inside the query instead.
