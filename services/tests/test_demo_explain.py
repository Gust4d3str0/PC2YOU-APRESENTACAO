import pytest
from services.ai.explain import validate_explanation
from services.ai.errors import ContractViolation


def test_explanation_accepts_paragraphs():
    validate_explanation('O conjunto tem bom equilíbrio.\n\nConfira as verificações do sistema.', '{}')


def test_explanation_rejects_new_price():
    with pytest.raises(ContractViolation):
        validate_explanation('O upgrade custa R$ 500.', '{}')


def test_explanation_rejects_contact_as_contract_error():
    with pytest.raises(ContractViolation):
        validate_explanation('Envie para exemplo@example.com', '{}')
