"""
A recorded scene rebuilt as a CRAM world and moved to any frame of its recording, so a
paused replay is asked about with every class of the semantic digital twin: its robot,
arms, grippers, bodies and annotations where they were at that moment.
"""

from __future__ import annotations

import gc
import importlib
import re
import threading
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path

from typing_extensions import Any, Callable, Dict, List, Optional

from cramera.scenes import SceneCatalog
from cramera_bridge.documents import DocumentFile
from cramera_bridge.questions.desk import QuestionDesk
from cramera_bridge.questions.highlights import HighlightKeys
from cramera_bridge.questions.knowledge import QueryDomain
from cramera_bridge.questions.recorded.entities import (
    RecordedPlanNode,
    RecordedStep,
)
from cramera_bridge.questions.recorded.knowledge_base import RecordedKnowledge
from cramera_bridge.questions.recorded.paused_episode import (
    Holding,
    HoldingsUnderWay,
    PausedEpisode,
    PieceAnnotations,
    PiecesHeld,
    StepsUnderWay,
)
from cramera_bridge.questions.live import (
    SpatialValueFormat,
    WorldKnowledge,
)
from cramera_bridge.questions.workspace_classes import WorkspaceClassIndex
from cramera_bridge.scenes.bundle_world import BundleEnvironment, PoseText
from cramera_bridge.scenes.environment import SceneEnvironment
from cramera_protocol.bundle.scene import ModelDescription, PlanNodeKind
from cramera_protocol.bundle.trajectory import Trajectory
from cramera_protocol.questions import QueryAnswer, QueryRequest, QueryScope
from krrood_spatial_math.spatial_types import HomogeneousTransformationMatrix
from semantic_digital_twin.adapters.urdf import URDFParser
from semantic_digital_twin.robots.robot_parts import AbstractRobot, EndEffector
from semantic_digital_twin.semantic_annotations.semantic_annotations import (
    ShapeSortingPiece,
)
from semantic_digital_twin.specifications.robots import RobotSpecification
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.connections import (
    ActiveConnection1DOF,
    Connection6DoF,
)
from krrood.symbol_graph.symbol_graph import SymbolGraph
from semantic_digital_twin.world_description.world_entity import (
    Body,
    SemanticAnnotation,
    WorldEntity,
)

PAUSED_WORLD_TITLE = "The paused world"
"""
The title of the desk answering questions about a paused recording.
"""

NAME_SEPARATOR = "/"
"""
What separates a robot's prefix from the names of its links in a bundle's URDF.
"""


class EpisodeVariable(StrEnum):
    """
    The ready-made variables of the run on the paused world's timeline.
    """

    PIECE = "piece"
    """
    Every piece of the shape-sorting toy.
    """

    HOLDING = "holding"
    """
    Every holding of a piece by a gripper.
    """

    STEP = "step"
    """
    Every step of the run.
    """

    PLAN_NODE = "plan_node"
    """
    Every node of the executed plan.
    """

    ACTION = "action"
    """
    Every action of the executed plan.
    """

    STEP_NOW = "step_now"
    """
    The steps under way at the shown frame.
    """

    HOLDING_NOW = "holding_now"
    """
    The holdings under way at the shown frame.
    """

    HELD_PIECE = "held_piece"
    """
    The pieces held at the shown frame.
    """


# %% robot


@dataclass(frozen=True)
class RecordedRobotDescription:
    """
    The URDF a bundle recorded its robot with, read as the robot's own description: the
    bundle writes every link and joint with the robot's prefix and fixes the robot to a
    world root, which the robot's class expects neither of.
    """

    directory: Path
    """
    The bundle directory.
    """

    model: ModelDescription
    """
    The robot's model in the scene description.
    """

    prefix: str
    """
    The prefix the bundle gives the robot's names.
    """

    def text(self) -> str:
        """
        :return: The URDF without the world root and with its names unprefixed.
        """
        text = (self.directory / self.model.urdf).read_text()
        world_root_joints = re.compile(
            r'<joint name="world_root_to_[^"]*".*?</joint>', flags=re.S
        )
        text = world_root_joints.sub("", text)
        text = re.sub(r'<link name="world_root"\s*/>', "", text)
        return text.replace(f'"{self.prefix}{NAME_SEPARATOR}', '"')

    def parser(self) -> URDFParser:
        """
        :return: A parser reading the robot under its prefix, its meshes found in the
            bundle.
        """
        return URDFParser(
            urdf=self.text(),
            prefix=self.prefix,
            path_resolver=SceneEnvironment.path_resolver_of(self.directory),
        )


