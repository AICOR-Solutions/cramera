"""
The plan builder's routes: the catalog, saved plans, constraint compilation, generated
demos, the demo process and the object models' files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

from typing_extensions import Any, List, Optional

from cramera.http.messages import HttpMethod, Request, Response
from cramera.plugins import PluginPrefixRoute, PluginRoute, RouteDeclaration
from cramera.scenes import SceneCatalog
from cramera_plan_builder.constraints import ConstraintCompiler
from cramera_plan_builder.demos import DemoDirectory, DemoTemplate
from cramera_plan_builder.environments import EnvironmentBundles
from cramera_plan_builder.exceptions import ContentTooLarge, MalformedRequestBody
from cramera_plan_builder.plans import CatalogCheck, PlanCheck, PlanStore
from cramera_plan_builder.runs import DemoRunner
from cramera_plan_builder.workspace import WorkspaceLoader
from cramera_protocol.plan_builder import (
    ActionSchema,
    ConstraintText,
    DemoDocument,
    PlanBuilderCatalog,
    PlanBuilderLimits,
    PlanBuilderRoute,
    PlanDocument,
    PlanList,
    PlanRecord,
    RunRequest,
    SavedNames,
)

# %% request bodies


@dataclass(frozen=True)
class JsonBody:
    """
    The JSON body of a request, read within a size limit.
    """

    request: Request
    """
    The request.
    """

    limit: int
    """
    How large the body may be, in bytes.
    """

    def read(self) -> Any:
        """
        The HTTP boundary is where a malformed body becomes a refusal, so this is the
        one place where the decoder's errors become the builder's.

        :return: The decoded body.
        :raises ContentTooLarge: When the body is larger than :attr:`limit`.
        :raises MalformedRequestBody: When the body is no UTF-8 JSON text.
        """
        if len(self.request.body) > self.limit:
            raise ContentTooLarge(len(self.request.body), self.limit)
        try:
            return json.loads(self.request.body.decode("utf-8"))
        except ValueError as error:
            raise MalformedRequestBody(str(error)) from error


# %% routes


@dataclass(frozen=True)
class PlanBuilderRoutes:
    """
    Answers the plan builder's requests.
    """

    scenes: SceneCatalog
    """
    The scenes the viewer shows, whose bundles without a robot are environments.
    """

    workspace: WorkspaceLoader
    """
    Reads what the CRAM workspace offers.
    """

    plans: PlanStore
    """
    The saved plans.
    """

    compiler: ConstraintCompiler
    """
    Compiles constraints written in plain language.
    """

    demos: DemoDirectory
    """
    Where generated demos are written.
    """

    runner: DemoRunner
    """
    Runs the demo of a plan.
    """

    limits: PlanBuilderLimits
    """
    The bounds plans and demos stay within.
    """

    live_url: str
    """
    Where started demos publish their world.
    """

    template: DemoTemplate = field(default_factory=DemoTemplate)
    """
    Renders a plan into its demo.
    """

    def declarations(self) -> List[RouteDeclaration]:
        """
        :return: The routes, below the plugin's prefix.
        """
        return [
            PluginRoute(HttpMethod.GET, PlanBuilderRoute.CATALOG, self.answer_catalog),
            PluginRoute(HttpMethod.GET, PlanBuilderRoute.PLANS, self.answer_plans),
            PluginRoute(HttpMethod.POST, PlanBuilderRoute.PLANS, self.answer_save),
            PluginPrefixRoute(HttpMethod.GET, PlanBuilderRoute.PLAN, self.answer_plan),
            PluginRoute(
                HttpMethod.POST, PlanBuilderRoute.CONSTRAINT, self.answer_constraint
            ),
            PluginRoute(HttpMethod.POST, PlanBuilderRoute.DEMO, self.answer_demo),
            PluginRoute(HttpMethod.POST, PlanBuilderRoute.DEMOS, self.answer_write),
            PluginRoute(HttpMethod.GET, PlanBuilderRoute.RUN, self.answer_run_status),
            PluginRoute(HttpMethod.POST, PlanBuilderRoute.RUN, self.answer_run),
            PluginRoute(HttpMethod.POST, PlanBuilderRoute.RUN_STOP, self.answer_stop),
            PluginPrefixRoute(
                HttpMethod.GET, PlanBuilderRoute.OBJECT_FILES, self.answer_object_file
            ),
        ]

    # %% catalog

    def catalog(self) -> PlanBuilderCatalog:
        """
        :return: What the builder offers: the workspace's robots, objects and actions,
            the viewer's bundles without a robot, the rules and the saved plans.
        """
        workspace = self.workspace.workspace()
        actions = workspace.action_catalog()
        return PlanBuilderCatalog(
            live_url=self.live_url,
            robots=workspace.robots(),
            environments=EnvironmentBundles(self.scenes).entries(),
            objects=workspace.objects(),
            surface_types=workspace.surface_types(),
            actions=actions.actions,
            failed_action_modules=actions.failed_modules,
            constraint_rules=list(self.compiler.book.rules),
            plans=self.plans.summaries(),
            limits=self.limits,
            missing=workspace.missing(),
        )

    def answer_catalog(self, request: Request) -> Response:
        """
        :param request: A request for the catalog.
        :return: The catalog.
        """
        return Response.of_json(self.catalog())

    def answer_object_file(self, request: Request, path: str) -> Response:
        """
        :param request: A request for an object model's file.
        :param path: The file, relative to the workspace's object directory.
        :return: The file.
        """
        return Response.of_file(self.workspace.workspace().object_file(path))

    # %% plans

    def answer_plans(self, request: Request) -> Response:
        """
        :param request: A request for the saved plans.
        :return: The saved plans.
        """
        return Response.of_json(PlanList(plans=self.plans.summaries()))

    def answer_plan(self, request: Request, identifier: str) -> Response:
        """
        :param request: A request for one saved plan.
        :param identifier: The plan's identity.
        :return: The plan with its identity.
        """
        record = self.plans.load(identifier)
        return Response.of_json(
            replace(record, document=self.translated(record.document))
        )

    def answer_save(self, request: Request) -> Response:
        """
        Check a plan against the limits, then save it; a saved plan may still lack
        parameters a demo needs.

        :param request: A request whose body is a :class:`PlanRecord`.
        :return: The saved plan with its identity.
        """
        record = PlanRecord.from_json(self.body(request))
        record = replace(record, document=self.translated(record.document))
        PlanCheck(self.limits).check(record.document)
        return Response.of_json(self.plans.save(record))

    # %% constraints

    def answer_constraint(self, request: Request) -> Response:
        """
        :param request: A request whose body is a :class:`ConstraintText`.
        :return: The compiled constraint.
        """
        text = ConstraintText.from_json(self.body(request))
        PlanCheck(self.limits).text(PlanBuilderRoute.CONSTRAINT, text.text)
        return Response.of_json(
            self.compiler.compile(text, self.action_schema(text.step_action))
        )

    def action_schema(self, name: Optional[str]) -> Optional[ActionSchema]:
        """
        :param name: An action's class name, or None.
        :return: The schema of the workspace's action of that name, or None.
        """
        for schema in self.workspace.workspace().action_catalog().actions:
            if schema.name == name:
                return schema
        return None

    # %% demos

    def translated(self, plan: PlanDocument) -> PlanDocument:
        """
        :param plan: A plan as it was saved or sent.
        :return: The plan naming actions and robots by the catalog's identifiers; a plan
            of the planner's class names is translated through the names the catalog
            lists them as having been saved under.
        """
        return SavedNames.of_catalog(self.catalog()).translated(plan)

    def runnable(self, plan: PlanDocument) -> DemoDocument:
        """
        :param plan: A plan as a browser sent it.
        :return: What the plan's demo runs, once the plan is complete and uses only
            what the catalog offers; the catalog lists only environments the viewer
            holds, so the environment's directory is found.
        """
        plan = self.translated(plan)
        check = PlanCheck(self.limits)
        check.check(plan)
        check.complete(plan)
        CatalogCheck(self.catalog(), self.limits).check(plan)
        if plan.environment is None:
            return DemoDocument(plan=plan)
        directory = self.scenes.directory_of(plan.environment).path / plan.environment
        return DemoDocument(plan=plan, environment_directory=str(directory.resolve()))

    def answer_demo(self, request: Request) -> Response:
        """
        :param request: A request whose body is a :class:`PlanDocument`.
        :return: The demo generated from the plan, not written.
        """
        demo = self.runnable(PlanDocument.from_json(self.body(request)))
        return Response.of_json(self.template.render(demo))

    def answer_write(self, request: Request) -> Response:
        """
        :param request: A request whose body is a :class:`PlanDocument`.
        :return: Where the plan's demo was written and how to run it.
        """
        demo = self.runnable(PlanDocument.from_json(self.body(request)))
        return Response.of_json(self.demos.write(self.template.render(demo)))

    # %% runs

    def answer_run(self, request: Request) -> Response:
        """
        :param request: A request whose body is a :class:`RunRequest`.
        :return: The state of the started demo.
        """
        run = RunRequest.from_json(self.body(request))
        return Response.of_json(self.runner.start(self.runnable(run.plan), run.mode))

    def answer_run_status(self, request: Request) -> Response:
        """
        :param request: A request for the demo's state.
        :return: The state of the demo started last.
        """
        return Response.of_json(self.runner.status())

    def answer_stop(self, request: Request) -> Response:
        """
        :param request: A request to stop the demo.
        :return: The state of the stopped demo.
        """
        return Response.of_json(self.runner.stop())

    def body(self, request: Request) -> Any:
        """
        :param request: A request with a JSON body.
        :return: The decoded body, read within the document limit.
        """
        return JsonBody(request, self.limits.maximum_document_bytes).read()
