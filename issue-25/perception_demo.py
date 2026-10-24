"""A PR2 parks its arms and detects the milk in simulation, then looks for a table there is none of."""
import json, sys
from pathlib import Path
from coraplex.datastructures.enums import DetectionTechnique
from coraplex.plans.factories import sequential
from coraplex.robot_plans.actions.core.misc import DetectAction
from coraplex.robot_plans.actions.core.navigation import LookAtAction
from cramera_bridge.plans.demo import PlannedTaskDemo
from cramera_bridge.plans.world import PlannedGraspable
from cramera_bridge.robot_task import TaskCommand
from cramera_bridge.plans.steps import StepActions
from cramera_protocol.plan_builder import DemoDocument, PlanDocument
from semantic_digital_twin.semantic_annotations.semantic_annotations import Table

FAIL = "--fail" in sys.argv

class PerceptionDemo(PlannedTaskDemo):
    def build_plan(self, context):
        actions = StepActions(context, self.bodies, self.discovered_actions)
        steps = [actions.action(step) for step in self.steps()]
        steps.append(LookAtAction(target=self.bodies['milk'].global_pose))
        steps.append(DetectAction(technique=DetectionTechnique.TYPES, object_sem_annotation=PlannedGraspable))
        if FAIL:
            steps.append(DetectAction(technique=DetectionTechnique.TYPES, object_sem_annotation=Table))
        return sequential(steps, context=context).plan

raw = json.loads(Path("/home/vee/cramera/.claude/worktrees/modest-darwin-0f381b/packages/plugins/plan-builder/test/dataset/plans/pick_and_place.json").read_text())
raw["robots"] = raw["robots"][:1]
raw["robots"][0]["steps"] = raw["robots"][0]["steps"][:2]
raw["name"] = "pr2_detects_milk_fail" if FAIL else "pr2_detects_milk"
raw["selectedRobot"] = raw["robots"][0]["id"]
document = DemoDocument(plan=PlanDocument.from_json(raw))
demo = PerceptionDemo.of_document(document, port=18767)
saved = TaskCommand(demo).main(["--port", "18767"])
print("saved", saved)
