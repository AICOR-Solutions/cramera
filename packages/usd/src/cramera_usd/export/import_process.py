"""
The conversion an export runs, as a process of its own with a memory cap.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from typing_extensions import List, Mapping

from cramera_usd.commands.import_scene import ImportOption

# %% environment


class ImportEnvironment(StrEnum):
    """
    The environment variables of the conversion process.
    """

    MEMORY_LIMIT = "CRAMERA_IMPORT_MEMORY"
    """
    The largest memory the conversion may use, as systemd writes it; ``0`` for none.
    """

    MATERIAL_BINDING_CHECK = "USD_SHADE_MATERIAL_BINDING_API_CHECK"
    """
    How strictly USD wants material bindings declared; Isaac stages print thousands of
    warnings otherwise.
    """


ALLOW_MISSING_BINDING_API = "allowMissingAPI"
"""
The material binding check that accepts bindings without ``MaterialBindingAPI``.
"""

DEFAULT_MEMORY_LIMIT = "8G"
"""
The memory cap of the conversion unless the environment sets one.
"""

NO_MEMORY_LIMIT = "0"
"""
The memory cap that switches the cap off.
"""

MEMORY_CAP_PROGRAM = "systemd-run"
"""
The program that runs the conversion in a memory-capped scope.
"""


class MemoryCapArgument(StrEnum):
    """
    The arguments of :data:`MEMORY_CAP_PROGRAM` that cap the conversion's memory.
    """

    USER = "--user"
    """
    Run in the user's service manager.
    """

    SCOPE = "--scope"
    """
    Run as a scope of the calling process, in its environment.
    """

    QUIET = "-q"
    """
    Print nothing about the scope.
    """

    PROPERTY = "-p"
    """
    Set a property of the scope.
    """

    MEMORY_MAX = "MemoryMax="
    """
    The property capping the memory, followed by the limit.
    """


PYTHON_MODULE_OPTION = "-m"
"""
The Python option running a module as the program.
"""

SUCCESS = 0
"""
The exit code of a conversion that succeeded.
"""

IMPORT_MODULE = "cramera_usd.commands.import_scene"
"""
The module running the conversion.
"""

# %% arguments


@dataclass(frozen=True)
class ImportArguments:
    """
    The command line of a conversion, written back from parsed import options.
    """

    options: argparse.Namespace
    """
    The parsed import options.
    """

    def to_list(self, scenes_directory: Path) -> List[str]:
        """
        :param scenes_directory: The scenes directory the conversion writes into.
        :return: The arguments of ``cramera-import`` that convert the options' stage
            into that directory.
        """
        options = self.options
        arguments = [str(options.stage), ImportOption.NAME, options.name]
        arguments += [ImportOption.OUT, str(scenes_directory)]
        arguments += self.repeated(ImportOption.PRIM, options.prim)
        arguments += self.repeated(ImportOption.EXCLUDE, options.exclude)
        arguments += [ImportOption.ENVIRONMENT_NAME, options.environment_name]
        arguments += [ImportOption.TASK, options.task]
        arguments += self.optional(ImportOption.EXPOSURE, options.exposure)
        arguments += self.optional(
            ImportOption.CAMERA_POSITION, options.camera_position
        )
        arguments += self.optional(ImportOption.CAMERA_TARGET, options.camera_target)
        arguments += self.optional(
            ImportOption.CAMERA_FIELD_OF_VIEW, options.camera_field_of_view
        )
        arguments += self.optional(ImportOption.TRACE, options.trace)
        arguments += self.optional(
            ImportOption.FRAMES_PER_SECOND, options.frames_per_second
        )
        arguments += self.optional(ImportOption.ROBOT, options.robot)
        arguments += [ImportOption.KEEP_ROBOTS] if options.keep_robots else []
        for selection in options.variant:
            arguments += [ImportOption.VARIANT, *selection]
        arguments += self.optional(ImportOption.RECORD, options.record)
        return [str(argument) for argument in arguments]

    @staticmethod
    def repeated(option: ImportOption, values: List[str]) -> List[str]:
        """
        :param option: A repeatable option.
        :param values: Its values.
        :return: The option before each value.
        """
        return [part for value in values for part in (option, value)]

    @staticmethod
    def optional(option: ImportOption, value: object) -> List[str]:
        """
        :param option: An option.
        :param value: Its value, a list of values, or None when it was not given.
        :return: The option with its values, or nothing.
        """
        if value is None:
            return []
        values = value if isinstance(value, list) else [value]
        return [option, *(str(item) for item in values)]


# %% process


@dataclass(frozen=True)
class ImportProcess:
    """
    Runs a conversion in a process of its own, capped in memory where systemd can.
    """

    environment: Mapping[str, str]
    """
    The environment the process starts from.
    """

    def command(self, arguments: List[str]) -> List[str]:
        """
        :param arguments: The arguments of ``cramera-import``.
        :return: The command line running the conversion, under a memory cap unless
            the environment switches it off or systemd is missing.
        """
        conversion = [sys.executable, PYTHON_MODULE_OPTION, IMPORT_MODULE, *arguments]
        limit = self.environment.get(
            ImportEnvironment.MEMORY_LIMIT, DEFAULT_MEMORY_LIMIT
        )
        if limit == NO_MEMORY_LIMIT or shutil.which(MEMORY_CAP_PROGRAM) is None:
            return conversion
        return [
            MEMORY_CAP_PROGRAM,
            MemoryCapArgument.USER,
            MemoryCapArgument.SCOPE,
            MemoryCapArgument.QUIET,
            MemoryCapArgument.PROPERTY,
            f"{MemoryCapArgument.MEMORY_MAX}{limit}",
            *conversion,
        ]

    def run(self, arguments: List[str]) -> bool:
        """
        Run the conversion and wait for it; its output goes to this process's output.

        :param arguments: The arguments of ``cramera-import``.
        :return: Whether the conversion succeeded.
        """
        environment = dict(self.environment)
        environment[ImportEnvironment.MATERIAL_BINDING_CHECK] = (
            ALLOW_MISSING_BINDING_API
        )
        completed = subprocess.run(self.command(arguments), env=environment)
        return completed.returncode == SUCCESS