# %% world


@dataclass
class PausedWorld:
    """
    A recorded scene as a CRAM world, moved to one frame of its recording at a time.
    """

    world: World
    """
    The scene's world.
    """

    trajectory: Optional[Trajectory]
    """
    The recording, or None for a scene without one.
    """

    objects: Dict[str, Body]
    """
    The free objects by the key the recording names them with.
    """

    frame: Optional[int] = None
    """
    The frame the world shows, or None before it was moved to one.
    """

    episode: Optional[PausedEpisode] = None
    """
    The run's pieces, holdings, steps and plan, or None before they were read.
    """

    @classmethod
    def of_scene(
        cls,
        catalog: SceneCatalog,
        name: str,
        robot_type: type[AbstractRobot],
        recorded: RecordedKnowledge,
    ) -> PausedWorld:
        """
        :param catalog: The scenes the viewer shows.
        :param name: A bundle of the catalog.
        :param robot_type: The class of the bundle's robot.
        :param recorded: The recorded steps and plan of the bundle's run.
        :return: The bundle's world with its robot, its free objects as pieces of the
            shape-sorting toy, and the run on the same timeline.
        """
        environment = BundleEnvironment.of_scene(catalog, name)
        scene = environment.contents.scene
        robot_model = next(model for model in scene.models if model.robot)
        description = RecordedRobotDescription(
            directory=environment.directory,
            model=robot_model,
            prefix=scene.robot.prefix,
        )
        trajectory = (
            DocumentFile(environment.directory / scene.trajectory).read(Trajectory)
            if scene.trajectory is not None
            else None
        )
        world = environment.create_world(
            [
                RobotSpecification(
                    semantic_annotation_type=robot_type,
                    description_parser=description.parser(),
                    localization_pose=cls.recorded_base_pose(trajectory),
                )
            ]
        )
        objects = {
            description.key: body
            for description in scene.objects
            for body in world.bodies
            if body.name.name == description.key
        }
        cls.forget_other_worlds(world)
        paused = cls(world=world, trajectory=trajectory, objects=objects)
        pieces = PieceAnnotations(world, scene).annotate(objects)
        paused.episode = PausedEpisode.of_run(
            recorded,
            pieces,
            world.get_semantic_annotations_by_type(EndEffector),
            paused.show,
        )
        paused.show(0)
        return paused

    @staticmethod
    def recorded_base_pose(
        trajectory: Optional[Trajectory],
    ) -> Optional[HomogeneousTransformationMatrix]:
        """
        :param trajectory: The recording, or None.
        :return: Where the recording places the robot's base at its first frame, or
            None to place it at the world's origin.
        """
        if trajectory is None or not trajectory.base:
            return None
        pose = trajectory.base[0]
        return HomogeneousTransformationMatrix.from_xyz_quaternion(
            pose.x, pose.y, pose.z, pose.qx, pose.qy, pose.qz, pose.qw
        )

    @staticmethod
    def forget_other_worlds(world: World) -> None:
        """
        Drop from the symbol graph the world entities of worlds other than this one,
        such as the robot's parsed description merged into it, so a class written
        without a domain ranges over this world's entities only, once each.

        :param world: The world questions are asked about.
        """
        gc.collect()
        graph = SymbolGraph()
        graph.remove_dead_instances()
        for wrapped in list(graph.wrapped_instances):
            instance = wrapped.instance
            if isinstance(instance, WorldEntity) and instance._world is not world:
                graph.remove_node(wrapped_instance=wrapped)

    @property
    def frame_count(self) -> int:
        """
        The number of frames of the recording.
        """
        return 0 if self.trajectory is None else len(self.trajectory.frames)

    def show(self, frame: int) -> None:
        """
        Move the robot's joints and the free objects to where they were at a frame.

        :param frame: A frame of the recording; one past either end shows that end.
        """
        if self.frame_count == 0:
            return
        frame = min(max(frame, 0), self.frame_count - 1)
        if frame == self.frame:
            return
        joint_values = self.trajectory.frames[frame]
        for connection in self.world.connections:
            if not isinstance(connection, ActiveConnection1DOF):
                continue
            value = joint_values.get(str(connection.name))
            if value is not None:
                connection.position = value
        if frame < len(self.trajectory.objects):
            for key, pose in self.trajectory.objects[frame].items():
                body = self.objects.get(key)
                if body is not None and isinstance(
                    body.parent_connection, Connection6DoF
                ):
                    body.parent_connection.origin = PoseText(pose).native(
                        self.world.root
                    )
        self.frame = frame

    def shown_frame(self) -> int:
        """
        :return: The frame the world shows.
        """
        return self.frame or 0

    def free_objects(self) -> List[Body]:
        """
        :return: The free objects.
        """
        return list(self.objects.values())


