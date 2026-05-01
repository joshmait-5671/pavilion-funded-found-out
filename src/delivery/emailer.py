"""Send the weekly Funded & Found Out report via Gmail API."""
import base64
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly',
]


SEND_TOKEN_LABEL = 'personal'


def get_gmail_service(auth_dir: Path):
    """Authenticate and return Gmail API service for the send-from account."""
    token_path = auth_dir / f'token-{SEND_TOKEN_LABEL}.json'
    secrets_path = auth_dir / 'client_secrets.json'

    # Backwards compat: pre-multi-account installs used a single token.json
    if not token_path.exists() and (auth_dir / 'token.json').exists():
        token_path = auth_dir / 'token.json'

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(str(token_path), 'w') as f:
            f.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


def send_report(
    pdf_path: Path,
    auth_dir: Path,
    to_email: str,
    from_email: str,
    company_names: list[str],
) -> bool:
    """Send the weekly carousel PDF to the recipient."""
    try:
        service = get_gmail_service(auth_dir)

        date_str = datetime.now().strftime("%B %d, %Y")
        names_str = ', '.join(company_names)

        subject = f"Funded & Found Out — {date_str}"

        body = f"""Hey Josh,

Your weekly Funded & Found Out report is attached and ready for Thursday.

This week's companies: {names_str}

The PDF is formatted as a LinkedIn carousel. Upload it directly to a LinkedIn post as a document — LinkedIn will auto-render it as a swipeable carousel.

—
Funded & Found Out Bot 🤖
"""

        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        with open(pdf_path, 'rb') as f:
            attachment = MIMEBase('application', 'pdf')
            attachment.set_payload(f.read())
            encoders.encode_base64(attachment)
            attachment.add_header(
                'Content-Disposition',
                f'attachment; filename="{pdf_path.name}"',
            )
            msg.attach(attachment)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()

        logger.info(f"Report sent: {pdf_path.name} → {to_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send report: {e}")
        return False


def send_curation_prompt(
    auth_dir: Path,
    to_email: str,
    from_email: str,
    candidates: list[dict],
    minimum: int,
) -> bool:
    """
    Sent on Monday when discovery returned fewer than `minimum` qualified
    companies. Lists what was found so Josh can curate manually.
    """
    try:
        service = get_gmail_service(auth_dir)
        date_str = datetime.now().strftime("%B %d, %Y")

        if candidates:
            lines = []
            for c in candidates:
                lines.append(
                    f"  · {c.get('company_name','?')} — "
                    f"${c.get('funding_amount','?')}M {c.get('funding_stage','')} — "
                    f"{c.get('website_url','')}"
                )
                if c.get('description'):
                    lines.append(f"    {c['description'][:140]}")
            candidates_block = "\n".join(lines)
        else:
            candidates_block = "  (no qualifying funding rounds found this week)"

        subject = f"FFO Monday: only {len(candidates)} candidate(s) this week — curate or skip"
        body = f"""Hey Josh,

Discovery ran Monday {date_str}. The qualifier returned {len(candidates)} qualifying funding round(s) — below the {minimum}-company floor for an episode.

What we found:
{candidates_block}

To ship this week, edit data/episodes/{datetime.now().strftime('%Y-%m-%d')}.json with the 5 companies you want
(use the candidates above, drop in your own picks, or both), then run:

  cd /Users/joshmait/Desktop/Claude/pavilion/funded-and-found-out
  .venv/bin/python scripts/render_episode.py data/episodes/{datetime.now().strftime('%Y-%m-%d')}.json

To skip the week, do nothing. The Wednesday delivery cron checks for a fresh PDF in output/ —
no PDF, no send.

—
Funded & Found Out Bot 🤖
"""
        msg = MIMEText(body, 'plain')
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()

        logger.info(f"Curation prompt sent → {to_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send curation prompt: {e}")
        return False
