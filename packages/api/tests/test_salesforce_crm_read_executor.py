"""Tests for the Salesforce CRM read-first executor."""

from __future__ import annotations

import pytest

from schemas.crm_capabilities import (
    CrmObjectDescribeRequest,
    CrmRecordGetRequest,
    CrmRecordSearchFilter,
    CrmRecordSearchRequest,
    CrmRecordSort,
)
from services.crm_connection_registry import SalesforceCrmBundle
from services.salesforce_crm_read_executor import (
    SalesforceCrmExecutorError,
    describe_object,
    get_record,
    search_records,
)


class MockResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class MockAsyncClient:
    def __init__(self, *, base_url: str, responses: dict[tuple[str, str, str], MockResponse], **_kwargs):
        self.base_url = str(base_url).rstrip("/")
        self.responses = responses
        self.calls: list[tuple[str, str, dict | None, dict | None, dict | None]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def request(self, method: str, path: str, params=None, json=None, headers=None, data=None):
        self.calls.append((method, path, params, json, data))
        response = self.responses.get((self.base_url, method, path))
        if response is None:
            raise AssertionError(
                f"unexpected request: base_url={self.base_url} method={method} path={path} params={params} json={json} data={data}"
            )
        return response


class RecordingClientFactory:
    def __init__(self, responses: dict[tuple[str, str, str], MockResponse]):
        self.responses = responses
        self.clients: list[MockAsyncClient] = []

    def __call__(self, **kwargs):
        client = MockAsyncClient(responses=self.responses, **kwargs)
        self.clients.append(client)
        return client


def _bundle(**overrides) -> SalesforceCrmBundle:
    data = {
        "crm_ref": "sf_main",
        "provider": "salesforce",
        "auth_mode": "connected_app_refresh_token",
        "client_id": "client-123",
        "client_secret": "secret-123",
        "refresh_token": "refresh-123",
        "auth_base_url": "https://test.salesforce.com",
        "api_version": "v61.0",
        "allowed_object_types": ("Account",),
        "allowed_properties_by_object": {
            "Account": ("Name", "Industry", "CreatedDate", "LastModifiedDate"),
        },
        "default_properties_by_object": {
            "Account": ("Name", "Industry"),
        },
        "searchable_properties_by_object": {
            "Account": ("Name",),
        },
        "sortable_properties_by_object": {
            "Account": ("CreatedDate",),
        },
        "allowed_record_ids_by_object": {},
    }
    data.update(overrides)
    return SalesforceCrmBundle(**data)


def _responses(extra: dict[tuple[str, str, str], MockResponse]) -> dict[tuple[str, str, str], MockResponse]:
    base = {
        ("https://test.salesforce.com", "POST", "/services/oauth2/token"): MockResponse(
            200,
            {
                "access_token": "access-123",
                "instance_url": "https://example.my.salesforce.com",
            },
        )
    }
    base.update(extra)
    return base


@pytest.mark.asyncio
async def test_describe_object_returns_contract_fields() -> None:
    request = CrmObjectDescribeRequest(crm_ref="sf_main", object_type="Account")
    client_factory = RecordingClientFactory(
        _responses(
            {
                ("https://example.my.salesforce.com", "GET", "/services/data/v61.0/sobjects/Account/describe"): MockResponse(
                    200,
                    {
                        "label": "Account",
                        "labelPlural": "Accounts",
                        "fields": [
                            {
                                "name": "Name",
                                "label": "Account Name",
                                "type": "string",
                                "soapType": "xsd:string",
                                "filterable": True,
                                "sortable": True,
                                "updateable": True,
                                "nillable": False,
                                "defaultedOnCreate": False,
                                "nameField": True,
                            },
                            {
                                "name": "Industry",
                                "label": "Industry",
                                "type": "picklist",
                                "soapType": "xsd:string",
                                "filterable": True,
                                "sortable": False,
                                "updateable": True,
                                "nillable": True,
                                "defaultedOnCreate": False,
                            },
                            {
                                "name": "Ignored__c",
                                "label": "Ignored",
                                "type": "string",
                                "soapType": "xsd:string",
                                "filterable": True,
                                "sortable": True,
                                "updateable": True,
                                "nillable": True,
                                "defaultedOnCreate": False,
                            },
                        ],
                    },
                )
            }
        )
    )

    response = await describe_object(request, bundle=_bundle(), client_factory=client_factory)

    assert response.provider_used == "salesforce"
    assert response.label == "Account"
    assert response.plural_label == "Accounts"
    assert response.primary_display_property == "Name"
    assert response.required_properties == ["Name"]
    assert [prop.name for prop in response.properties] == ["Name", "Industry"]
    assert response.properties[0].searchable is True
    assert response.properties[0].sortable is False


@pytest.mark.asyncio
async def test_search_records_builds_bounded_soql_and_respects_record_scope() -> None:
    request = CrmRecordSearchRequest(
        crm_ref="sf_main",
        object_type="Account",
        query="Acme",
        property_names=["Name", "Industry"],
        filters=[CrmRecordSearchFilter(property="Name", operator="EQ", value="Acme")],
        sorts=[CrmRecordSort(property="CreatedDate", direction="desc")],
    )
    bundle = _bundle(allowed_record_ids_by_object={"Account": ("001ABC000000123XYZ",)})
    client_factory = RecordingClientFactory(
        _responses(
            {
                ("https://example.my.salesforce.com", "GET", "/services/data/v61.0/query"): MockResponse(
                    200,
                    {
                        "totalSize": 2,
                        "done": False,
                        "nextRecordsUrl": "/services/data/v61.0/query/01gNEXT0000001-2000",
                        "records": [
                            {
                                "Id": "001ABC000000123XYZ",
                                "Name": "Acme",
                                "Industry": "Software",
                                "CreatedDate": "2026-04-09T17:00:00.000+0000",
                                "LastModifiedDate": "2026-04-09T17:01:00.000+0000",
                            },
                            {
                                "Id": "001ABC000000999XYZ",
                                "Name": "Wrong Scope",
                                "Industry": "Finance",
                                "CreatedDate": "2026-04-09T17:02:00.000+0000",
                                "LastModifiedDate": "2026-04-09T17:03:00.000+0000",
                            },
                        ],
                    },
                )
            }
        )
    )

    response = await search_records(request, bundle=bundle, client_factory=client_factory)

    assert response.record_count_returned == 1
    assert response.records[0].record_id == "001ABC000000123XYZ"
    assert response.records[0].properties == {"Name": "Acme", "Industry": "Software"}
    assert response.next_after == "/services/data/v61.0/query/01gNEXT0000001-2000"
    assert len(client_factory.clients) == 2
    _, _, params, _, _ = client_factory.clients[1].calls[0]
    assert params is not None
    assert "SELECT Id, Name, Industry, CreatedDate, LastModifiedDate FROM Account" in params["q"]
    assert "Name LIKE '%Acme%'" in params["q"]
    assert "Name = 'Acme'" in params["q"]
    assert "Id IN ('001ABC000000123XYZ')" in params["q"]
    assert "ORDER BY CreatedDate DESC" in params["q"]
    assert params["q"].endswith("LIMIT 10")


@pytest.mark.asyncio
async def test_search_records_rejects_mixed_cursor_and_filter_shape() -> None:
    request = CrmRecordSearchRequest(
        crm_ref="sf_main",
        object_type="Account",
        after="/services/data/v61.0/query/01gNEXT0000001-2000",
        filters=[CrmRecordSearchFilter(property="Name", operator="EQ", value="Acme")],
    )

    with pytest.raises(SalesforceCrmExecutorError) as exc:
        await search_records(
            request,
            bundle=_bundle(),
            client_factory=RecordingClientFactory(_responses({})),
        )

    assert exc.value.code == "crm_request_invalid"
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_record_maps_not_found() -> None:
    request = CrmRecordGetRequest(crm_ref="sf_main", object_type="Account", record_id="001ABC000000123XYZ")
    client_factory = RecordingClientFactory(
        _responses(
            {
                ("https://example.my.salesforce.com", "GET", "/services/data/v61.0/query"): MockResponse(
                    200,
                    {
                        "totalSize": 0,
                        "done": True,
                        "records": [],
                    },
                )
            }
        )
    )

    with pytest.raises(SalesforceCrmExecutorError) as exc:
        await get_record(request, bundle=_bundle(), client_factory=client_factory)

    assert exc.value.code == "crm_record_not_found"
    assert exc.value.status_code == 404
