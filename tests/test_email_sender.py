import smtplib
from unittest.mock import MagicMock, patch

import pytest

from src.email_sender import get_email_config, send_email


@pytest.fixture
def valid_email_config(monkeypatch):
    """Set safe dummy credentials for unit testing."""

    settings = {
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORT": "587",
        "SENDER_EMAIL": "sender@example.com",
        "SENDER_APP_PASSWORD": "dummy_test_password",
        "RECIPIENT_EMAIL": "recipient@example.com",
    }

    for key, value in settings.items():
        monkeypatch.setenv(key, value)

    return settings


def test_get_email_config_success(valid_email_config):
    """Check that valid configuration is loaded."""

    config = get_email_config()

    assert config["SMTP_HOST"] == "smtp.gmail.com"
    assert config["SMTP_PORT"] == 587
    assert config["SENDER_EMAIL"] == "sender@example.com"
    assert config["RECIPIENT_EMAIL"] == "recipient@example.com"


def test_missing_environment_variable(
    valid_email_config, monkeypatch
):
    """Check that missing configuration is rejected."""

    monkeypatch.delenv("SENDER_EMAIL")

    with pytest.raises(
        ValueError,
        match="Missing environment variable: SENDER_EMAIL",
    ):
        get_email_config()


def test_invalid_smtp_port(
    valid_email_config, monkeypatch
):
    """Check that nonnumeric SMTP ports are rejected."""

    monkeypatch.setenv("SMTP_PORT", "invalid")

    with pytest.raises(
        ValueError,
        match="SMTP_PORT must be a valid integer",
    ):
        get_email_config()


def test_unsupported_smtp_port(
    valid_email_config, monkeypatch
):
    """Check that unsupported SMTP ports are rejected."""

    monkeypatch.setenv("SMTP_PORT", "465")

    with pytest.raises(
        ValueError,
        match="requires SMTP port 587",
    ):
        get_email_config()


def test_invalid_email_address(
    valid_email_config, monkeypatch
):
    """Check that obviously invalid addresses are rejected."""

    monkeypatch.setenv("RECIPIENT_EMAIL", "invalid-address")

    with pytest.raises(
        ValueError,
        match="Invalid email address",
    ):
        get_email_config()


def test_placeholder_credentials(
    valid_email_config, monkeypatch
):
    """Check that sample credentials cannot be used."""

    monkeypatch.setenv(
        "SENDER_APP_PASSWORD",
        "your_16_character_app_password",
    )

    with pytest.raises(
        ValueError,
        match="Replace the placeholder values",
    ):
        get_email_config()


def test_send_email_success(valid_email_config):
    """Verify SMTP delivery logic without connecting to Gmail."""

    with patch(
        "src.email_sender.smtplib.SMTP"
    ) as mock_smtp:

        mock_server = MagicMock()

        mock_smtp.return_value.__enter__.return_value = (
            mock_server
        )

        result = send_email(
            subject="Test Subject",
            text_body="Plain text test",
            html_body="<h1>HTML Test</h1>",
        )

        assert result is True

        mock_smtp.assert_called_once_with(
            "smtp.gmail.com",
            587,
            timeout=30,
        )

        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with(
            "sender@example.com",
            "dummy_test_password",
        )

        mock_server.send_message.assert_called_once()

        message = (
            mock_server.send_message.call_args.args[0]
        )

        assert message["Subject"] == "Test Subject"
        assert message["From"] == "sender@example.com"
        assert message["To"] == "recipient@example.com"

        assert message.is_multipart()


def test_send_email_authentication_failure(
    valid_email_config,
):
    """Check that SMTP authentication errors propagate."""

    with patch(
        "src.email_sender.smtplib.SMTP"
    ) as mock_smtp:

        mock_server = MagicMock()

        mock_smtp.return_value.__enter__.return_value = (
            mock_server
        )

        mock_server.login.side_effect = (
            smtplib.SMTPAuthenticationError(
                535,
                b"Authentication failed",
            )
        )

        with pytest.raises(
            smtplib.SMTPAuthenticationError
        ):
            send_email(
                subject="Test Subject",
                text_body="Test",
                html_body="<p>Test</p>",
            )

        mock_server.send_message.assert_not_called()