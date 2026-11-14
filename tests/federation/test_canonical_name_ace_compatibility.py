"""Current Python codec behavior, not selection of a normative federation IDNA profile.

Keep edition-sensitive cases explicit when an approved profile change is made.
These isolate name validation from unrelated service-ID/signature failures.
"""
import pytest

from nbsr.federation.fields import FederationValidationError, _delegation_scope
from nbsr.federation.ownership import _canonical_name


@pytest.mark.parametrize("name,accepted", [
    ("xn--a.example", False),
    ("xn--fa-hia.example", False),
    ("xn--bcher-kva.example", True),
    ("xn--invalid.example", True),
])
@pytest.mark.parametrize("scope", [False, True], ids=["ownership", "delegation"])
def test_current_python_ace_acceptance_isolated_from_other_fields(name, accepted, scope):
    def validate(value):
        if scope:
            _delegation_scope({1: value, 2: None, 3: None, 4: None, 5: None,
                               6: None, 7: [], 8: [1], 9: [1], 10: False, 11: 0})
        else:
            assert _canonical_name(value) == value

    validate("service.example")  # Non-name fields cannot mask the result.
    if accepted:
        validate(name)
    else:
        with pytest.raises(FederationValidationError):
            validate(name)
