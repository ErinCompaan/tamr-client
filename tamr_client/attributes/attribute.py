"""
See https://docs.tamr.com/reference/attribute-types
"""
from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Optional, Tuple

import tamr_client.attributes.attribute_type as attribute_type
from tamr_client.attributes.attribute_type import AttributeType
import tamr_client.attributes.type_alias as type_alias
from tamr_client.datasets.dataset import Dataset
import tamr_client.response as response
from tamr_client.session import Session
from tamr_client.types import JsonDict
from tamr_client.url import URL


_RESERVED_NAMES = frozenset(
    [
        # See javasrc/procurify/ui/app/scripts/constants/ElasticConstants.js
        "origin_source_name",
        "tamr_id",
        "origin_entity_id",
        # See javasrc/procurify/ui/app/scripts/constants/PipelineConstants.js
        "clusterId",
        "originSourceId",
        "originEntityId",
        "sourceId",
        "entityId",
        "suggestedClusterId",
        "verificationType",
        "verifiedClusterId",
    ]
)


class AttributeNotFound(Exception):
    """Raised when referencing (e.g. updating or deleting) an attribute
    that does not exist on the server.
    """

    pass


class AttributeExists(Exception):
    """Raised when trying to create an attribute that already exists on the server"""

    pass


class ReservedAttributeName(Exception):
    """Raised when attempting to create an attribute with a reserved name"""

    pass


@dataclass(frozen=True)
class Attribute:
    """A Tamr Attribute.

    See https://docs.tamr.com/reference#attribute-types

    Args:
        url
        name
        type
        description
    """

    url: URL
    name: str
    type: AttributeType
    is_nullable: bool
    _json: JsonDict = field(compare=False, repr=False)
    description: Optional[str] = None


def from_resource_id(session: Session, dataset: Dataset, id: str) -> Attribute:
    """Get attribute by resource ID

    Fetches attribute from Tamr server

    Args:
        dataset: Dataset containing this attribute
        id: Attribute ID

    Raises:
        AttributeNotFound: If no attribute could be found at the specified URL.
            Corresponds to a 404 HTTP error.
        requests.HTTPError: If any other HTTP error is encountered.
    """
    url = replace(dataset.url, path=dataset.url.path + f"/attributes/{id}")
    return _from_url(session, url)


def _from_url(session: Session, url: URL) -> Attribute:
    """Get attribute by URL

    Fetches attribute from Tamr server

    Args:
        url: Attribute URL

    Raises:
        AttributeNotFound: If no attribute could be found at the specified URL.
            Corresponds to a 404 HTTP error.
        requests.HTTPError: If any other HTTP error is encountered.
    """
    r = session.get(str(url))
    if r.status_code == 404:
        raise AttributeNotFound(str(url))
    data = response.successful(r).json()
    return _from_json(url, data)


def _from_json(url: URL, data: JsonDict) -> Attribute:
    """Make attribute from JSON data (deserialize)

    Args:
        url: Attribute URL
        data: Attribute JSON data from Tamr server
    """
    cp = deepcopy(data)
    return Attribute(
        url,
        name=cp["name"],
        description=cp.get("description"),
        is_nullable=cp["isNullable"],
        type=attribute_type.from_json(cp["type"]),
        _json=cp,
    )


def from_dataset_all(session: Session, dataset: Dataset) -> Tuple[Attribute, ...]:
    """Get all attributes from a dataset

    Args:
        dataset: Dataset containing the desired attributes

    Returns:
        The attributes for the specified dataset

    Raises:
        requests.HTTPError: If an HTTP error is encountered.
    """
    attrs_url = replace(dataset.url, path=dataset.url.path + "/attributes")
    r = session.get(str(attrs_url))
    attrs_json = response.successful(r).json()

    attrs = []
    for attr_json in attrs_json:
        id = attr_json["name"]
        attr_url = replace(attrs_url, path=attrs_url.path + f"/{id}")
        attr = _from_json(attr_url, attr_json)
        attrs.append(attr)
    return tuple(attrs)


def to_json(attr: Attribute) -> JsonDict:
    """Serialize attribute into JSON

    Args:
        attr: Attribute to serialize

    Returns:
        JSON data representing the attribute
    """
    d = {
        "name": attr.name,
        "type": attribute_type.to_json(attr.type),
        "isNullable": attr.is_nullable,
    }
    if attr.description is not None:
        d["description"] = attr.description
    return d


def create(
    session: Session,
    dataset: Dataset,
    *,
    name: str,
    is_nullable: bool,
    type: AttributeType = type_alias.DEFAULT,
    description: Optional[str] = None,
) -> Attribute:
    """Create an attribute

    Posts a creation request to the Tamr server

    Args:
        dataset: Dataset that should contain the new attribute
        name: Name for the new attribute
        type: Attribute type for the new attribute
        is_nullable: Determines if the new attribute can contain NULL values
        description: Description of the new attribute
        force: If `True`, skips reserved attribute name check

    Returns:
        The newly created attribute

    Raises:
        ReservedAttributeName: If attribute name is reserved.
        AttributeExists: If an attribute already exists at the specified URL.
            Corresponds to a 409 HTTP error.
        requests.HTTPError: If any other HTTP error is encountered.
    """
    if name in _RESERVED_NAMES:
        raise ReservedAttributeName(name)

    return _create(
        session,
        dataset,
        name=name,
        is_nullable=is_nullable,
        type=type,
        description=description,
    )


def _create(
    session: Session,
    dataset: Dataset,
    *,
    name: str,
    is_nullable: bool,
    type: AttributeType = type_alias.DEFAULT,
    description: Optional[str] = None,
) -> Attribute:
    """Same as `tc.attribute.create`, but does not check for reserved attribute
    names.
    """
    attrs_url = replace(dataset.url, path=dataset.url.path + "/attributes")
    url = replace(attrs_url, path=attrs_url.path + f"/{name}")

    body = {
        "name": name,
        "type": attribute_type.to_json(type),
        "isNullable": is_nullable,
    }
    if description is not None:
        body["description"] = description

    r = session.post(str(attrs_url), json=body)
    if r.status_code == 409:
        raise AttributeExists(str(url))
    data = response.successful(r).json()

    return _from_json(url, data)


def update(
    session: Session, attribute: Attribute, *, description: Optional[str] = None
) -> Attribute:
    """Update an existing attribute

    PUTS an update request to the Tamr server

    Args:
        attribute: Existing attribute to update
        description: Updated description for the existing attribute

    Returns:
        The newly updated attribute

    Raises:
        AttributeNotFound: If no attribute could be found at the specified URL.
            Corresponds to a 404 HTTP error.
        requests.HTTPError: If any other HTTP error is encountered.
    """
    updates = {"description": description}
    r = session.put(str(attribute.url), json=updates)
    if r.status_code == 404:
        raise AttributeNotFound(str(attribute.url))
    data = response.successful(r).json()
    return _from_json(attribute.url, data)


def delete(session: Session, attribute: Attribute):
    """Deletes an existing attribute

    Sends a deletion request to the Tamr server

    Args:
        attribute: Existing attribute to delete

    Raises:
        AttributeNotFound: If no attribute could be found at the specified URL.
            Corresponds to a 404 HTTP error.
        requests.HTTPError: If any other HTTP error is encountered.
    """
    r = session.delete(str(attribute.url))
    if r.status_code == 404:
        raise AttributeNotFound(str(attribute.url))
    response.successful(r)
