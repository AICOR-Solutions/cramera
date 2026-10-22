"""
A WebDriver that answers like a browser showing a ready viewer page, without a browser.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

from cramera.http.messages import HttpMethod
from cramera.screenshot import BrowserKind, WebDriver, WebDriverKey
from cramera_protocol.events import PageReportKey, PageState
from typing_extensions import Any, Dict, List, Optional

# %% answers

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
"""
The bytes every PNG file starts with; the mimic's screenshot is just this.
"""

MIMIC_SESSION = "mimic"
"""
The identity of the only session the mimic creates.
"""

READY_STATUS = "Scene shown"
"""
The status line the mimic's page reports.
"""

# %% mimic


@dataclass
class MimicWebDriver(WebDriver):
    """
    Answers the WebDriver calls of a screenshot: the page is ready at once.
    """

    kind: BrowserKind = BrowserKind.FIREFOX
    """
    The browser the mimic stands for.
    """

    pages: List[str] = field(default_factory=list)
    """
    The addresses the screenshot loaded.
    """

    def start(self) -> MimicWebDriver:
        return self

    def stop(self) -> None:
        return None

    def call(
        self, method: HttpMethod, path: str, body: Optional[Dict[str, Any]] = None
    ) -> Any:
        if path.endswith("/url"):
            self.pages.append(body[WebDriverKey.URL])
            return None
        if path.endswith("/execute/sync"):
            return {
                PageReportKey.STATE: PageState.READY,
                PageReportKey.STATUS: READY_STATUS,
            }
        if path.endswith("/screenshot"):
            return base64.b64encode(PNG_SIGNATURE).decode()
        if method == HttpMethod.POST:
            return {WebDriverKey.SESSION_IDENTIFIER: MIMIC_SESSION}
        return None
