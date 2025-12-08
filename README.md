# Financial Operations Dashboard

Auto-updating dashboard that syncs data from Gmail, Google Calendar, and Calendly to track your financial services pipeline.

## Features

- **Multi-Email Sync**: Monitors 3 Gmail accounts for applications and status updates
- **Calendar Integration**: Tracks meetings from Google Calendar
- **Calendly Integration**: Captures booking information and attendee details
- **Smart Parsing**: Automatically extracts names, policy numbers, face amounts from emails
- **Auto-Pipeline**: New people are automatically added when applications arrive
- **Live Dashboard**: Professional dark-themed dashboard with real-time metrics
- **Commission Tracking**: Estimates commissions and weighted pipeline values

## Setup

### 1. Google Cloud Console Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (e.g., "Financial Dashboard")
3. Enable APIs:
   - Gmail API
   - Google Calendar API
4. Configure OAuth consent screen:
   - User Type: External
   - Add scopes: `gmail.readonly`, `calendar.readonly`
5. Create OAuth 2.0 credentials:
   - Application type: Desktop app
   - Download the JSON file as `client_secrets.json`

### 2. Generate OAuth Tokens

```bash
# Install dependencies locally
pip install google-auth-oauthlib google-api-python-client

# Run OAuth setup
python setup_oauth.py client_secrets.json
```

Follow the prompts to authorize each Gmail account and calendar.

### 3. Get Calendly API Key

1. Go to [Calendly Integrations](https://calendly.com/integrations)
2. Navigate to API & Webhooks
3. Create a Personal Access Token
4. Copy the token

### 4. Deploy to Railway

1. Create a new Railway project
2. Add PostgreSQL database
3. Connect your GitHub repo
4. Set environment variables:

```
DATABASE_URL=<auto-set by Railway>
GMAIL_TOKEN_GWINDOM2=<token from setup>
GMAIL_TOKEN_GWINDOMFINANCE=<token from setup>
GMAIL_TOKEN_WISEFINANCIAL=<token from setup>
GOOGLE_CALENDAR_TOKEN=<token from setup>
CALENDLY_API_KEY=<your Calendly API key>
PORT=8080
UPDATE_INTERVAL_MINUTES=15
```

5. Deploy!

## Email Accounts

- gwindom2@gmail.com
- gwindomfinance@gmail.com
- Wisefinancialpartners@gmail.com

## API Endpoints

- `GET /` - Main dashboard
- `GET /health` - Health check
- `GET /api/status` - Sync status for all sources
- `GET /api/people` - All people in pipeline
- `GET /api/person/<id>` - Detailed person info
- `POST /api/refresh` - Trigger manual refresh

## Architecture

```
main.py                 - Flask app + scheduler
email_scanner.py        - Gmail API integration
calendar_scanner.py     - Google Calendar API
calendly_scanner.py     - Calendly API
parsers.py             - Email/event parsing
database.py            - SQLAlchemy models
dashboard_generator.py - HTML generation
utils.py               - Helper functions
setup_oauth.py         - OAuth setup script
```

## Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your tokens

# Run locally
python main.py
```

## License

Private - Glenn Windom
