"""
``cramera-check-bundle``: the reports it prints and its exit code.
"""

from __future__ import annotations

import io
import json

from cramera_offline.bundle_check import BundleCheck
from cramera_offline.check_command import CheckExit, CheckOption, ReportText, main
from cramera_protocol.offline import BundleCheckReport

# %% text


def test_a_complete_bundle_is_one_line(complete_bundle):
    report = BundleCheck(complete_bundle).report()
    lines = ReportText(report).lines()
    assert len(lines) == 1
    assert str(len(report.checked_files)) in lines[0]


def test_an_incomplete_bundle_lists_every_problem(broken_bundle):
    report = BundleCheck(broken_bundle).report()
    lines = ReportText(report).lines()
    assert len(lines) == 1 + len(report.problems)
    assert all(
        problem.reference in line for problem, line in zip(report.problems, lines[1:])
    )


# %% command


def test_complete_bundles_exit_with_success(complete_bundle):
    output = io.StringIO()
    assert main([str(complete_bundle)], output) == CheckExit.COMPLETE
    assert (
        output.getvalue().splitlines()
        == ReportText(BundleCheck(complete_bundle).report()).lines()
    )


def test_an_incomplete_bundle_fails_the_check(complete_bundle, broken_bundle):
    output = io.StringIO()
    exit_code = main([str(complete_bundle), str(broken_bundle)], output)
    assert exit_code == CheckExit.INCOMPLETE


def test_the_reports_can_be_printed_as_json(complete_bundle, broken_bundle):
    output = io.StringIO()
    main([str(complete_bundle), str(broken_bundle), CheckOption.JSON], output)
    reports = [
        BundleCheckReport.from_json(data) for data in json.loads(output.getvalue())
    ]
    assert reports == [
        BundleCheck(complete_bundle).report(),
        BundleCheck(broken_bundle).report(),
    ]
