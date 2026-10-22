"""
Copy the browser libraries the viewer imports into its web directory: the pinned npm
releases are downloaded, checked against the registry's integrity hash, and only the
modules the viewer names, with every module they import, are kept.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import shutil
import sys
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from typing_extensions import Dict, List, Sequence, Set, Tuple

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
"""
The repository root.
"""

VENDOR_DIRECTORY = REPOSITORY_ROOT / "packages/viewer/src/cramera/web/vendor"
"""
Where the vendored libraries go.
"""

REGISTRY = "https://registry.npmjs.org"
"""
The npm registry the releases are downloaded from.
"""

IMPORT_PATTERN = re.compile(
    r"""(?:import|export)\s[^'"]*?from\s*['"]([^'"]+)['"]|import\s*['"]([^'"]+)['"]"""
)
"""
Finds the module specifiers of static ``import`` and ``export ... from`` statements.
"""

PACKAGE_PREFIX = "package/"
"""
The directory npm tarballs keep their files in.
"""

LICENCE_FILE = "LICENSE"
"""
The file holding a package's licence text.
"""


# %% packages


@dataclass(frozen=True)
class VendoredPackage:
    """
    One npm release and the modules the viewer imports from it.
    """

    name: str
    """
    The npm package name.
    """

    version: str
    """
    The exact release.
    """

    entry_modules: Tuple[str, ...]
    """
    The modules the viewer imports, relative to the package root.
    """

    extra_files: Tuple[str, ...] = (LICENCE_FILE, "package.json")
    """
    Further files to keep, such as the licence.
    """

    licence_url: str = ""
    """
    Where to fetch the licence text when the release does not ship it, empty when
    it does.
    """

    def download(self) -> Dict[str, bytes]:
        """
        :return: The release's files by path relative to the package root, after the
            tarball matched the registry's integrity hash.
        :raises ValueError: When the tarball does not match.
        """
        with urllib.request.urlopen(f"{REGISTRY}/{self.name}/{self.version}") as answer:
            metadata = json.loads(answer.read())
        distribution = metadata["dist"]
        with urllib.request.urlopen(distribution["tarball"]) as answer:
            tarball = answer.read()
        algorithm, expected = distribution["integrity"].split("-", 1)
        actual = base64.b64encode(hashlib.new(algorithm, tarball).digest()).decode()
        if actual != expected:
            raise ValueError(
                f"{self.name}@{self.version} does not match its integrity hash"
            )
        files: Dict[str, bytes] = {}
        with tarfile.open(fileobj=io.BytesIO(tarball)) as archive:
            for member in archive.getmembers():
                if member.isfile() and member.name.startswith(PACKAGE_PREFIX):
                    files[member.name[len(PACKAGE_PREFIX) :]] = archive.extractfile(
                        member
                    ).read()
        return files

    def needed_modules(self, files: Dict[str, bytes]) -> List[str]:
        """
        :param files: The release's files.
        :return: The entry modules and every module of the package they import.
        """
        needed: Set[str] = set()
        pending = list(self.entry_modules)
        while pending:
            module = pending.pop()
            if module in needed:
                continue
            needed.add(module)
            source = files[module].decode("utf-8")
            for match in IMPORT_PATTERN.finditer(source):
                specifier = match.group(1) or match.group(2)
                if specifier.startswith("."):
                    pending.append(
                        str(PurePosixPath(module).parent.joinpath(specifier)).replace(
                            "/./", "/"
                        )
                    )
                    pending[-1] = self.normalised(pending[-1])
        return sorted(needed)

    @staticmethod
    def normalised(path: str) -> str:
        """
        :param path: A relative module path that may contain ``..``.
        :return: The path without ``..`` and ``.`` segments.
        """
        parts: List[str] = []
        for part in path.split("/"):
            if part == "..":
                parts.pop()
            elif part not in ("", "."):
                parts.append(part)
        return "/".join(parts)

    def write(self, files: Dict[str, bytes], destination: Path) -> List[str]:
        """
        :param files: The release's files.
        :param destination: The package's vendor directory, replaced entirely.
        :return: The written files.
        """
        if destination.exists():
            shutil.rmtree(destination)
        if self.licence_url:
            with urllib.request.urlopen(self.licence_url) as answer:
                files[LICENCE_FILE] = answer.read()
        written = self.needed_modules(files) + [
            name for name in self.extra_files if name in files
        ]
        for name in written:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(files[name])
        return written


PACKAGES: Tuple[VendoredPackage, ...] = (
    VendoredPackage(
        name="three",
        version="0.186.1",
        entry_modules=(
            "build/three.module.js",
            "examples/jsm/controls/OrbitControls.js",
            "examples/jsm/controls/TransformControls.js",
            "examples/jsm/loaders/GLTFLoader.js",
            "examples/jsm/loaders/STLLoader.js",
            "examples/jsm/loaders/ColladaLoader.js",
            "examples/jsm/loaders/OBJLoader.js",
            "examples/jsm/loaders/MTLLoader.js",
            "examples/jsm/environments/RoomEnvironment.js",
            "examples/jsm/postprocessing/EffectComposer.js",
            "examples/jsm/postprocessing/RenderPass.js",
            "examples/jsm/postprocessing/GTAOPass.js",
            "examples/jsm/postprocessing/OutputPass.js",
        ),
    ),
    VendoredPackage(
        name="urdf-loader",
        version="0.13.1",
        entry_modules=("src/URDFLoader.js",),
        licence_url="https://raw.githubusercontent.com/gkjohnson/urdf-loaders/v0.13.1/LICENSE",
    ),
)
"""
The libraries the viewer uses.
"""


def main(arguments: Sequence[str]) -> int:
    """
    Download, check and copy every vendored library, and write a manifest.

    :param arguments: Unused.
    :return: The process exit code.
    """
    manifest = {}
    for package in PACKAGES:
        files = package.download()
        written = package.write(files, VENDOR_DIRECTORY / package.name)
        manifest[package.name] = {"version": package.version, "files": written}
        print(f"{package.name}@{package.version}: {len(written)} files")
    (VENDOR_DIRECTORY / "manifest.json").write_text(
        json.dumps(manifest, indent=1) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
