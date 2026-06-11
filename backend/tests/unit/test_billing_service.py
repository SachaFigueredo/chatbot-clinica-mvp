"""Unit tests for BillingService — Mercado Pago billing operations.

Tests focus on pure logic that can be verified without HTTP calls:
- Webhook signature verification
- (MP API calls are tested via integration tests with mocking)
"""

import hashlib
import hmac

import pytest

from app.domain.services.billing_service import BillingService


class TestVerifyWebhookSignature:
    """BillingService.verify_webhook_signature validates MP X-Signature."""

    def test_valid_signature_returns_true(self):
        """Given a correctly computed signature, verification returns True."""
        # Arrange: compute a valid signature
        secret = "test-webhook-secret"
        body = b'{"action":"payment.created","data":{"id":"123"}}'
        ts = "1700000000"
        request_id = "req-abc-123"

        template = (
            f"id:{request_id};request-id:{request_id};ts:{ts};"
        )
        data_to_sign = template + body.decode("utf-8")
        expected_hash = hmac.new(
            key=secret.encode("utf-8"),
            msg=data_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        x_signature = f"ts={ts},v1={expected_hash}"

        result = BillingService.verify_webhook_signature(
            body=body,
            x_signature=x_signature,
            x_request_id=request_id,
            webhook_secret=secret,
        )

        assert result is True

    def test_invalid_signature_returns_false(self):
        """Given an incorrect signature, verification returns False."""
        body = b'{"action":"payment.created"}'
        x_signature = "ts=1700000000,v1=invalidhash"
        request_id = "req-abc-123"
        secret = "test-webhook-secret"

        result = BillingService.verify_webhook_signature(
            body=body,
            x_signature=x_signature,
            x_request_id=request_id,
            webhook_secret=secret,
        )

        assert result is False

    def test_empty_signature_returns_false(self):
        """Given an empty X-Signature header, verification returns False."""
        result = BillingService.verify_webhook_signature(
            body=b"{}",
            x_signature="",
            x_request_id="req-1",
            webhook_secret="secret",
        )
        assert result is False

    def test_malformed_signature_returns_false(self):
        """Given a signature missing ts or v1, verification returns False."""
        result = BillingService.verify_webhook_signature(
            body=b"{}",
            x_signature="invalid-format-no-equals",
            x_request_id="req-1",
            webhook_secret="secret",
        )
        assert result is False

    def test_different_secret_fails(self):
        """Using a different secret than the one used to sign fails."""
        body = b'{"action":"payment.approved"}'
        ts = "1700000000"
        request_id = "req-xyz"

        template = f"id:{request_id};request-id:{request_id};ts:{ts};"
        data_to_sign = template + body.decode("utf-8")
        valid_hash = hmac.new(
            key=b"correct-secret",
            msg=data_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        x_signature = f"ts={ts},v1={valid_hash}"

        result = BillingService.verify_webhook_signature(
            body=body,
            x_signature=x_signature,
            x_request_id=request_id,
            webhook_secret="wrong-secret",
        )

        assert result is False