# %% presentation


@dataclass(frozen=True)
class PausedWorldHighlightKeys(HighlightKeys):
    """
    Lights up a body under the name the bundle gives it, and an annotation through its
    bodies.
    """

    def keys_of(self, value: Any) -> List[str]:
        if isinstance(value, Body):
            return [str(value.name)]
        if isinstance(value, Holding):
            return self.keys_of(value.gripper) + self.keys_of(value.piece)
        if isinstance(value, RecordedStep) and value.picks is not None:
            return [value.picks.key]
        if isinstance(value, SemanticAnnotation):
            return [key for body in self.own_bodies(value) for key in self.keys_of(body)]
        return []

    @staticmethod
    def own_bodies(annotation: SemanticAnnotation) -> List[Body]:
        """
        :param annotation: A semantic annotation.
        :return: Its bodies; a part of a robot leaves out the robot's root and, for a
            kinematic chain such as an arm, the body it is mounted on, which it starts
            from but which is not part of it.
        """
        bodies = list(annotation.bodies)
        if isinstance(annotation, AbstractRobot) or annotation._world is None:
            return bodies
        robot_roots = {
            robot.root.id
            for robot in annotation._world.get_semantic_annotations_by_type(
                AbstractRobot
            )
        }
        chain_root = getattr(annotation, "root", None) if hasattr(annotation, "tip") else None
        if chain_root is not None:
            robot_roots.add(chain_root.id)
        own = [body for body in bodies if body.id not in robot_roots]
        return own or bodies


# %% desk


@dataclass
class PausedWorldDesk:
    """
    Answers questions about a recorded scene at the frame the viewer shows.
    """

    paused: PausedWorld
    """
    The scene's world.
    """

    class_index: WorkspaceClassIndex = field(default_factory=WorkspaceClassIndex)
    """
    The workspace classes a query may name.
    """

    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    """
    Keeps one question at a time moving the world.
    """

    desk: QuestionDesk = field(init=False)
    """
    The desk over the world.
    """

    def __post_init__(self) -> None:
        world_knowledge = WorldKnowledge(
            self.paused.world, self.paused.free_objects
        ).knowledge()
        self.desk = QuestionDesk(
            title=PAUSED_WORLD_TITLE,
            knowledge=[
                replace(
                    world_knowledge,
                    scope=QueryScope.PAUSED_WORLD,
                    domains=world_knowledge.domains + self.episode_domains(),
                    extra_names={
                        **world_knowledge.extra_names,
                        Holding.__name__: Holding,
                        RecordedStep.__name__: RecordedStep,
                        RecordedPlanNode.__name__: RecordedPlanNode,
                        PlanNodeKind.__name__: PlanNodeKind,
                    },
                )
            ],
            presets=[],
            highlight_keys=PausedWorldHighlightKeys(),
            class_index=self.class_index,
            value_formats=[SpatialValueFormat()],
        )

    def episode_domains(self) -> List[QueryDomain]:
        """
        :return: The run's pieces, holdings, steps, plan and actions, and those under
            way at the shown frame.
        """
        episode = self.paused.episode
        frame = self.paused.shown_frame
        return [
            QueryDomain(
                EpisodeVariable.PIECE,
                ShapeSortingPiece,
                list(episode.pieces.values()),
            ),
            QueryDomain(EpisodeVariable.HOLDING, Holding, episode.holdings),
            QueryDomain(EpisodeVariable.STEP, RecordedStep, episode.recorded.steps),
            QueryDomain(
                EpisodeVariable.PLAN_NODE, RecordedPlanNode, episode.recorded.plan_nodes
            ),
            QueryDomain(EpisodeVariable.ACTION, RecordedPlanNode, episode.actions()),
            QueryDomain(
                EpisodeVariable.STEP_NOW, RecordedStep, StepsUnderWay(episode, frame)
            ),
            QueryDomain(
                EpisodeVariable.HOLDING_NOW, Holding, HoldingsUnderWay(episode, frame)
            ),
            QueryDomain(
                EpisodeVariable.HELD_PIECE, ShapeSortingPiece, PiecesHeld(episode, frame)
            ),
        ]

    def answer_query(self, request: QueryRequest) -> QueryAnswer:
        """
        :param request: A query and the frame it is asked at.
        :return: Its answer about the world at that frame.
        """
        with self.lock:
            self.paused.show(request.frame or 0)
            return self.desk.answer_query(request)


