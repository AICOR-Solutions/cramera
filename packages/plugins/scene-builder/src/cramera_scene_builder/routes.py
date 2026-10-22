"""
The scene builder's routes: the catalog, scene templates, saved drafts, library files,
point cloud uploads and their display samples.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from typing_extensions import Any, List

from cramera.http.messages import HttpMethod, MediaType, Request, Response
from cramera.plugins import PluginPrefixRoute, PluginRoute, RouteDeclaration
from cramera.scenes import SceneCatalog
from cramera_protocol.scene_builder import (
    DraftList,
    DraftRecord,
    PointCloudFormat,
    SceneBuilderCatalog,
    SceneBuilderLimits,
    SceneBuilderRoute,
    TemplateParameter,
)
from cramera_scene_builder.assets import AssetFiles
from cramera_scene_builder.drafts import DraftCheck, DraftResources, DraftStore
from cramera_scene_builder.exceptions import (
    ContentTooLarge,
    InvalidTemplateRequest,
    MalformedRequestBody,
    UnsupportedPointCloudFormat,
)
from cramera_scene_builder.point_clouds import PointCloudFile
from cramera_scene_builder.resources import ResourceIdentifier, ResourceLibrary
from cramera_scene_builder.templates import SceneTemplate
from cramera_scene_builder.uploads import PointCloudStore

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
class SceneBuilderRoutes:
    """
    Answers the scene builder's requests.
    """

    catalog: SceneCatalog
    """
    The scenes the viewer shows, which drafts can start from.
    """

    library: ResourceLibrary
    """
    The files drafts can place.
    """

    drafts: DraftStore
    """
    The saved drafts.
    """

    point_clouds: PointCloudStore
    """
    The uploaded point clouds.
    """

    limits: SceneBuilderLimits
    """
    The bounds drafts and uploads stay within.
    """

    def declarations(self) -> List[RouteDeclaration]:
        """
        :return: The routes, below the plugin's prefix.
        """
        return [
            PluginRoute(HttpMethod.GET, SceneBuilderRoute.CATALOG, self.answer_catalog),
            PluginRoute(
                HttpMethod.GET, SceneBuilderRoute.TEMPLATE, self.answer_template
            ),
            PluginRoute(HttpMethod.GET, SceneBuilderRoute.DRAFTS, self.answer_drafts),
            PluginRoute(HttpMethod.POST, SceneBuilderRoute.DRAFTS, self.answer_save),
            PluginPrefixRoute(
                HttpMethod.GET, SceneBuilderRoute.DRAFT, self.answer_draft
            ),
            PluginPrefixRoute(
                HttpMethod.GET, SceneBuilderRoute.ASSETS, self.answer_asset
            ),
            PluginPrefixRoute(
                HttpMethod.POST, SceneBuilderRoute.POINT_CLOUDS, self.answer_upload
            ),
            PluginPrefixRoute(
                HttpMethod.GET,
                SceneBuilderRoute.POINT_CLOUD_SAMPLES,
                self.answer_sample,
            ),
        ]

    def answer_catalog(self, request: Request) -> Response:
        """
        :param request: A request for the catalog.
        :return: The resources, scenes and drafts, with the limits.
        """
        return Response.of_json(
            SceneBuilderCatalog(
                resources=self.library.resources(),
                scenes=self.catalog.index().scenes,
                drafts=self.drafts.summaries(),
                limits=self.limits,
            )
        )

    def answer_template(self, request: Request) -> Response:
        """
        :param request: A request naming one scene by :attr:`TemplateParameter.SCENE`.
        :return: A new draft of the scene, with the notices of its resources.
        :raises InvalidTemplateRequest: Unless the request names exactly one scene.
        """
        parameters = request.parameters()
        scenes = parameters.get(TemplateParameter.SCENE, [])
        if set(parameters) != {TemplateParameter.SCENE} or len(scenes) != 1:
            raise InvalidTemplateRequest(request.query)
        draft = SceneTemplate(self.catalog, self.library).draft(scenes[0])
        return Response.of_json(DraftResources(self.library).complete(draft))

    def answer_drafts(self, request: Request) -> Response:
        """
        :param request: A request for the saved drafts.
        :return: The saved drafts.
        """
        return Response.of_json(DraftList(drafts=self.drafts.summaries()))

    def answer_draft(self, request: Request, identifier: str) -> Response:
        """
        :param request: A request for one saved draft.
        :param identifier: The draft's identity.
        :return: The draft with its identity.
        """
        return Response.of_json(self.drafts.load(identifier))

    def answer_save(self, request: Request) -> Response:
        """
        Check a draft against the limits and the library, then save it.

        :param request: A request whose body is a :class:`DraftRecord`.
        :return: The saved draft with its identity and completed notices.
        """
        body = JsonBody(request, self.limits.maximum_document_bytes).read()
        record = DraftRecord.from_json(body)
        DraftCheck(self.limits).check(record.document)
        document = DraftResources(self.library).complete(record.document)
        return Response.of_json(
            self.drafts.save(
                DraftRecord(identifier=record.identifier, document=document)
            )
        )

    def answer_asset(self, request: Request, path: str) -> Response:
        """
        :param request: A request for a library file.
        :param path: The file's resource identifier.
        :return: The file, with a model's references relative to it.
        """
        return AssetFiles(self.library).answer(ResourceIdentifier.parse(path))

    def answer_upload(self, request: Request, format_name: str) -> Response:
        """
        :param request: A request whose body is a point cloud file.
        :param format_name: The file's :class:`PointCloudFormat` value.
        :return: The kept point cloud as the library lists it.
        :raises UnsupportedPointCloudFormat: For another format.
        """
        if format_name not in {member.value for member in PointCloudFormat}:
            raise UnsupportedPointCloudFormat(format_name)
        identifier = self.point_clouds.keep(PointCloudFormat(format_name), request.body)
        return Response.of_json(self.library.resource(identifier))

    def answer_sample(self, request: Request, path: str) -> Response:
        """
        :param request: A request for a point cloud's display sample.
        :param path: The point cloud's resource identifier.
        :return: The sample's bytes, see :class:`PointCloudSample`.
        :raises ContentTooLarge: When the file is larger than an upload may be.
        """
        identifier = ResourceIdentifier.parse(path)
        file_format = self.library.point_cloud_format(identifier)
        file = self.library.placeable_file(identifier)
        size = file.stat().st_size
        if size > self.limits.maximum_point_cloud_bytes:
            raise ContentTooLarge(size, self.limits.maximum_point_cloud_bytes)
        sample = PointCloudFile(file_format, file.read_bytes(), self.limits).sample()
        return Response(body=sample.to_bytes(), media_type=MediaType.BINARY)
