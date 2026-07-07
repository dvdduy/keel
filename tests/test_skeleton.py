import importlib
import pytest


@pytest.mark.parametrize(
    "module_name",
    ["keel", "keel.domain", "keel.application", "keel.adapters", "keel.entrypoints"],
)
def test_layers_importable(module_name: str) -> None:
    importlib.import_module(module_name)
