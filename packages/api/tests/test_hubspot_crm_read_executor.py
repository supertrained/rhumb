"""Tests for the HubSpot CRM read-first executor."""

from __future__ import annotations

import pytest

from schemas.crm_capabilities import (
    CrmObjectDescribeRequest,
    CrmRecordGetRequest,
    CrmRecordSearchFilter,
    CrmRecordSearchRequest,
    CrmRecordSort,
)
from services.crm_connection_registry import HubSpotCrmBundle
from services.hubspot_crm_read_executor import (
    HubSpotCrmExecutorError,
    _build_headers,
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
    def __init__(self, *, responses: dict[tuple[str, str], MockResponse], **_kwargs):
        self.responses = responses
        self.calls: list[tuple[str, str, dict | None, dict | None]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def request(self, method: str, path: str, params=None, json=None):
        self.calls.append((method, path, params, json))
        response = self.responses.get((method, path))
        if response is None:
            raise AssertionError(f"unexpected request: {method} {path} params={params} json={json}")
        return response


class RecordingClientFactory:
    def __init__(self, responses: dict[tuple[str, str], MockResponse]):
        self.responses = responses
        self.client: MockAsyncClient | None = None

    def __call__(self, **kwargs):
        self.client = MockAsyncClient(responses=self.responses, **kwargs)
        return self.client


def _bundle(**overrides) -> HubSpotCrmBundle:
    data = {
        "crm_ref": "hs_main",
        "provider": "hubspot",
        "auth_mode": "private_app_token",
        "private_app_token": "token-123",
        "portal_id": "12345678",
        "allowed_object_types": ("contacts",),
        "allowed_properties_by_object": {
            "contacts": ("email", "firstname", "lastname", "createdate", "lastmodifieddate"),
        },
        "default_properties_by_object": {
            "contacts": ("email", "firstname"),
        },
        "searchable_properties_by_object": {
            "contacts": ("email", "firstname"),
        },
        "sortable_properties_by_object": {
            "contacts": ("createdate",),
        },
        "allowed_record_ids_by_object": {},
    }
    data.update(overrides)
    return HubSpotCrmBundle(**data)


@pytest.mark.asyncio
async def test_describe_object_returns_contract_fields() -> None:
    request = CrmObjectDescribeRequest(crm_ref="hs_main", object_type="contacts")
    bundle = _bundle()
    client_factory = RecordingClientFactory(
        {
            ("GET", "/crm/v3/properties/contacts"): MockResponse(
                200,
                {
                    "results": [
                        {"name": "email", "label": "Email", "type": "string", "fieldType": "text"},
                        {"name": "firstname", "label": "First name", "type": "string", "fieldType": "text"},
                        {"name": "notes_last_updated", "label": "Ignored", "type": "string", "fieldType": "text"},
                    ],
                },
            )
        }
    )

    response = await describe_object(request, bundle=bundle, client_factory=client_factory)

    assert response.portal_id == "12345678"
    assert response.label == "Contact"
    assert response.plural_label == "Contacts"
    assert response.primary_display_property == "email"
    assert response.required_properties == []
    assert response.property_count_returned == 2
    assert [prop.name for prop in response.properties] == ["email", "firstname"]
    assert response.properties[0].searchable is True
    assert response.properties[0].sortable is False
    assert response.properties[0].read_only is False


@pytest.mark.asyncio
async def test_describe_object_maps_scope_denial_to_contract_code() -> None:
    request = CrmObjectDescribeRequest(crm_ref="hs_main", object_type="deals")

    with pytest.raises(HubSpotCrmExecutorError) as exc:
        await describe_object(
            request,
            bundle=_bundle(),
            client_factory=RecordingClientFactory({}),
        )

    assert exc.value.code == "crm_object_scope_denied"
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_search_records_rejects_out_of_scope_filter_property() -> None:
    request = CrmRecordSearchRequest(
        crm_ref="hs_main",
        object_type="contacts",
        filters=[CrmRecordSearchFilter(property="lastname", operator="EQ", value="Lovelace")],
    )
    bundle = _bundle(searchable_properties_by_object={"contacts": ("email",)})

    with pytest.raises(HubSpotCrmExecutorError) as exc:
        await search_records(
            request,
            bundle=bundle,
            client_factory=RecordingClientFactory({}),
        )

    assert exc.value.code == "crm_property_scope_denied"
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_search_records_serializes_filters_and_sorts_and_filters_record_scope() -> None:
    request = CrmRecordSearchRequest(
        crm_ref="hs_main",
        object_type="contacts",
        property_names=["email", "firstname"],
        filters=[CrmRecordSearchFilter(property="email", operator="EQ", value="ada@example.com")],
        sorts=[CrmRecordSort(property="createdate", direction="desc")],
    )
    bundle = _bundle(allowed_record_ids_by_object={"contacts": ("101",)})
    client_factory = RecordingClientFactory(
        {
            ("POST", "/crm/v3/objects/contacts/search"): MockResponse(
                200,
                {
                    "results": [
                        {
                            "id": "101",
                            "properties": {"email": "ada@example.com", "firstname": "Ada"},
                            "createdAt": "2026-04-09T17:00:00Z",
                            "updatedAt": "2026-04-09T17:01:00Z",
                            "archived": False,
                        },
                        {
                            "id": "202",
                            "properties": {"email": "grace@example.com", "firstname": "Grace"},
                            "createdAt": "2026-04-09T18:00:00Z",
                            "updatedAt": "2026-04-09T18:01:00Z",
                            "archived": False,
                        },
                    ],
                    "paging": {"next": {"after": "cursor-2"}},
                },
            )
        }
    )

    response = await search_records(request, bundle=bundle, client_factory=client_factory)

    assert response.record_count_returned == 1
    assert response.records[0].record_id == "101"
    assert response.records[0].properties == {"email": "ada@example.com", "firstname": "Ada"}
    assert response.next_after == "cursor-2"
    assert client_factory.client is not None
    _, _, _, body = client_factory.client.calls[0]
    assert body["properties"] == ["email", "firstname"]
    assert body["filterGroups"][0]["filters"][0] == {
        "propertyName": "email",
        "operator": "EQ",
        "value": "ada@example.com",
    }
    assert body["sorts"] == ["-createdate"]


@pytest.mark.asyncio
async def test_search_records_maps_unsupported_operator_to_request_invalid() -> None:
    request = CrmRecordSearchRequest.model_construct(
        crm_ref="hs_main",
        object_type="contacts",
        limit=10,
        after=None,
        query=None,
        property_names=None,
        filters=[CrmRecordSearchFilter.model_construct(property="email", operator="BOGUS", value="ada@example.com")],
        sorts=[],
        reason=None,
    )

    with pytest.raises(HubSpotCrmExecutorError) as exc:
        await search_records(
            request,
            bundle=_bundle(),
            client_factory=RecordingClientFactory({}),
        )

    assert exc.value.code == "crm_request_invalid"
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_record_maps_not_found() -> None:
    request = CrmRecordGetRequest(crm_ref="hs_main", object_type="contacts", record_id="999")
    bundle = _bundle()
    client_factory = RecordingClientFactory(
        {
            ("GET", "/crm/v3/objects/contacts/999"): MockResponse(404, {"message": "Not Found"})
        }
    )

    with pytest.raises(HubSpotCrmExecutorError) as exc:
        await get_record(request, bundle=bundle, client_factory=client_factory)

    assert exc.value.code == "crm_record_not_found"
    assert exc.value.status_code == 404


def test_build_headers() -> None:
    bundle = _bundle(private_app_token="secret")

    headers = _build_headers(bundle)

    assert headers["Accept"] == "application/json"
    assert headers["Authorization"] == "Bearer secret"
    assert headers["Content-Type"] == "application/json"
