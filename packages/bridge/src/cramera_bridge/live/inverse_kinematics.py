"""
Inverse kinematics of one arm chain for hand control: damped least squares steps on
the chain's compiled forward kinematics, within the joints' position limits.

semantic_digital_twin dropped its inverse kinematics solver, so hand control solves the
small steps it needs here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy
from typing_extensions import TYPE_CHECKING, Dict, List, Optional

from krrood.symbolic_math.symbolic_math import (
    CompiledFunction,
    Matrix,
    VariableParameters,
)

if TYPE_CHECKING:
    from semantic_digital_twin.world import World
    from semantic_digital_twin.world_description.degree_of_freedom import (
        DegreeOfFreedom,
    )
    from semantic_digital_twin.world_description.world_entity import (
        KinematicStructureEntity,
    )

DAMPING = 0.003
"""
The damping of the least squares steps, which keeps steps near a singular pose finite;
low, since an outstretched arm must still move along its weak direction.
"""

POSITION_TOLERANCE_METRES = 1e-3
"""
How near the tip must come to the target position for a solution.
"""

ROTATION_TOLERANCE_RADIANS = 1e-2
"""
How near the tip must come to the target orientation for a solution.
"""

MAXIMUM_JOINT_STEP = 0.2
"""
The largest change of one joint value per iteration, in radians or metres.
"""


@dataclass
class ChainInverseKinematics:
    """
    The inverse kinematics of the chain from a root to a tip.
    """

    world: World
    """
    The world the chain belongs to.
    """

    root: KinematicStructureEntity
    """
    The frame targets are given in.
    """

    tip: KinematicStructureEntity
    """
    The frame that is moved to the target.
    """

    degrees_of_freedom: List[DegreeOfFreedom] = field(init=False)
    """
    The degrees of freedom that move the tip, in a fixed order.
    """

    other_degrees_of_freedom: List[DegreeOfFreedom] = field(init=False)
    """
    The other degrees of freedom the chain's pose depends on, held at their values.
    """

    pose_function: CompiledFunction = field(init=False)
    """
    The tip's pose in the root frame, as position and rotation matrix entries.
    """

    jacobian_function: CompiledFunction = field(init=False)
    """
    The derivative of :attr:`pose_function` by the moving degrees of freedom.
    """

    def __post_init__(self) -> None:
        upwards, downwards = self.world.compute_split_chain_of_connections(
            self.root, self.tip
        )
        moving = set()
        held = set()
        for connection in upwards + downwards:
            moving.update(connection.active_dofs)
            held.update(connection.passive_dofs)
        self.degrees_of_freedom = sorted(moving, key=lambda dof: str(dof.id))
        self.other_degrees_of_freedom = sorted(held, key=lambda dof: str(dof.id))
        root_T_tip = self.world.compose_forward_kinematics_expression(
            self.root, self.tip
        )
        entries = Matrix(
            [root_T_tip[row, column] for column in (3, 0, 1, 2) for row in range(3)]
        )
        variables = [dof.variables.position for dof in self.degrees_of_freedom]
        parameters = VariableParameters.from_lists(
            variables,
            [dof.variables.position for dof in self.other_degrees_of_freedom],
        )
        self.pose_function = entries.compile(parameters=parameters)
        self.jacobian_function = entries.jacobian(variables=variables).compile(
            parameters=parameters
        )

    def solve(
        self, target: numpy.ndarray, maximum_iterations: int
    ) -> Optional[Dict[DegreeOfFreedom, float]]:
        """
        :param target: The tip's target pose in the root frame, as a 4x4 matrix.
        :param maximum_iterations: The steps one solve may take.
        :return: Values of the moving degrees of freedom that bring the tip to the
            target, or None when the steps do not get there, as for an unreachable
            target; the world's state is not changed.
        """
        values = numpy.array(
            [self.world.state[dof.id].position for dof in self.degrees_of_freedom],
            dtype=float,
        )
        held = numpy.array(
            [
                self.world.state[dof.id].position
                for dof in self.other_degrees_of_freedom
            ],
            dtype=float,
        )
        lower, upper = self.position_limits()
        for _ in range(maximum_iterations):
            error, jacobian = self.error_and_jacobian(target, values, held)
            if (
                numpy.linalg.norm(error[:3]) <= POSITION_TOLERANCE_METRES
                and numpy.linalg.norm(error[3:]) <= ROTATION_TOLERANCE_RADIANS
            ):
                return dict(zip(self.degrees_of_freedom, values.tolist()))
            step = self.step_within_limits(jacobian, error, values, lower, upper)
            values = numpy.clip(values + step, lower, upper)
        return None

    @staticmethod
    def step_within_limits(
        jacobian: numpy.ndarray,
        error: numpy.ndarray,
        values: numpy.ndarray,
        lower: numpy.ndarray,
        upper: numpy.ndarray,
    ) -> numpy.ndarray:
        """
        :param jacobian: The geometric Jacobian at the values.
        :param error: The tip's position and rotation error.
        :param values: The values of the moving degrees of freedom.
        :param lower: Their lower position limits.
        :param upper: Their upper position limits.
        :return: A damped least squares step that reduces the error; a degree of
            freedom the step would push past the limit it stands at is held, and the
            others make up for it.
        """
        free = numpy.ones(len(values), dtype=bool)
        step = numpy.zeros(len(values))
        for _ in range(len(values)):
            columns = jacobian[:, free]
            step = numpy.zeros(len(values))
            step[free] = columns.T @ numpy.linalg.solve(
                columns @ columns.T + DAMPING**2 * numpy.eye(len(error)), error
            )
            blocked = free & (
                ((values <= lower) & (step < 0)) | ((values >= upper) & (step > 0))
            )
            if not blocked.any():
                break
            free &= ~blocked
        return numpy.clip(step, -MAXIMUM_JOINT_STEP, MAXIMUM_JOINT_STEP)

    def position_limits(self) -> tuple[numpy.ndarray, numpy.ndarray]:
        """
        :return: The lower and upper position limits of the moving degrees of freedom,
            infinite where a degree of freedom has none.
        """
        lower = []
        upper = []
        for dof in self.degrees_of_freedom:
            lower_limit = dof.limits.lower.position
            upper_limit = dof.limits.upper.position
            lower.append(-numpy.inf if lower_limit is None else float(lower_limit))
            upper.append(numpy.inf if upper_limit is None else float(upper_limit))
        return numpy.array(lower), numpy.array(upper)

    def error_and_jacobian(
        self, target: numpy.ndarray, values: numpy.ndarray, held: numpy.ndarray
    ) -> tuple[numpy.ndarray, numpy.ndarray]:
        """
        :param target: The tip's target pose in the root frame.
        :param values: The values of the moving degrees of freedom.
        :param held: The values of the other degrees of freedom.
        :return: The position and rotation error of the tip, and the geometric
            Jacobian that maps steps of the moving degrees of freedom to tip motion.
        """
        entries = numpy.asarray(self.pose_function(values, held)).reshape(-1)
        derivatives = numpy.asarray(self.jacobian_function(values, held)).reshape(
            12, -1
        )
        position = entries[:3]
        rotation = entries[3:].reshape(3, 3).T
        target_rotation = target[:3, :3]
        rotation_error = 0.5 * sum(
            numpy.cross(rotation[:, column], target_rotation[:, column])
            for column in range(3)
        )
        error = numpy.concatenate([target[:3, 3] - position, rotation_error])
        angular = []
        for derivative in derivatives.T:
            spin = derivative[3:].reshape(3, 3).T @ rotation.T
            angular.append([spin[2, 1], spin[0, 2], spin[1, 0]])
        jacobian = numpy.vstack([derivatives[:3], numpy.array(angular).T])
        return error, jacobian
