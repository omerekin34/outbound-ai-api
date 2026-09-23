"""Step 15: yalnızca `valid` outbound için kullanılabilir."""

from api.services.email_verify import (
    STATUS_ACCEPT_ALL,
    STATUS_INVALID,
    STATUS_RISKY,
    STATUS_UNKNOWN,
    STATUS_VALID,
    is_email_usable,
    verify_email,
)


def test_verify_email_rejects_empty_and_syntax() -> None:
    assert verify_email(None, mx_lookup=lambda _: True) == STATUS_INVALID
    assert verify_email("not-an-email", mx_lookup=lambda _: True) == STATUS_INVALID
    assert verify_email("a@b", mx_lookup=lambda _: True) == STATUS_INVALID


def test_verify_email_unknown_without_mx() -> None:
    assert (
        verify_email("deniz@ornekmakina.com.tr", mx_lookup=lambda _: False)
        == STATUS_UNKNOWN
    )


def test_verify_email_personal_with_mx_is_valid() -> None:
    assert (
        verify_email("deniz.korkmaz@ornekmakina.com.tr", mx_lookup=lambda _: True)
        == STATUS_VALID
    )
    assert is_email_usable(STATUS_VALID) is True
    assert is_email_usable(STATUS_ACCEPT_ALL) is False


def test_verify_email_generic_local_is_accept_all() -> None:
    assert (
        verify_email("info@ornekmakina.com.tr", mx_lookup=lambda _: True)
        == STATUS_ACCEPT_ALL
    )


def test_verify_email_disposable_is_risky() -> None:
    assert (
        verify_email("ahmet@mailinator.com", mx_lookup=lambda _: True) == STATUS_RISKY
    )
