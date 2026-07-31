"""Thai NGIS fetches must run over a verified TLS channel (D-01 / H-1).

The real-data module previously disabled certificate verification for all
Thai NGIS/GISTDA ArcGIS requests. Authoritative administrative boundaries and
river networks were therefore fetched over an unauthenticated channel, so a
MITM could substitute geometry and silently corrupt HAND, susceptibility, and
every zonal aggregate downstream.

These tests are offline and assert the *configuration*, not connectivity, so
they cannot be skipped by a sandbox with no network. The network probe that
established the chain is genuinely valid lives in the module docstring of
``real_data`` rather than in the suite, because a test that needs the internet
would be skipped exactly when it matters.
"""

from __future__ import annotations

import ssl

from geoai_runner.realpipeline import real_data


def test_ngis_ssl_context_verifies_certificates() -> None:
    """The shared context must not have verification disabled."""

    assert real_data._SSL.verify_mode == ssl.CERT_REQUIRED, (
        "TLS verification is disabled for Thai NGIS fetches. Provenance cannot "
        "be claimed over an unauthenticated channel. If the certificate chain "
        "has broken, pin the CA explicitly instead of restoring CERT_NONE."
    )
    assert real_data._SSL.check_hostname is True, (
        "Hostname checking is disabled for Thai NGIS fetches, so any valid "
        "certificate for any host would be accepted."
    )


def test_source_module_does_not_disable_verification() -> None:
    """Guard against the flags being re-disabled anywhere in the module.

    Checks source text so a reviewer sees the intent even if the context object
    is later rebuilt or replaced.
    """

    from pathlib import Path

    source = Path(real_data.__file__).read_text(encoding="utf-8")

    offenders = [
        line.strip()
        for line in source.splitlines()
        if ("CERT_NONE" in line or "check_hostname = False" in line)
        and not line.lstrip().startswith("#")
    ]
    assert not offenders, f"TLS verification disabled in real_data.py: {offenders}"
