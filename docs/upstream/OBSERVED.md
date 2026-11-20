# What ESR does but never documents

Notes, written by hand, on what USDA FAS Export Sales Reporting's API does that no page of
this snapshot states (sdk-core's conventions §3, sdk-core ADR-0028). The two Swagger
documents under `openapi/` are the reference for names and parameters: they type the path
parameters `commodityCode`, `countryCode` and `marketYear` as `int32` and describe every
operation's answer as HTTP 200 with a schema of `type: object`, and they define no schema
beside it. The answers' shapes, ESR's empty answers and its refusals below come from the
wire, and `models.py`, `_client.classify` and `tests/fixtures/` follow it.
`scripts/refresh_upstream.py` neither writes nor checks this file, and `FETCHED.md` lists
it in a row of its own.

Each note ends with its probe: the date, the operation, by the `operationId` the snapshot
gives it, and the sample. A sample recorded as a fixture is named by its path under
`tests/fixtures/`, whose `recorded_at` gives the time of the request. A probe that kept no
answer says so and names its request, with its date where the text that held the note
gave one. The notes moved here on 2026-11-20 from `CLAUDE.md` and the docstring of
`params.EARLIEST_MARKET_YEAR`; no request was sent to write this file.

## The answers' shapes

### Codes are integers on the wire

The answers carry every code as a JSON integer, as the snapshot types the path parameters:
`commodityCode`, `countryCode`, `regionId` and `unitId` in the lists, `commodityCode`,
`countryCode` and `unitId` in the exports records, and `commodityCode` and `marketYear` in
the release list.

Probe: 2026-10-25, `ESRData_GetCommodities`, `ESRData_GetCountries`,
`ESRData_GetCountryData` and `ESRData_GetDataReleaseInfo`; samples
`tests/fixtures/get_commodities/all.json`, `tests/fixtures/get_countries/all.json`,
`tests/fixtures/get_country_data/wheat_white_canada_2024.json` and
`tests/fixtures/get_data_release_info/all.json`.

### The four lists

The commodities are 44, codes 101 to 1702, each with `commodityCode`, `commodityName` and
`unitId`. The countries are 211, codes 1 to 9990, each with `countryCode`, `countryName`,
`countryDescription`, `regionId` and `gencCode`, the two names padded with spaces, nearly
every `countryName` to 8 characters (`"CANADA  "`) and nearly every `countryDescription`
to 31. The regions are 12, each with `regionId` and `regionName`, and 99 is `UNKNOWN`. The
units are 5, each with `unitId` and `unitNames`, the field's name plural.

Probe: 2026-10-25, `ESRData_GetCommodities`, `ESRData_GetCountries`, `ESRData_GetRegions`
and `ESRData_GetUnitsOfMeasure`; samples `tests/fixtures/get_commodities/all.json`,
`tests/fixtures/get_countries/all.json`, `tests/fixtures/get_regions/all.json` and
`tests/fixtures/get_units_of_measure/all.json`.

### The exports records

An exports answer holds one record per destination and week, each with `commodityCode`,
`countryCode`, eight quantities as JSON integers (`weeklyExports`, `accumulatedExports`,
`outstandingSales`, `grossNewSales`, `currentMYNetSales`, `currentMYTotalCommitment`,
`nextMYOutstandingSales` and `nextMYNetSales`), `unitId` and `weekEndingDate`, a midnight
without a zone (`2023-06-01T00:00:00`). `currentMYNetSales` can be negative. Wheat white
(104) to Canada (1220) is 54 weeks in market year 2024, from 2023-06-01 to 2024-06-06, and
53 weeks in 2023, from 2022-06-02 to 2023-06-01.

Probe: 2026-10-25 and 2026-10-28, `ESRData_GetCountryData`; samples
`tests/fixtures/get_country_data/wheat_white_canada_2024.json`, recorded 2026-10-25, and
`tests/fixtures/get_country_data/wheat_white_canada_2023.json`, recorded 2026-10-28.

### A week that straddles two market years comes in each

The week ending 2023-06-01 is in both answers of wheat white to Canada, market year 2023
and market year 2024, with other values: 2023's record has `weeklyExports` 285 and
`accumulatedExports` 11060, 2024's 0 and 0, its accumulation starting again. A week that
straddles two market years comes in each, and a record carries no market year.

Probe: 2026-10-25 and 2026-10-28, `ESRData_GetCountryData`; samples
`tests/fixtures/get_country_data/wheat_white_canada_2024.json`, recorded 2026-10-25, and
`tests/fixtures/get_country_data/wheat_white_canada_2023.json`, recorded 2026-10-28.

### `allCountries` has no paging

The every-country form answers all of a market year's records in one body, without paging:
cottonseed (1201) in market year 2024 is 498 records for 11 destinations, a body of 139,119
bytes, and wheat HRW (101) in 2024 was 1,136 records for 28 destinations, 319,532 bytes.

Probe: 2026-10-25, `ESRData_GetAllCountriesData`; sample
`tests/fixtures/get_all_countries_data/cottonseed_2024.json`. The request for wheat HRW,
`GET /api/esr/exports/commodityCode/101/allCountries/marketYear/2024`, kept no answer, and
the text that held the note gave it no date.

### The destination UNKNOWN

Destination 9990, `UNKNOWN`, comes in an every-country answer as a row like any country's.
Wheat white in market year 2027 is 385 records for 22 destinations over 20 weeks, a 9990
row in each week, in a fixture of 119,811 bytes. Wheat white in 2024 was 1,012 records for
22 destinations, a 9990 row in all 54 weeks, 312,360 bytes as a fixture, over the fixtures'
cap of 256 KiB.

Probe: 2026-10-28, `ESRData_GetAllCountriesData`; sample
`tests/fixtures/get_all_countries_data/wheat_white_2027.json`. The request for wheat white
in 2024, `GET /api/esr/exports/commodityCode/104/allCountries/marketYear/2024`, sent the
same day, kept no answer.

### The release list

The release list holds one record per commodity, 44, each with `commodityCode`,
`marketYearStart`, `marketYearEnd`, `marketYear` and `releaseTimeStamp`. `marketYear` is
the commodity's current market year, named by the year it ends in: wheat white's 2027 runs
from 2026-06-01 to 2027-05-31. `releaseTimeStamp` carries no zone and prints two fractional
digits, and all 44 read `2026-10-22T08:30:42.67`. Market years differ per commodity and
start in June, August, September, October or January: wheat runs June to May, corn and
soybeans September to August, cotton August to July, and beef and pork the calendar year.

Probe: 2026-10-25, `ESRData_GetDataReleaseInfo`; sample
`tests/fixtures/get_data_release_info/all.json`.

## Empty answers

### An empty list for a code or a year without data

HTTP 200 with `[]` answers an unknown commodity (999), an unknown country (9999), a market
year far ahead (2099) and valid codes without exports (rye, 501, to every country in market
year 2024). An empty answer is no error, and it cannot tell an unknown code from a known
one without exports.

Probe: 2026-10-25, `ESRData_GetCountryData` and `ESRData_GetAllCountriesData`; samples
`tests/fixtures/get_country_data/unknown_commodity.json`,
`tests/fixtures/get_country_data/unknown_country.json`,
`tests/fixtures/get_country_data/year_2099.json` and
`tests/fixtures/get_all_countries_data/rye_2024.json`.

### A market year not yet released

Market year 2028 of wheat white to Canada answered HTTP 200 with `[]`, while wheat's
current market year was 2027, so a market year ESR has not released cannot be told from one
without exports.

Probe: 2026-10-28, `ESRData_GetCountryData`; the request
`GET /api/esr/exports/commodityCode/104/countryCode/1220/marketYear/2028`, one keyed call,
kept no answer.

### Where ESR's data begins is not established

Market years 1998 and 1999 of wheat white to Canada answered HTTP 200 with `[]`, as a pair
without exports does, where market year 1900 answers HTTP 404 (below): where ESR's data
begins is not established.

Probe: 2026-10-25, `ESRData_GetCountryData`; the requests
`GET /api/esr/exports/commodityCode/104/countryCode/1220/marketYear/1998` and
`GET /api/esr/exports/commodityCode/104/countryCode/1220/marketYear/1999` kept no answer.

## Refusals

### Market year 1900: HTTP 404 with an empty body

Market year 1900 answers HTTP 404 with an empty `text/plain` body on both exports forms, to
one country and to every country.

Probe: 2026-10-25 and 2026-10-28, `ESRData_GetCountryData` and
`ESRData_GetAllCountriesData`; samples `tests/fixtures/get_country_data/year_1900.json`,
recorded 2026-10-25, and `tests/fixtures/get_all_countries_data/year_1900.json`, recorded
2026-10-28.

### A path value that is not an integer: HTTP 400

A path value that is not an integer, `commodityCode/abc`, answers HTTP 400 with
`{"message":"The request is invalid."}`.

Probe: 2026-10-25, `ESRData_GetCountryData`; sample
`tests/fixtures/get_country_data/not_an_integer.json`.

### An invalid key: HTTP 403 without the quota headers

api.data.gov answers a key it does not know with HTTP 403 and
`{"error": {"code": "API_KEY_INVALID", ...}}`, without the `x-ratelimit-limit` and
`x-ratelimit-remaining` headers that every other recording carries.

Probe: 2026-10-25, `ESRData_GetCommodities` with a bogus key; sample
`tests/fixtures/get_commodities/invalid_key.json`.
