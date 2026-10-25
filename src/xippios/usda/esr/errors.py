"""ESR failure modes with a distinct meaning (conventions §5)."""

from xippios.core import InvalidRequestError, NotFoundError

from xippios.usda.esr._client import SOURCE

__all__ = ["NoDataForYear", "UnknownCode"]


class NoDataForYear(NotFoundError):
    """ESR's own answer for a market year it holds no data for (HTTP 404, empty ``text/plain``).

    Recorded for market year 1900 on the one-country form
    (``tests/fixtures/ESRData_GetCountryData/year_1900.json``): status 404, an empty body,
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


class UnknownCode(InvalidRequestError):
    """A code the packaged ESR reference list does not contain (HTTP 422).

    ESR answers an unknown commodity or country code with HTTP 200 and an empty list
    (``tests/fixtures/ESRData_GetCountryData/unknown_commodity.json``, 999, and
    ``unknown_country.json``, 9999), which is indistinguishable from a query without
    exports. The package therefore checks codes against the packaged lists before calling
    upstream and refuses unknown ones, naming the closest known codes.

    Attributes:
        param: The parameter, as the package names it, e.g. ``"commodity_code"``.
        value: The integer given, e.g. ``999``.
        list_name: The packaged list checked, as upstream names it, e.g. ``"commodities"``.
        fetched: The day the packaged list was fetched, an ISO date, e.g. ``"2026-10-25"``.
        closest: The closest known codes with their upstream names, best match first.
    """

    def __init__(
        self,
        param: str,
        value: int,
        *,
        list_name: str,
        fetched: str,
        closest: list[tuple[int, str]],
    ) -> None:
        hint = (
            " Did you mean " + ", ".join(f"{code} ({name})" for code, name in closest) + "?"
            if closest
            else ""
        )
        super().__init__(
            f"{value} is not a {param} in ESR's {list_name} list (packaged, fetched "
            f"{fetched}).{hint} ESR answers unknown codes with an empty result, so the package "
            "refuses them. If ESR added the code since, the packaged lists need a refresh "
            "(/refresh-reference-data).",
            source=SOURCE,
        )
        self.param = param
        self.value = value
        self.list_name = list_name
        self.fetched = fetched
        self.closest = closest
