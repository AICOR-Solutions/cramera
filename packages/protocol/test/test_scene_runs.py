"""
The runs a viewer offers and their state, as documents.
"""

from __future__ import annotations

from cramera_protocol.browser import BrowserModule
from cramera_protocol.scene_runs import (
    SceneRun,
    SceneRunCatalog,
    SceneRunKey,
    SceneRunPlaceholder,
    SceneRunsState,
    SceneRunState,
    SceneRunStatus,
)

CATALOG = {
    "runs": [
        {
            "identifier": "pr2_transfer",
            "label": "PR2 vessel transfer",
            "command": [
                "python",
                "-m",
                "demo",
                "--name",
                SceneRunPlaceholder.RECORDING,
            ],
            "scene": "aicor_medical_lab_pr2_query_stepper",
        },
        {"identifier": "fr3_plates", "label": "FR3 plate cycle", "command": ["fr3"]},
    ]
}


def test_a_catalog_file_reads_its_runs_in_order():
    catalog = SceneRunCatalog.from_json(CATALOG)
    assert [run.identifier for run in catalog.runs] == ["pr2_transfer", "fr3_plates"]
    assert catalog.runs[1].scene is None
    assert catalog.to_json() == CATALOG


def test_pages_see_a_run_without_its_command():
    choice = SceneRunCatalog.from_json(CATALOG).runs[0].choice()
    assert SceneRunKey.COMMAND not in choice.to_json()
    assert choice.scene == "aicor_medical_lab_pr2_query_stepper"


def test_the_state_names_the_run_started_last():
    state = SceneRunsState(
        runs=[run.choice() for run in SceneRunCatalog.from_json(CATALOG).runs],
        current=SceneRunStatus(
            identifier="pr2_transfer",
            state=SceneRunState.RUNNING,
            recording="pr2_transfer_20261028_120000",
        ),
    )
    assert SceneRunsState.from_json(state.to_json()) == state
    assert "current" not in SceneRunsState().to_json()


def test_the_browser_reads_the_scene_run_names():
    source = BrowserModule().source()
    for name in (
        "SceneRunsName",
        "SceneRunsRoute",
        "SceneRunState",
        "SceneRunsStateKey",
    ):
        assert f"export const {name}" in source
