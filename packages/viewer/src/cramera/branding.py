"""
The logo every page's top bar shows: the AICOR logo, or an image the viewer was given
with ``--logo`` or :attr:`~cramera_protocol.viewer.EnvironmentVariable.LOGO`, served at
:attr:`~cramera_protocol.viewer.ViewerRoute.LOGO` and copied into an exported site.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from typing_extensions import Mapping, Optional

from cramera.exceptions import LogoNotFound, UnsupportedLogo
from cramera_protocol.viewer import EnvironmentVariable

DEFAULT_LOGO = Path(__file__).parent / "web" / "images" / "aicor-logo.png"
"""
The AICOR logo, shown unless another is given.
"""

LOGO_SUFFIXES = (".png", ".svg", ".jpg", ".jpeg")
"""
The suffixes of the images a logo may be.
"""

# %% branding


@dataclass(frozen=True)
class Branding:
    """
    Which logo the viewer shows.
    """

    logo: Optional[Path] = None
    """
    The image shown instead of the AICOR logo, or None for the AICOR logo.
    """

    logo_text: Optional[str] = None
    """
    What the given logo shows, for people who cannot see it; None names the file's stem
    for a given logo.
    """

    @classmethod
    def of(
        cls,
        logo: Optional[Path],
        logo_text: Optional[str],
        environment: Mapping[str, str],
    ) -> Branding:
        """
        :param logo: The logo given on the command line, or None.
        :param logo_text: Its text given on the command line, or None.
        :param environment: The environment, whose :attr:`EnvironmentVariable.LOGO`
            names a logo when the command line gives none.
        :return: The branding, its logo checked.
        :raises LogoNotFound: When the logo does not exist.
        :raises UnsupportedLogo: When the logo is no image a browser shows.
        """
        named = environment.get(EnvironmentVariable.LOGO)
        chosen = logo if logo is not None else (Path(named) if named else None)
        branding = cls(logo=chosen, logo_text=logo_text)
        branding.file()
        return branding

    def file(self) -> Path:
        """
        :return: The logo's image file.
        :raises LogoNotFound: When the given logo does not exist.
        :raises UnsupportedLogo: When the given logo is no image a browser shows.
        """
        if self.logo is None:
            return DEFAULT_LOGO
        if not self.logo.is_file():
            raise LogoNotFound(self.logo)
        if self.logo.suffix.lower() not in LOGO_SUFFIXES:
            raise UnsupportedLogo(self.logo, list(LOGO_SUFFIXES))
        return self.logo

    def text(self) -> Optional[str]:
        """
        :return: What the given logo shows, or None for the AICOR logo, whose text the
            page knows.
        """
        if self.logo is None:
            return None
        return self.logo_text or self.logo.stem
