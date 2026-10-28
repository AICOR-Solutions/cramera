# cramera-bridge

Publishes a running CRAM world to the cramera viewer, records runs into scene bundles
with the class of each entity (`cramera-record-classes` names them in bundles recorded
before), onboards demos, turns bundles back into CRAM worlds, answers questions in the entity
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
