"""
A MuJoCo composite cable in a CRAM world: rigid capsules joined by ball joints with
MuJoCo's elastic cable plugin, and one semantic body per capsule that follows it.

The semantic points have free connections below the world's root and receive the
capsules' measured poses; they add no second physical body, and nothing ever moves a
capsule from the semantic side.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from enum import StrEnum

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
from typing_extensions import List, Tuple

from cramera_cable_lab.exceptions import CableNotBuilt, CablePrefixTaken
from cramera_protocol.cable_lab import CableConfiguration
from semantic_digital_twin.adapters.multi_sim import MujocoBuilder, MujocoSynchronizer
from semantic_digital_twin.datastructures.prefixed_name import PrefixedName
from semantic_digital_twin.mixin import SimulatorAdditionalProperty
from semantic_digital_twin.spatial_types import HomogeneousTransformationMatrix
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.connections import Connection6DoF
from semantic_digital_twin.world_description.world_entity import Body, Connection

# %% names


class CableName(StrEnum):
    """
    The names model generation and the semantic points share.
    """

    PREFIX = "cable_segment_"
    """
    The prefix of the semantic points and the capsules.
    """

    BODY_INFIX = "B"
    """
    What follows the prefix in a capsule's body name, before its index.
    """

    PLUGIN = "mujoco.elasticity.cable"
    """
    MuJoCo's bending and twisting plugin.
    """


class CompositeXml(StrEnum):
    """
    The MuJoCo XML elements and values of the composite cable.
    """

    ROOT = "mujoco"
    """
    The document's root.
    """

    EXTENSION = "extension"
    """
    The plugins the model uses.
    """

    PLUGIN = "plugin"
    """
    A plugin.
    """

    WORLD_BODY = "worldbody"
    """
    The world's bodies.
    """

    COMPOSITE = "composite"
    """
    MuJoCo's macro that expands into the cable's bodies.
    """

    CONFIG = "config"
    """
    A plugin setting.
    """

    GEOM = "geom"
    """
    The capsules' shape.
    """

    CABLE = "cable"
    """
    The composite type of a cable.
    """

    CAPSULE = "capsule"
    """
    The capsules' geom type.
    """

    S_CURVE = "s"
    """
    A straight cable along its first axis.
    """

    BALL = "ball"
    """
    A first point pinned by a ball joint.
    """

    FREE = "free"
    """
    A loose first point.
    """

    BEND = "bend"
    """
    The bending modulus setting.
    """

    TWIST = "twist"
    """
    The twisting modulus setting.
    """

    MAXIMUM_STRESS = "vmax"
    """
    The plugin's stress colouring limit, off.
    """


NO_STRESS_COLOURING = 0
"""
The plugin's stress colouring limit that turns it off.
"""

# %% points


@dataclass
class CablePoint(SimulatorAdditionalProperty):
    """
    Marks a semantic body that only follows a capsule, so the world's MuJoCo model
    leaves it out.
    """


@dataclass(frozen=True)
class CableCompilation:
    """
    A scene with the cable built in.
    """

    specification: mujoco.MjSpec
    """
    The specification the model was compiled from.
    """

    model: mujoco.MjModel
    """
    The compiled model.
    """

    data: mujoco.MjData
    """
    Its state, carried over from the scene without the cable.
    """


# %% cable


@dataclass
class Cable(SimulatorAdditionalProperty):
    """
    A composite cable and the semantic points that follow its capsules.
    """

    world: World
    """
    The world holding the points.
    """

    configuration: CableConfiguration
    """
    The cable's geometry, mechanics and placement.
    """

    parent: Body
    """
    The body the cable's anchor frame is fixed to.
    """

    prefix: str = CableName.PREFIX
    """
    The prefix of the points' and capsules' names.
    """

    points: Tuple[Body, ...] = field(default=(), init=False)
    """
    The semantic points, one per capsule.
    """

    connections: Tuple[Connection6DoF, ...] = field(default=(), init=False)
    """
    The points' free connections below the world's root.
    """

    root_T_anchor: np.ndarray = field(default_factory=lambda: np.eye(4), init=False)
    """
    The anchor frame in the world's root frame.
    """

    installed: bool = field(default=False, init=False)
    """
    Whether the capsules were built into a MuJoCo scene.
    """

    def __post_init__(self) -> None:
        taken = {body.name.name for body in self.world.bodies}
        if any(name in taken for name in self.point_names()):
            raise CablePrefixTaken(self.prefix)
        configuration = self.configuration
        root_T_parent = self.world.compute_forward_kinematics_np(
            self.world.root, self.parent
        )
        parent_T_anchor = HomogeneousTransformationMatrix.from_xyz_rpy(
            *configuration.anchor_offset.to_json(),
            *configuration.anchor_rotation.to_json(),
        ).to_np()
        self.root_T_anchor = root_T_parent @ parent_T_anchor
        points: List[Body] = []
        connections: List[Connection6DoF] = []
        with self.world.modify_world():
            for name in self.point_names():
                point = Body(
                    name=PrefixedName(name),
                    simulator_additional_properties=[CablePoint()],
                )
                self.world.add_kinematic_structure_entity(point)
                connection = Connection6DoF.create_with_dofs(
                    self.world, self.world.root, point
                )
                self.world.add_connection(connection)
                points.append(point)
                connections.append(connection)
        self.points = tuple(points)
        self.connections = tuple(connections)
        with self.world.batch_state_changes():
            direction = self.root_T_anchor[:3, 0]
            for index, connection in enumerate(self.connections):
                position = (
                    self.root_T_anchor[:3, 3]
                    + direction * index * configuration.segment_length
                )
                self.place(
                    connection,
                    position,
                    Rotation.from_matrix(self.root_T_anchor[:3, :3]).as_quat(),
                )
        self.world.notify_state_change()
        self.world.simulator_additional_properties.append(self)

    def point_names(self) -> List[str]:
        """
        :return: The semantic points' names.
        """
        return [
            f"{self.prefix}{index}" for index in range(self.configuration.segment_count)
        ]

    def body_names(self) -> List[str]:
        """
        :return: The capsules' body names in MuJoCo.
        """
        return [
            f"{self.prefix}{CableName.BODY_INFIX}{index}"
            for index in range(self.configuration.segment_count)
        ]

    def place(
        self, connection: Connection6DoF, position: np.ndarray, quaternion: np.ndarray
    ) -> None:
        """
        :param connection: A point's free connection.
        :param position: The point's position in the world's root frame.
        :param quaternion: Its orientation, scalar last.
        """
        degrees = (
            connection.x,
            connection.y,
            connection.z,
            connection.qx,
            connection.qy,
            connection.qz,
            connection.qw,
        )
        for degree, value in zip(degrees, (*position, *quaternion)):
            self.world.state[degree.id].position = float(value)

    def follow(self, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        """
        Put the capsules' measured poses on the semantic points.

        :param model: The compiled scene with the cable.
        :param data: Its state.
        """
        if not self.installed:
            return
        with self.world.batch_state_changes(publish_changes=False):
            for connection, name in zip(self.connections, self.body_names()):
                body = model.body(name).id
                self.place(connection, data.xpos[body], np.roll(data.xquat[body], -1))
        self.world.notify_state_change()

    # %% building

    def composite(self) -> mujoco.MjSpec:
        """
        :return: MuJoCo's composite cable expanded into its capsules, with the capsules
            renamed to :meth:`body_names`.
        """
        configuration = self.configuration
        root = ElementTree.Element(CompositeXml.ROOT)
        extension = ElementTree.SubElement(root, CompositeXml.EXTENSION)
        ElementTree.SubElement(extension, CompositeXml.PLUGIN, plugin=CableName.PLUGIN)
        world = ElementTree.SubElement(root, CompositeXml.WORLD_BODY)
        composite = ElementTree.SubElement(
            world,
            CompositeXml.COMPOSITE,
            type=CompositeXml.CABLE,
            prefix=self.prefix,
            count=f"{configuration.segment_count + 1} 1 1",
            curve=CompositeXml.S_CURVE,
            size=str(configuration.length()),
            initial=CompositeXml.BALL if configuration.anchored else CompositeXml.FREE,
        )
        plugin = ElementTree.SubElement(
            composite, CompositeXml.PLUGIN, plugin=CableName.PLUGIN
        )
        for key, value in (
            (CompositeXml.BEND, configuration.bend),
            (CompositeXml.TWIST, configuration.twist),
            (CompositeXml.MAXIMUM_STRESS, NO_STRESS_COLOURING),
        ):
            ElementTree.SubElement(
                plugin, CompositeXml.CONFIG, key=key, value=str(value)
            )
        ElementTree.SubElement(
            composite,
            CompositeXml.GEOM,
            type=CompositeXml.CAPSULE,
            size=str(configuration.radius),
            mass=str(configuration.mass / configuration.segment_count),
            rgba=numbers(configuration.color.to_json()),
            friction=numbers(configuration.friction.to_json()),
            condim=str(configuration.contact_dimension),
            solref=numbers(configuration.solver_reference.to_json()),
            solimp=numbers(configuration.solver_impedance.to_json()),
        )
        native = mujoco.MjSpec.from_string(
            ElementTree.tostring(root, encoding="unicode")
        )
        renamed = {}
        for body, name in zip(native.bodies[1:], self.body_names()):
            renamed[body.name] = name
            body.name = name
        for exclusion in native.excludes:
            exclusion.bodyname1 = renamed[exclusion.bodyname1]
            exclusion.bodyname2 = renamed[exclusion.bodyname2]
        return native

    def install(
        self, specification: mujoco.MjSpec, model: mujoco.MjModel, data: mujoco.MjData
    ) -> CableCompilation:
        """
        Build the capsules into a copy of a scene, pinned to the parent's body or loose
        at the anchor, keeping the scene's state.

        :param specification: The scene's specification.
        :param model: The scene's compiled model.
        :param data: The scene's state.
        :return: The scene with the cable.
        :raises CableNotBuilt: When MuJoCo cannot build or compile the cable.
        """
        candidate = specification.copy()
        parent = candidate.worldbody
        frame_T_anchor = self.root_T_anchor
        if self.configuration.anchored:
            parent = candidate.body(self.parent.name.name)
            root_T_parent = self.world.compute_forward_kinematics_np(
                self.world.root, self.parent
            )
            frame_T_anchor = np.linalg.inv(root_T_parent) @ self.root_T_anchor
        frame = parent.add_frame(
            pos=frame_T_anchor[:3, 3],
            quat=Rotation.from_matrix(frame_T_anchor[:3, :3]).as_quat(
                scalar_first=True
            ),
        )
        compiled = MujocoCompilation(candidate, model, data).compile(
            self.composite(), frame
        )
        self.installed = True
        self.follow(compiled.model, compiled.data)
        return compiled


def numbers(values: List[float]) -> str:
    """
    :param values: Numbers.
    :return: Them as one XML attribute value.
    """
    return " ".join(str(float(value)) for value in values)


@dataclass(frozen=True)
class MujocoCompilation:
    """
    Attaches the cable to a scene's specification, recompiles it and carries the
    previous scene's state over.
    """

    specification: mujoco.MjSpec
    """
    The scene's specification, extended by the cable.
    """

    previous_model: mujoco.MjModel
    """
    The scene's model before the extension.
    """

    previous_data: mujoco.MjData
    """
    The scene's state before the extension.
    """

    def compile(
        self, composite: mujoco.MjSpec, frame: mujoco.MjsFrame
    ) -> CableCompilation:
        """
        :param composite: The cable's expanded specification.
        :param frame: The frame of the specification the cable is attached to.
        :return: The compiled scene with the cable and the previous state.
        :raises CableNotBuilt: When MuJoCo cannot attach or compile the cable.
        """
        # MuJoCo reports a specification it cannot attach or compile only by raising
        try:
            self.specification.attach(composite, prefix="", frame=frame)
            model, data = self.specification.recompile(
                self.previous_model, self.previous_data
            )
        except ValueError as error:
            raise CableNotBuilt(str(error)) from error
        mujoco.mj_resetData(model, data)
        SceneState(self.previous_model, self.previous_data).copy_to(model, data)
        mujoco.mj_forward(model, data)
        return CableCompilation(self.specification, model, data)


@dataclass(frozen=True)
class SceneState:
    """
    The joints, equalities, actuators and applied forces of a compiled scene, found by
    name in another compilation of it.
    """

    model: mujoco.MjModel
    """
    The scene's model.
    """

    data: mujoco.MjData
    """
    Its state.
    """

    def copy_to(self, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        """
        :param model: A compilation that holds every named element of the scene.
        :param data: Its state, receiving the scene's.
        """
        self.copy_joints(model, data)
        for index in range(self.model.neq):
            target = model.equality(self.model.equality(index).name).id
            data.eq_active[target] = self.data.eq_active[index]
        for index in range(self.model.nu):
            target = model.actuator(self.model.actuator(index).name).id
            data.ctrl[target] = self.data.ctrl[index]
            count = self.model.actuator_actnum[index]
            start = self.model.actuator_actadr[index]
            target_start = model.actuator_actadr[target]
            data.act[target_start : target_start + count] = self.data.act[
                start : start + count
            ]
        for index in range(self.model.nbody):
            target = model.body(self.model.body(index).name).id
            data.xfrc_applied[target] = self.data.xfrc_applied[index]
            mocap = self.model.body_mocapid[index]
            if mocap >= 0:
                target_mocap = model.body_mocapid[target]
                data.mocap_pos[target_mocap] = self.data.mocap_pos[mocap]
                data.mocap_quat[target_mocap] = self.data.mocap_quat[mocap]
        data.time = self.data.time

    def copy_joints(self, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        """
        :param model: The other compilation.
        :param data: Its state, receiving the joints' positions, velocities and forces.
        """
        for index in range(self.model.njnt):
            target = model.joint(self.model.joint(index).name).id
            positions = self.span(index, self.model.jnt_qposadr, self.model.nq)
            velocities = self.span(index, self.model.jnt_dofadr, self.model.nv)
            position_start = model.jnt_qposadr[target]
            velocity_start = model.jnt_dofadr[target]
            position_count = positions.stop - positions.start
            velocity_count = velocities.stop - velocities.start
            data.qpos[position_start : position_start + position_count] = (
                self.data.qpos[positions]
            )
            data.qvel[velocity_start : velocity_start + velocity_count] = (
                self.data.qvel[velocities]
            )
            data.qfrc_applied[velocity_start : velocity_start + velocity_count] = (
                self.data.qfrc_applied[velocities]
            )

    def span(self, joint: int, addresses: np.ndarray, size: int) -> slice:
        """
        :param joint: A joint's index.
        :param addresses: Where each joint's numbers start.
        :param size: How many numbers there are.
        :return: The joint's numbers, as a slice with a start and a stop.
        """
        end = addresses[joint + 1] if joint + 1 < self.model.njnt else size
        return slice(int(addresses[joint]), int(end))


# %% world model and synchronization


def is_point(body: Body) -> bool:
    """
    :param body: A body.
    :return: Whether it is a semantic cable point.
    """
    return any(
        isinstance(property, CablePoint)
        for property in body.simulator_additional_properties
    )


@dataclass
class CableMujocoBuilder(MujocoBuilder):
    """
    Builds the world's MuJoCo model without the semantic cable points.
    """

    def build_body(self, body: Body) -> None:
        if not is_point(body):
            super().build_body(body)

    def _build_connection(self, connection: Connection) -> None:
        if not is_point(connection.child):
            super()._build_connection(connection)

    def _end_build(self, file_path: str) -> None:
        super()._end_build(file_path)
        HomeKeyframe(self).write(file_path)
        for property in self.world.simulator_additional_properties:
            if isinstance(property, Cable):
                property.connections = tuple(
                    point.parent_connection for point in property.points
                )


@dataclass(frozen=True)
class HomeKeyframe:
    """
    The model file's initial keyframe, written for the joints left after the points were
    left out.
    """

    builder: CableMujocoBuilder
    """
    The builder that wrote the model file.
    """

    def write(self, file_path: str) -> None:
        """
        :param file_path: The model file.
        """
        world = self.builder.world
        tree = ElementTree.parse(file_path)
        model = self.builder.spec.compile()
        positions = model.qpos0.copy()
        for body in world.bodies:
            connection = body.parent_connection
            if (
                is_point(body)
                or connection is None
                or isinstance(connection, self.builder._ignore_connection_types)
            ):
                continue
            joint = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_JOINT, connection.name.name
            )
            if joint < 0:
                continue
            address = model.jnt_qposadr[joint]
            if isinstance(connection, Connection6DoF):
                root_T_body = world.compute_forward_kinematics_np(world.root, body)
                positions[address : address + 3] = root_T_body[:3, 3]
                positions[address + 3 : address + 7] = Rotation.from_matrix(
                    root_T_body[:3, :3]
                ).as_quat(scalar_first=True)
                continue
            coordinates = [
                world.state[degree.id].position
                for degree in connection.active_dofs + connection.passive_dofs
            ]
            positions[address : address + len(coordinates)] = coordinates
        key = tree.find("keyframe/key")
        key.set("qpos", numbers(positions.tolist()))
        tree.write(file_path, encoding="utf-8", xml_declaration=True)


@dataclass(eq=False)
class CableMujocoSynchronizer(MujocoSynchronizer):
    """
    Puts the capsules' measured poses on the semantic points whenever the world's
    degrees of freedom are synchronized, without echoing them back to MuJoCo.
    """

    def _sim_to_world(self) -> None:
        previous_time = self._last_sync_time
        super()._sim_to_world()
        if self._last_sync_time == previous_time:
            return
        self._state_callback.pause()
        for property in self._world.simulator_additional_properties:
            if isinstance(property, Cable):
                property.follow(self.simulator._mj_model, self.simulator._mj_data)
        self._state_callback.update_previous_world_state()
        self._state_callback.resume()
