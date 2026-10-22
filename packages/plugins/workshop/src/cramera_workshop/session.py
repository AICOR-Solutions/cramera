"""
The workshop session: one contact world shared by every browser, the thread that lets
its time pass, and the commands that change it, all under one lock.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace

from typing_extensions import Callable, Optional

from cramera_protocol.geometry import Pose
from cramera_protocol.workshop import (
    DriveDirection,
    WorkshopAction,
    WorkshopCommand,
    WorkshopState,
)
from cramera_workshop.exceptions import (
    InactiveReason,
    WorkshopInactive,
    WorkshopSimulationFailure,
)

WORKER_NAME = "workshop-physics"
"""
The name of the thread that lets the workshop's time pass.
"""

SHORTEST_WAIT = 0.001
"""
The shortest time the worker waits between two steps, in seconds.
"""

# %% dynamics


class WorkshopDynamics(ABC):
    """
    A contact world the session lets time pass in and sends commands to; not safe to use
    from several threads, the session serializes every call.
    """

    @abstractmethod
    def held(self) -> Optional[str]:
        """
        :return: The object key of the body the spring holds, or None.
        """

    @abstractmethod
    def grab(self, key: str) -> None:
        """
        Hold a body with the force-limited spring, at its measured pose.

        :param key: The body's object key.
        :raises UnknownWorkshopBody: When no loose body has the key.
        """

    @abstractmethod
    def move(self, key: str, pose: Pose) -> None:
        """
        Move the spring's target; the body follows as far as contacts let it.

        :param key: The held body's object key.
        :param pose: The new target; its quaternion is normalized.
        :raises NothingHeld: When the spring does not hold that body.
        :raises TargetOutsideWorkspace: When the target leaves the workshop.
        """

    @abstractmethod
    def release(self) -> None:
        """
        Let go of the held body, so gravity and contacts move it.
        """

    @abstractmethod
    def set_drawer(self, joint: str, position: float) -> None:
        """
        :param joint: A drawer joint.
        :param position: The drawer motor's new target, in metres.
        :raises UnknownDrawer: When the joint belongs to no drawer.
        :raises DrawerTargetOutOfRange: When the target is beyond the drawer's travel.
        """

    @abstractmethod
    def drive(self, direction: DriveDirection) -> None:
        """
        :param direction: Which way the held screwdriver turns.
        :raises DriverNotEngaged: When turning a driver whose blade is not engaged.
        """

    @abstractmethod
    def step(self, duration: float) -> None:
        """
        Let time pass.

        :param duration: The simulated time, in seconds.
        :raises InvalidStepDuration: When the duration is negative or too long.
        :raises WorkshopSimulationFailure: When the solver loses a valid state.
        """

    @abstractmethod
    def state(self) -> WorkshopState:
        """
        :return: The measured state; the session fills in whether time passes.
        """

    @abstractmethod
    def reset(self) -> None:
        """
        Put every body where it started and let go of everything.
        """


DynamicsFactory = Callable[[], WorkshopDynamics]
"""
Builds the contact world the first time a browser starts it.
"""

Clock = Callable[[], float]
"""
A monotonic clock in seconds; :func:`time.monotonic` outside of tests.
"""


# %% session


@dataclass
class WorkshopSession:
    """
    Owns the workshop's contact world and the worker thread that steps it; every
    command, state read and step holds :attr:`lock`.

    The world pauses and lets go of what it holds once no browser has asked for its
    state for :attr:`inactivity_timeout`.
    """

    factory: DynamicsFactory
    """
    Builds the contact world on the first start.
    """

    step_duration: float = 0.01
    """
    The simulated time the worker advances per cycle, in seconds; it waits so time
    passes as fast as on the wall clock where the solver keeps up.
    """

    inactivity_timeout: float = 90.0
    """
    How long the world runs without any browser asking for its state, in seconds.
    """

    clock: Clock = time.monotonic
    """
    The monotonic clock the inactivity is measured with.
    """

    dynamics: Optional[WorkshopDynamics] = field(default=None, init=False)
    """
    The contact world, once built.
    """

    worker: Optional[threading.Thread] = field(default=None, init=False)
    """
    The thread that lets time pass, once started.
    """

    running: bool = field(default=False, init=False)
    """
    Whether time passes.
    """

    closed: bool = field(default=False, init=False)
    """
    Whether the session was closed; a closed session takes no commands.
    """

    error: Optional[str] = field(default=None, init=False)
    """
    Why the solver stopped, until the world is reset.
    """

    lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    """
    Serializes commands, state reads and steps.
    """

    stopping: threading.Event = field(default_factory=threading.Event, init=False)
    """
    Set when the worker must end.
    """

    last_activity: float = field(default=0.0, init=False)
    """
    When a browser last asked for the state or sent a command, by :attr:`clock`.
    """

    # %% reading

    def state(self) -> WorkshopState:
        """
        :return: The measured state; asking keeps the world running.
        """
        with self.lock:
            self.last_activity = self.clock()
            return self.current_state()

    def current_state(self) -> WorkshopState:
        """
        :return: The measured state with the session's lifecycle; call with the lock.
        """
        self.notice_lost_worker()
        measured = WorkshopState() if self.dynamics is None else self.dynamics.state()
        return replace(
            measured,
            running=self.running,
            available=self.error is None and not self.closed,
            error=self.error,
        )

    def notice_lost_worker(self) -> None:
        """
        Report a worker that ended by itself while time should pass.
        """
        if self.running and self.worker is not None and not self.worker.is_alive():
            self.running = False
            self.error = WorkshopSimulationFailure().message()

    # %% commands

    def command(self, command: WorkshopCommand) -> WorkshopState:
        """
        Apply one command while no step runs.

        :param command: The command.
        :return: The state after it.
        :raises WorkshopInactive: When the session is closed, failed, or the command
            needs time to pass and it does not.
        """
        with self.lock:
            if self.closed:
                raise WorkshopInactive(InactiveReason.CLOSED)
            self.last_activity = self.clock()
            self.notice_lost_worker()
            if command.action is WorkshopAction.START:
                self.start()
            elif command.action is WorkshopAction.RESET:
                self.reset()
            elif command.action is WorkshopAction.PAUSE:
                self.pause()
            else:
                self.manipulate(command)
            return self.current_state()

    def start(self) -> None:
        """
        Build the world if needed, start the worker if needed and let time pass.

        :raises WorkshopInactive: When the solver failed and the world is not reset.
        """
        if self.error is not None:
            raise WorkshopInactive(InactiveReason.FAILED)
        if self.dynamics is None:
            self.dynamics = self.factory()
        self.running = True
        if self.worker is None:
            self.stopping.clear()
            self.worker = threading.Thread(
                target=self.run, name=WORKER_NAME, daemon=True
            )
            self.worker.start()

    def reset(self) -> None:
        """
        Build the world if needed, put every body back and clear a failure.
        """
        if self.dynamics is None:
            self.dynamics = self.factory()
        self.dynamics.reset()
        self.error = None

    def pause(self) -> None:
        """
        Stop the driver, let go of the held body and stop time.
        """
        if self.dynamics is not None and self.running:
            self.dynamics.drive(DriveDirection.STOP)
            self.dynamics.release()
        self.running = False

    def manipulate(self, command: WorkshopCommand) -> None:
        """
        :param command: A command that acts on the running world.
        :raises WorkshopInactive: When time does not pass.
        """
        if not self.running:
            raise WorkshopInactive(InactiveReason.NOT_STARTED)
        action = command.action
        if action is WorkshopAction.GRAB:
            self.dynamics.grab(command.object_key)
        elif action is WorkshopAction.MOVE:
            self.dynamics.move(command.object_key, command.pose)
        elif action is WorkshopAction.RELEASE:
            self.dynamics.release()
        elif action is WorkshopAction.DRAWER:
            self.dynamics.set_drawer(command.joint, command.position)
        elif action is WorkshopAction.DRIVE:
            self.dynamics.drive(command.direction)

    # %% stepping

    def run(self) -> None:
        """
        Step the world until the session closes, pausing it after inactivity; a solver
        failure stops time and is reported in the state.
        """
        while not self.stopping.is_set():
            started = self.clock()
            with self.lock:
                self.advance()
            elapsed = self.clock() - started
            self.stopping.wait(max(SHORTEST_WAIT, self.step_duration - elapsed))

    def advance(self) -> None:
        """
        Take one cycle's step, or pause the world after inactivity; call with the lock.
        """
        if not self.running:
            return
        if self.clock() - self.last_activity >= self.inactivity_timeout:
            self.pause()
            return
        if not self.step_or_fail():
            self.pause()

    def step_or_fail(self) -> bool:
        """
        Take one cycle's step; a solver failure is recorded rather than raised, since no
        request is waiting for it.

        :return: Whether the step succeeded.
        """
        try:
            self.dynamics.step(self.step_duration)
        except WorkshopSimulationFailure as failure:
            self.error = failure.message()
            return False
        return True

    # %% closing

    def close(self) -> None:
        """
        Stop time, end the worker and refuse further commands.
        """
        with self.lock:
            if self.closed:
                return
            self.closed = True
            self.stopping.set()
            self.pause()
            worker = self.worker
        if worker is not None and worker is not threading.current_thread():
            worker.join()
        with self.lock:
            self.worker = None
