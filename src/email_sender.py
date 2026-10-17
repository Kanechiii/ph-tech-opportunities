import os
import smtplib
import ssl

from email.message import EmailMessage


def get_email_config():
    """Read and validate SMTP configuration."""

    required = [
        "SMTP_HOST",
        "SMTP_PORT",
        "SENDER_EMAIL",
        "SENDER_APP_PASSWORD",
        "RECIPIENT_EMAIL",
    ]

    config = {}

    for key in required:
        value = os.getenv(key, "").strip()

        if not value:
            raise ValueError(f"Missing environment variable: {key}")

        config[key] = value

    try:
        config["SMTP_PORT"] = int(config["SMTP_PORT"])
    except ValueError as exc:
        raise ValueError(
            "SMTP_PORT must be a valid integer."
        ) from exc

    if not 1 <= config["SMTP_PORT"] <= 65535:
        raise ValueError("SMTP_PORT is out of range.")

    if config["SMTP_PORT"] != 587:
        raise ValueError(
            "This version requires SMTP port 587 (STARTTLS)."
        )

    for key in ["SENDER_EMAIL", "RECIPIENT_EMAIL"]:
        if "@" not in config[key]:
            raise ValueError(f"Invalid email address: {key}")

    if (
        config["SENDER_EMAIL"] == "your_email@gmail.com"
        or config["RECIPIENT_EMAIL"] == "your_email@gmail.com"
        or config["SENDER_APP_PASSWORD"] == "your_16_character_app_password"
    ):
        raise ValueError(
            "Replace the placeholder values in your .env file."
        )

    return config


def send_email(subject, text_body, html_body):
    """Send a multipart email through Gmail SMTP."""

    config = get_email_config()

    message = EmailMessage()

    message["From"] = config["SENDER_EMAIL"]
    message["To"] = config["RECIPIENT_EMAIL"]
    message["Subject"] = subject

    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    secure_context = ssl.create_default_context()

    with smtplib.SMTP(
        config["SMTP_HOST"],
        config["SMTP_PORT"],
        timeout=30,
    ) as server:

        server.ehlo()
        server.starttls(context=secure_context)
        server.ehlo()

        server.login(
            config["SENDER_EMAIL"],
            config["SENDER_APP_PASSWORD"],
        )

        server.send_message(message)

    return True