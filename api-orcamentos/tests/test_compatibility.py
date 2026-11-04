from compatibility import check_components
from test_api import component


def test_ram_quantity_respects_motherboard_slots():
    motherboard = component("motherboard", "motherboard")
    ram = component("ram", "ram")
    result = check_components([motherboard, ram], {"ram": 5})
    assert result["compatible"] is False
    assert "5 slots" in result["errors"][0]


def test_kit_quantity_counts_modules_without_changing_quantity_contract():
    motherboard = component("motherboard", "motherboard")
    kit = component("kit", "kit-ram")
    assert check_components([motherboard, kit], {"kit": 2})["compatible"] is True
    result = check_components([motherboard, kit], {"kit": 3})
    assert result["compatible"] is False
    assert "6 slots" in result["errors"][0]
