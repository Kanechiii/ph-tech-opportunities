import argparse
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from src.email_sender import send_email


# Load local configuration
load_dotenv()


# Sample opportunities for Phase 1 testing only.
# These are NOT verified current opportunities.
SAMPLE_OPPORTUNITIES = [
    {
        "category": "Certification Voucher",
        "title": "Sample Cloud Certification Voucher",
        "description": "Example of a 100% free exam voucher.",
        "deadline": "To be verified",
    },
    {
        "category": "Tech Event",
        "title": "Sample Philippine Developer Meetup",
        "description": "Example of a free technology workshop.",
        "deadline": "To be verified",
    },
    {
        "category": "Hackathon",
        "title": "Sample Student AI Hackathon",
        "description": "Example of a student hackathon.",
        "deadline": "To be verified",
    },
]


def build_email_content():
    """Generate a sample HTML and plain-text digest."""

    date_today = datetime.now(
        ZoneInfo("Asia/Manila")
    ).strftime("%B %d, %Y")

    subject = (
        "PH Tech Opportunities - Test Notification"
    )

    text_lines = [
        "PH TECH OPPORTUNITIES AUTOMATION",
        f"Date: {date_today}",
        "",
        "PHASE 1 TEST EMAIL - SAMPLE DATA ONLY",
        "",
    ]

    html_items = []

    for opportunity in SAMPLE_OPPORTUNITIES:
        category = escape(opportunity["category"])
        title = escape(opportunity["title"])
        description = escape(opportunity["description"])
        deadline = escape(opportunity["deadline"])

        text_lines.extend([
            category,
            title,
            description,
            f"Deadline: {deadline}",
            "",
        ])

        html_items.append(f"""
        <div style="
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
        ">
            <p style="
                color: #2563eb;
                font-size: 12px;
                font-weight: bold;
            ">{category}</p>

            <h3 style="margin: 8px 0;">
                {title}
            </h3>

            <p>{description}</p>

            <p>
                <strong>Deadline:</strong> {deadline}
            </p>
        </div>
        """)

    text_lines.append(
        "This is an automated development test email."
    )

    html_body = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>PH Tech Opportunities</title>
    </head>

    <body style="
        font-family: Arial, sans-serif;
        background: #f1f5f9;
        padding: 24px;
        color: #0f172a;
    ">
        <div style="
            max-width: 640px;
            margin: auto;
            background: white;
            padding: 24px;
            border-radius: 12px;
        ">

            <h1 style="color: #1d4ed8;">
                PH Tech Opportunities
            </h1>

            <p style="color: #64748b;">
                {date_today}
            </p>

            <p>
                <strong>
                    Phase 1 Development Test
                </strong>
            </p>

            <p>
                The following opportunities are
                fictional examples used to test
                email notification delivery.
            </p>

            {"".join(html_items)}

            <hr>

            <p style="
                font-size: 12px;
                color: #64748b;
            ">
                PH Tech Opportunities Automation
                - Development Mode
            </p>

        </div>
    </body>
    </html>
    """

    text_body = "\n".join(text_lines)

    return subject, text_body, html_body


def main():
    """Application entry point."""

    parser = argparse.ArgumentParser(
        description="PH Tech Opportunities Automation"
    )

    parser.add_argument(
        "--send",
        action="store_true",
        help="Send the test email through SMTP.",
    )

    args = parser.parse_args()

    subject, text_body, html_body = (
        build_email_content()
    )

    print("=" * 50)
    print("PH TECH OPPORTUNITIES AUTOMATION")
    print("=" * 50)

    if not args.send:
        print("MODE: PREVIEW ONLY")
        print()
        print(f"Subject: {subject}")
        print()
        print(text_body)
        print()
        print("No email was sent.")
        print("Use --send to deliver the test email.")
        return

    print("MODE: EMAIL DELIVERY")
    print("Connecting to SMTP server...")

    try:
        send_email(
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )

    except Exception as error:
        print(
            f"Email delivery failed: "
            f"{type(error).__name__}"
        )
        print(
            "Check your configuration, "
            "network connection, and Gmail access."
        )
        raise SystemExit(1) from None

    print("Email successfully submitted to SMTP server.")


if __name__ == "__main__":
    main()