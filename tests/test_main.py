import sys
from unittest.mock import patch

import pytest

from src.main import (
    SAMPLE_OPPORTUNITIES,
    build_email_content,
    main,
)


def test_email_content_generation():
    """Check that the email builder returns valid content."""

    subject, text_body, html_body = (
        build_email_content()
    )

    assert subject == (
        "PH Tech Opportunities - Test Notification"
    )

    assert "PH TECH OPPORTUNITIES" in text_body

    assert "<html" in html_body.lower()
    assert "</html>" in html_body.lower()


def test_all_opportunity_categories_present():
    """Verify that all sample categories appear."""

    _, text_body, html_body = (
        build_email_content()
    )

    expected_categories = [
        "Certification Voucher",
        "Tech Event",
        "Hackathon",
    ]

    for category in expected_categories:
        assert category in text_body
        assert category in html_body


def test_sample_opportunity_count():
    """Check that all three sample records are defined."""

    assert len(SAMPLE_OPPORTUNITIES) == 3


def test_preview_mode_does_not_send_email(
    capsys,
):
    """Confirm preview mode cannot send an email."""

    with patch.object(
        sys, "argv", ["program"]
    ), patch(
        "src.main.send_email"
    ) as mock_send:

        main()

        mock_send.assert_not_called()

    output = capsys.readouterr().out

    assert "MODE: PREVIEW ONLY" in output
    assert "No email was sent." in output


def test_send_mode_calls_email_sender():
    """Check that --send invokes the SMTP sender."""

    with patch.object(
        sys, "argv", ["program", "--send"]
    ), patch(
        "src.main.send_email"
    ) as mock_send:

        main()

        mock_send.assert_called_once()

        kwargs = mock_send.call_args.kwargs

        assert "subject" in kwargs
        assert "text_body" in kwargs
        assert "html_body" in kwargs


def test_send_mode_handles_failure():
    """Confirm that email failures exit with an error."""

    with patch.object(
        sys, "argv", ["program", "--send"]
    ), patch(
        "src.main.send_email",
        side_effect=RuntimeError(
            "Simulated SMTP failure"
        ),
    ):

        with pytest.raises(
            SystemExit
        ) as error:
            main()

        assert error.value.code == 1