# %% scenes


ROBOT_MODULE = "semantic_digital_twin.robots"
"""
The package holding a module per robot class, named as the robot.
"""


@dataclass(frozen=True)
class RobotClassName:
    """
    The robot class a bundle's robot name stands for.
    """

    name: str
    """
    The robot's name in the bundle.
    """

    def robot_class(self) -> Optional[type[AbstractRobot]]:
        """
        :return: The robot class of CRAM's module of that name, or None when CRAM has
            none.
        """
        try:
            module = importlib.import_module(f"{ROBOT_MODULE}.{self.name.lower()}")
        except ModuleNotFoundError:
            return None
        return next(
            (
                candidate
                for candidate in vars(module).values()
                if isinstance(candidate, type)
                and issubclass(candidate, AbstractRobot)
                and candidate.__name__.lower() == self.name.lower()
            ),
            None,
        )


@dataclass
class PausedWorldDesks:
    """
    The paused-world desk of each scene, built once on first use and warmed up in the
    background so the first question does not wait for it.
    """

    catalog: SceneCatalog
    """
    The scenes the viewer shows.
    """

    class_index: WorkspaceClassIndex
    """
    The workspace classes a query may name.
    """

    recorded_of: Callable[[str], RecordedKnowledge]
    """
    Answers the recorded steps and plan of a scene, shared with the recorded scene's
    own questions so each step is one entity.
    """

    built: Dict[str, PausedWorldDesk] = field(default_factory=dict)
    """
    The desk of each scene built so far.
    """

    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    """
    Builds each scene's desk once.
    """

    def robot_class_of(self, scene: str) -> Optional[type[AbstractRobot]]:
        """
        :param scene: A bundle name.
        :return: The class of its robot, or None when it has none CRAM knows.
        """
        environment = BundleEnvironment.of_scene(self.catalog, scene)
        robot = environment.contents.scene.robot
        return None if robot is None else RobotClassName(robot.name).robot_class()

    def offers(self, scene: str) -> bool:
        """
        :param scene: A bundle name.
        :return: Whether the scene can be rebuilt as a world.
        """
        return self.robot_class_of(scene) is not None

    def warm_up(self, scene: str) -> None:
        """
        Build the scene's desk in the background.

        :param scene: A bundle name.
        """
        threading.Thread(target=self.of_scene, args=(scene,), daemon=True).start()

    def of_scene(self, scene: str) -> PausedWorldDesk:
        """
        :param scene: A bundle name.
        :return: The scene's desk.
        """
        with self.lock:
            desk = self.built.get(scene)
            if desk is None:
                paused = PausedWorld.of_scene(
                    self.catalog,
                    scene,
                    self.robot_class_of(scene),
                    self.recorded_of(scene),
                )
                desk = PausedWorldDesk(paused=paused, class_index=self.class_index)
                self.built[scene] = desk
            return desk
