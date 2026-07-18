import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

creds = None

# If token.json already exists, reuse it instead of logging in again
if os.path.exists('token.json'):
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)

# If no valid credentials, run the login flow
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)

    # Save the credentials for next time
    with open('token.json', 'w') as token_file:
        token_file.write(creds.to_json())

service = build('gmail', 'v1', credentials=creds)
results = service.users().labels().list(userId='me').execute()
labels = results.get('labels', [])

print("SUCCESS — Gmail API access confirmed.")
print("Labels found:", [label['name'] for label in labels])