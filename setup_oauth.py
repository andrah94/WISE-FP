#!/usr/bin/env python3
"""
OAuth Setup Script for Gmail and Google Calendar.
Run this locally to generate tokens for each account.

Usage:
    python setup_oauth.py <client_secrets.json>

This will guide you through OAuth setup for:
- gwindom2@gmail.com
- gwindomfinance@gmail.com
- Wisefinancialpartners@gmail.com
- Google Calendar
"""

import sys
import json
import os

from google_auth_oauthlib.flow import InstalledAppFlow

# Scopes needed
GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
CALENDAR_SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

# Email accounts to set up
EMAIL_ACCOUNTS = [
    ('gwindom2', 'gwindom2@gmail.com', 'GMAIL_TOKEN_GWINDOM2'),
    ('gwindomfinance', 'gwindomfinance@gmail.com', 'GMAIL_TOKEN_GWINDOMFINANCE'),
    ('wisefinancial', 'Wisefinancialpartners@gmail.com', 'GMAIL_TOKEN_WISEFINANCIAL'),
]


def run_oauth(client_secrets_file, scopes, account_name, port=8090):
    """Run OAuth flow and return token JSON."""
    print(f"\n{'='*60}")
    print(f"Setting up OAuth for: {account_name}")
    print(f"{'='*60}")
    print("\nA browser window will open.")
    print(f"Make sure to sign in with: {account_name}")
    print("\nPress Enter to continue...")
    input()

    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, scopes)
    creds = flow.run_local_server(port=port)

    token_data = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': list(creds.scopes)
    }

    return json.dumps(token_data)


def main():
    if len(sys.argv) < 2:
        print("Usage: python setup_oauth.py <client_secrets.json>")
        print("\nTo get client_secrets.json:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a new project or select existing")
        print("3. Enable Gmail API and Google Calendar API")
        print("4. Go to Credentials → Create Credentials → OAuth client ID")
        print("5. Choose 'Desktop app'")
        print("6. Download the JSON file")
        sys.exit(1)

    client_secrets_file = sys.argv[1]

    if not os.path.exists(client_secrets_file):
        print(f"Error: File not found: {client_secrets_file}")
        sys.exit(1)

    print("\n" + "="*60)
    print("Financial Dashboard OAuth Setup")
    print("="*60)
    print("\nThis script will help you set up OAuth tokens for:")
    print("  - 3 Gmail accounts")
    print("  - Google Calendar")
    print("\nYou'll need to sign into each account in your browser.")
    print("\nIMPORTANT: Make sure you're signed into the CORRECT account")
    print("in your browser before authorizing each one!")

    tokens = {}

    # Set up Gmail accounts
    print("\n" + "-"*60)
    print("GMAIL ACCOUNTS")
    print("-"*60)

    port = 8090
    for key, email, env_var in EMAIL_ACCOUNTS:
        try:
            token_json = run_oauth(client_secrets_file, GMAIL_SCOPES, email, port)
            tokens[env_var] = token_json
            port += 1
            print(f"\n✅ {email} - Token generated successfully!")
        except Exception as e:
            print(f"\n❌ {email} - Error: {e}")
            continue

    # Set up Google Calendar
    print("\n" + "-"*60)
    print("GOOGLE CALENDAR")
    print("-"*60)

    try:
        # Usually use the primary email for calendar
        token_json = run_oauth(client_secrets_file, CALENDAR_SCOPES,
                               "your primary Google account", port)
        tokens['GOOGLE_CALENDAR_TOKEN'] = token_json
        print("\n✅ Google Calendar - Token generated successfully!")
    except Exception as e:
        print(f"\n❌ Google Calendar - Error: {e}")

    # Output all tokens
    print("\n" + "="*60)
    print("SETUP COMPLETE!")
    print("="*60)
    print("\nAdd these environment variables to Railway:\n")

    for env_var, token_json in tokens.items():
        print(f"\n{env_var}=")
        print(token_json)

    # Save to file for easy copy
    output_file = 'oauth_tokens.json'
    with open(output_file, 'w') as f:
        json.dump(tokens, f, indent=2)

    print(f"\n\nTokens also saved to: {output_file}")
    print("\n⚠️  IMPORTANT: Keep these tokens secure!")
    print("    Do not commit them to version control.")
    print("\nTo add to Railway:")
    print("1. Go to your Railway project")
    print("2. Go to Variables")
    print("3. Add each variable above")


if __name__ == '__main__':
    main()
