"""
The authorship and reuse terms of a bundle's original assets, which a bundle carries in
``rights.json`` beside its licence and notice files.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Any, Mapping, Optional

from cramera_protocol.document import JsonDocument, document_field


class AssetRightsKey(StrEnum):
    """
    The keys of an asset rights record, as ``rights.json`` and ``scene.json`` write
    them.
    """

    PRINCIPAL_AUTHOR = "principalAuthor"
    """
    The assets' principal author.
    """

    INSTITUTION = "institution"
    """
    The institution the assets were made at.
    """

    COPYRIGHT = "copyright"
    """
    The copyright line.
    """

    LICENSE = "license"
    """
    The licence identifier.
    """

    PERMISSION_NOTICE = "permissionNotice"
    """
    Who may reuse the assets and how to ask.
    """

    PRIOR_LICENSE_NOTICE = "priorLicenseNotice"
    """
    Which earlier rights stay unaffected.
    """

    LICENSE_FILE = "licenseFile"
    """
    The licence text's file.
    """

    NOTICE_FILE = "noticeFile"
    """
    The credits' file.
    """


@dataclass(kw_only=True)
class AssetRights(JsonDocument):
    """
    The authorship and the reuse terms of a bundle's original assets, as ``rights.json``
    and a scene description's plugin content write them.
    """

    principal_author: str = document_field(AssetRightsKey.PRINCIPAL_AUTHOR)
    """
    The assets' principal author.
    """

    institution: str = document_field(AssetRightsKey.INSTITUTION)
    """
    The institution the assets were made at.
    """

    copyright_statement: str = document_field(AssetRightsKey.COPYRIGHT)
    """
    The copyright line.
    """

    license_identifier: str = document_field(AssetRightsKey.LICENSE)
    """
    The licence identifier, such as ``LicenseRef-AICOR-Laboratory-Assets``.
    """

    permission_notice: str = document_field(AssetRightsKey.PERMISSION_NOTICE)
    """
    Who may reuse the assets and how to ask.
    """

    prior_license_notice: str = document_field(AssetRightsKey.PRIOR_LICENSE_NOTICE)
    """
    Which earlier rights stay unaffected.
    """

    license_file: str = document_field(AssetRightsKey.LICENSE_FILE)
    """
    The licence text's file, beside the record.
    """

    notice_file: str = document_field(AssetRightsKey.NOTICE_FILE)
    """
    The credits' file, beside the record.
    """

    @classmethod
    def of_scene(cls, extensions: Mapping[str, Any], key: str) -> Optional[AssetRights]:
        """
        :param extensions: The plugin content of a scene description.
        :param key: The plugin content key the rights are stored under.
        :return: The rights the scene names, or None for a scene without them.
        """
        data = extensions.get(key)
        return None if data is None else cls.from_json(data)
