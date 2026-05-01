#!/usr/bin/env python3
"""
Per-account Gmail auth.

FFO scans multiple Gmail accounts (personal for newsletters, 100yards for
GTM newsletters, pavilion for the send-from address). Each account gets its
own token file: auth/token-<label>.json.

The send-from account is the only one that needs `gmail.send` scope; all
others only need `gmail.readonly`. We grant both to every token for
simplicity — refresh tokens stay long-lived either way.

Usage:
    python scripts/auth_gmail.py <label>

Examples:
    python scripts/auth_gmail.py personal     → auth/token-personal.json
    python scripts/auth_gmail.py 100yards     → auth/token-100yards.json
    python scripts/auth_gmail.py pavilion     → auth/token-pavilion.json
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from google_auth_oauthlib.flow import InstalledAppFlow

BASE_DIR = Path(__file__).parent.parent
AUTH_DIR = BASE_DIR / 'auth'

SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly',
]


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/auth_gmail.py <label>")
        print("Example: python scripts/auth_gmail.py personal")
        sys.exit(1)

    label = sys.argv[1].lower().strip()
    if not label.replace('-', '').replace('_', '').isalnum():
        print("Label must be alphanumeric (with - or _ allowed).")
        sys.exit(1)

    secrets_path = AUTH_DIR / 'client_secrets.json'
    token_path = AUTH_DIR / f'token-{label}.json'

    if not secrets_path.exists():
        print(f"❌ Missing: {secrets_path}")
        sys.exit(1)

    if token_path.exists():
        print(f"Removing old token: {token_path}")
        token_path.unlink()

    print(f"Opening browser. Choose the Google account for '{label}'.")
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
    creds = flow.run_local_server(port=0)

    with open(str(token_path), 'w') as f:
        f.write(creds.to_json())

    # Verify which account got authorized
    from googleapiclient.discovery import build
    svc = build('gmail', 'v1', credentials=creds, cache_discovery=False)
    prof = svc.users().getProfile(userId='me').execute()

    print(f"✓ Token written: {token_path}")
    print(f"  Authorized as: {prof.get('emailAddress')}")
    print(f"  Total messages: {prof.get('messagesTotal')}")


if __name__ == '__main__':
    main()
