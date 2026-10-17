"""
tests/test_validator.py — Unit tests for URL validation and SSRF protection.

All tests are self-contained and do not require network access.
"""

import pytest
from scraper.validator import (
    URLValidationError,
    is_valid_email,
    is_valid_phone,
    normalise_domain,
    validate_url,
)


class TestValidateURL:
    """URL validation and SSRF protection tests."""

    def test_valid_http_url(self):
        url = validate_url("http://example.com", resolve_ip=False)
        assert url.startswith("http://")

    def test_valid_https_url(self):
        url = validate_url("https://www.morphogenesis.org/about", resolve_ip=False)
        assert "morphogenesis.org" in url

    def test_strips_fragment(self):
        url = validate_url("https://example.com/page#section", resolve_ip=False)
        assert "#" not in url

    def test_lowercases_scheme(self):
        url = validate_url("HTTPS://Example.com", resolve_ip=False)
        assert url.startswith("https://")

    def test_rejects_ftp_scheme(self):
        with pytest.raises(URLValidationError, match="scheme"):
            validate_url("ftp://example.com", resolve_ip=False)

    def test_rejects_file_scheme(self):
        with pytest.raises(URLValidationError, match="scheme"):
            validate_url("file:///etc/passwd", resolve_ip=False)

    def test_rejects_javascript_scheme(self):
        with pytest.raises(URLValidationError, match="scheme"):
            validate_url("javascript:alert(1)", resolve_ip=False)

    def test_rejects_empty_string(self):
        with pytest.raises(URLValidationError):
            validate_url("", resolve_ip=False)

    def test_rejects_no_hostname(self):
        with pytest.raises(URLValidationError, match="hostname"):
            validate_url("https://", resolve_ip=False)

    def test_rejects_localhost(self):
        with pytest.raises(URLValidationError):
            validate_url("http://localhost/admin", resolve_ip=False)

    def test_rejects_metadata_endpoint(self):
        with pytest.raises(URLValidationError):
            validate_url("http://metadata.google.internal/", resolve_ip=False)

    def test_rejects_private_ip_10(self):
        with pytest.raises(URLValidationError, match="private"):
            validate_url("http://10.0.0.1/", resolve_ip=False)

    def test_rejects_private_ip_192_168(self):
        with pytest.raises(URLValidationError, match="private"):
            validate_url("http://192.168.1.100/", resolve_ip=False)

    def test_rejects_private_ip_172_16(self):
        with pytest.raises(URLValidationError, match="private"):
            validate_url("http://172.16.5.5/", resolve_ip=False)

    def test_rejects_loopback(self):
        with pytest.raises(URLValidationError, match="private"):
            validate_url("http://127.0.0.1/", resolve_ip=False)

    def test_rejects_link_local(self):
        with pytest.raises(URLValidationError, match="private"):
            validate_url("http://169.254.169.254/latest/meta-data/", resolve_ip=False)

    def test_url_too_long(self):
        with pytest.raises(URLValidationError, match="length"):
            validate_url("https://example.com/" + "a" * 2048, resolve_ip=False)


class TestNormaliseDomain:
    def test_strips_www(self):
        assert normalise_domain("https://www.example.com/page") == "example.com"

    def test_no_www(self):
        assert normalise_domain("https://example.com/") == "example.com"

    def test_lowercases(self):
        assert normalise_domain("https://EXAMPLE.COM") == "example.com"

    def test_subdomain_preserved(self):
        result = normalise_domain("https://blog.example.com/")
        assert result == "blog.example.com"


class TestEmailValidator:
    def test_valid_email(self):
        assert is_valid_email("info@morphogenesis.org")

    def test_valid_email_with_plus(self):
        assert is_valid_email("contact+arch@studio.in")

    def test_invalid_no_at(self):
        assert not is_valid_email("notanemail")

    def test_invalid_no_domain(self):
        assert not is_valid_email("user@")

    def test_empty(self):
        assert not is_valid_email("")

    def test_image_extension_rejected(self):
        # The extractor filters these; validator just checks format
        assert not is_valid_email("logo.png")


class TestPhoneValidator:
    def test_valid_indian_mobile(self):
        assert is_valid_phone("+91 98765 43210")

    def test_valid_10_digit(self):
        assert is_valid_phone("9876543210")

    def test_valid_with_dashes(self):
        assert is_valid_phone("022-2345-6789")

    def test_too_short(self):
        assert not is_valid_phone("12345")

    def test_empty(self):
        assert not is_valid_phone("")

    def test_alpha_rejected(self):
        assert not is_valid_phone("CALL-NOW")
