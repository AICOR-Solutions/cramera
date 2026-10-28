# cramera-bridge

Publishes a running CRAM world to the cramera viewer, records runs into scene bundles
with the class of each entity and the world's semantic annotations
(`cramera-record-classes` names them in bundles recorded before), onboards demos, turns bundles back into CRAM worlds, answers questions in the entity
query language about live worlds and recorded scenes (`cramera_bridge.questions`, with
`cramera-record-answers`) and performs the plans composed in the plan builder
(`cramera_bridge.plans`). It is the only package that imports the CRAM
workspace, and needs it installed. See the repository README and
`docs/architecture.md`.

## Publishing how plans are resolved and the queries a process asks

A process that resolves the open parts of its plans, or steps through the queries it
asks, publishes protocol documents to the live publisher of its `LiveVisualization`:

```python
publisher = visualization.publisher
highlight = publisher.scene_highlight([piece], framed=[piece])
publisher.resolutions.publish(resolutions, execution)  # PlanResolutions
publisher.query_steps.publish(steps, control)  # QuerySteps
```

`execution` (a `ResolutionExecution`) carries out a resolved plan when the viewer asks,
and `control` (a `QueryStepControl`) holds the process at each query until the viewer
moves on; either may be left out. The viewer shows the Plan resolution and Queries
panels once a process publishes them.

## Stepping through a robot task's queries

Every `RobotTaskDemo` can step through the queries it asks: its command
(`TaskCommand`) takes `--step-queries`, and then the run is published from before its
setup, so it is held at the first query it asks. `--no-hold` starts it without
holding (the viewer can turn holding on), `--port` (8765 by default) is where it is
published, and `--name` the name its recording is saved under.

```bash
python -m cramera_bridge.demos.query_stepping --bundle ~/.cramera/scenes/aicor_medical_lab
python -m cramera_bridge.demos.garmi_apartment --step-queries --name garmi_run_1
curl -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8765/query_steps/next
```

Only the task's own queries are stepped: those asked on the run's thread by code outside
the CRAM workspace, such as `VesselTransferDemo` finding its robot, the bench's handles
and its vessel, and the parts a plan leaves open, which coraplex grounds through the
context's `query_backend`. What CRAM's packages ask for their own purposes, such as a
robot part finding its robot or the world reasoner's rules, is answered without a step.
Each query is held where it is asked and again where its answering ends; a part a plan
leaves open ends once its candidate was carried out, and its answers are published as
they are given. A step names the action under way, or the task while none is. The
recording keeps the steps (`query_steps.json`) and is stamped with a clock that stands
still while the run is held, so its replay keeps the run's pace.

`cramera_bridge.query_stepping.QueryStepper` does this for any thread:
`QueryStepper.watching()` steps the queries asked until the block ends,
`QueryStepper.resolving(backend)` wraps a context's backend, and
`QueryStepper.progress()` is the plan callback naming the action under way.
`HeldQueries` (`cramera_bridge.live.query_steps`) is the `QueryStepControl` that holds
the thread.

`cramera_bridge.demos.garmi_apartment` is CRAM's GARMI demonstration as a task demo:
GARMI carries a bowl off the kitchen counter and a spoon out of a drawer to the table,
each transport grounded by a query. It needs ROS 2 with `iai_garmi_apartment` and
`garmi_description` built.
