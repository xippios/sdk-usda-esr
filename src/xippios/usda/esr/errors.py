"""ESR failure modes with a distinct meaning (conventions §5).

A code the packaged lists lack is refused with core's ``xippios.core.UnknownCode``
(``params``, ADR-0022).
"""

from xippios.core import NotFoundError

from xippios.usda.esr._client import SOURCE

__all__ = ["NoDataForYear"]


class NoDataForYear(NotFoundError):
    """ESR's own answer for a market year it holds no data for (HTTP 404, empty ``text/plain``).

    Recorded for market year 1900 on the one-country form
    (``tests/fixtures/get_country_data/year_1900.json``): status 404, an empty body,
    ``content-type: text/plain; charset=utf-8``. ``_client.classify`` raises it for that
    answer on an exports path only. A market year in the future answers differently, HTTP
    200 with ``[]`` (``year_2099.json``), which ``params.validate_market_year`` refuses
    before any call. The gateway's 404 (``{"error": {"code": "NOT_FOUND", ...}}``, no such
    route) stays a plain ``NotFoundError``: it says the request is wrong, not that the year
    is empty. ``get_exports`` raises it again with a message naming commodity, country and
    market year.

    Attributes:
        path: The request path, e.g.
            ``"/api/esr/exports/commodityCode/104/countryCode/1220/marketYear/1900"``.
    """

    def __init__(self, path: str, message: str | None = None) -> None:
        super().__init__(
            message or f"ESR has no data for {path} (HTTP 404 with an empty body)",
            source=SOURCE,
        )
        self.path = path
