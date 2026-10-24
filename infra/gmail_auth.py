"""One-off: mint a Gmail OAuth refresh token for the demo clinic inbox (desktop flow).

Usage: python infra/gmail_auth.py client_secret.json
Prints the refresh token to stdout ONLY; pipe it straight into Secret Manager:
  python infra/gmail_auth.py client_secret.json | gcloud secrets versions add GMAIL_REFRESH_TOKEN --data-file=-
Scopes: gmail.modify, gmail.send. Tokens last ~7 days while the consent screen is in Testing.
"""
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    sys.stdout.write(creds.refresh_token or "")


if __name__ == "__main__":
    main()
