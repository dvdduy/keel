from __future__ import annotations

import re
from collections import defaultdict
from uuid import UUID, uuid4

from keel.application.specs.parser import parse_pipeline_spec_yaml
from keel.application.specs.versioning import SpecVersion, spec_content_hash
from keel.application.use_cases.submit_spec import SubmitSpec

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class FakeSpecVersionRepository:
    def __init__(self) -> None:
        self.history: dict[UUID, list[SpecVersion]] = defaultdict(list)

    def head_for(self, pipeline_id: UUID) -> SpecVersion | None:
        versions = self.history[pipeline_id]
        return versions[-1] if versions else None

    def add(self, version: SpecVersion) -> None:
        self.history[version.pipeline_id].append(version)


def _spec(yaml_text: str):
    return parse_pipeline_spec_yaml(yaml_text)


def _orders_spec_yaml(
    *,
    explicit_nullable: bool = False,
    swapped_contract: bool = False,
    destination: str = "analytics.orders",
) -> str:
    nullable_line = "      nullable: true\n" if explicit_nullable else ""

    first_column = f"""    - name: order_id
      type: string
{nullable_line}"""

    second_column = """    - name: amount
      type: decimal
"""

    contract = second_column + first_column if swapped_contract else first_column + second_column

    return f"""name: orders_daily
team: analytics
owner: data-platform@example.com
source:
  type: csv
  path: tests/fixtures/orders.csv
contract:
{contract}destination: {destination}
freshness:
  max_age_minutes: 60
quality_checks: []
"""


def test_content_hash_is_deterministic() -> None:
    spec = _spec(_orders_spec_yaml())

    first = spec_content_hash(spec)
    second = spec_content_hash(spec)

    assert first == second
    assert _HEX_64.match(first)


def test_content_hash_ignores_representation_defaults() -> None:
    implicit_default = _spec(_orders_spec_yaml(explicit_nullable=False))
    explicit_default = _spec(_orders_spec_yaml(explicit_nullable=True))

    assert spec_content_hash(implicit_default) == spec_content_hash(explicit_default)


def test_content_hash_ignores_key_order() -> None:
    one = _spec(_orders_spec_yaml())
    reordered = _spec("""quality_checks: []
freshness:
  max_age_minutes: 60
destination: analytics.orders
contract:
  - name: order_id
    type: string
  - name: amount
    type: decimal
source:
  type: csv
  path: tests/fixtures/orders.csv
owner: data-platform@example.com
team: analytics
name: orders_daily
""")

    assert spec_content_hash(one) == spec_content_hash(reordered)


def test_content_hash_is_order_sensitive_for_contract() -> None:
    original = _spec(_orders_spec_yaml())
    swapped = _spec(_orders_spec_yaml(swapped_contract=True))

    assert spec_content_hash(original) != spec_content_hash(swapped)


def test_first_submit_creates_root_version() -> None:
    pipeline_id = uuid4()
    spec = _spec(_orders_spec_yaml())
    repo = FakeSpecVersionRepository()

    result = SubmitSpec(repo).submit(pipeline_id, spec)

    assert result.created is True
    assert result.version.pipeline_id == pipeline_id
    assert result.version.parent_id is None
    assert result.version.spec_id == spec_content_hash(spec)
    assert repo.history[pipeline_id] == [result.version]


def test_identical_resubmit_is_noop() -> None:
    pipeline_id = uuid4()
    spec = _spec(_orders_spec_yaml())
    repo = FakeSpecVersionRepository()
    submit = SubmitSpec(repo)

    first = submit.submit(pipeline_id, spec)
    second = submit.submit(pipeline_id, spec)

    assert first.created is True
    assert second.created is False
    assert second.version.version_id == first.version.version_id
    assert len(repo.history[pipeline_id]) == 1


def test_changed_spec_appends_child() -> None:
    pipeline_id = uuid4()
    first_spec = _spec(_orders_spec_yaml(destination="analytics.orders"))
    changed_spec = _spec(_orders_spec_yaml(destination="analytics.orders_v2"))
    repo = FakeSpecVersionRepository()
    submit = SubmitSpec(repo)

    first = submit.submit(pipeline_id, first_spec)
    second = submit.submit(pipeline_id, changed_spec)

    assert second.created is True
    assert second.version.parent_id == first.version.version_id
    assert len(repo.history[pipeline_id]) == 2


def test_revert_appends_new_version_with_recurring_hash() -> None:
    pipeline_id = uuid4()
    spec_a = _spec(_orders_spec_yaml(destination="analytics.orders"))
    spec_b = _spec(_orders_spec_yaml(destination="analytics.orders_v2"))
    repo = FakeSpecVersionRepository()
    submit = SubmitSpec(repo)

    first = submit.submit(pipeline_id, spec_a)
    second = submit.submit(pipeline_id, spec_b)
    third = submit.submit(pipeline_id, spec_a)

    assert third.created is True
    assert third.version.version_id != first.version.version_id
    assert third.version.parent_id == second.version.version_id
    assert third.version.spec_id == first.version.spec_id
    assert len(repo.history[pipeline_id]) == 3
