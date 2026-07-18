import os
import re
import time
import base64
import gspread
from datetime import datetime
from email.mime.text import MIMEText
from dotenv import load_dotenv

from sentence_transformers import SentenceTransformer
import chromadb

# Google Auth and GenAI Imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google import genai

# ---- Setup ----
load_dotenv()

# Initialize the Gemini Client (automatically pulls GEMINI_API_KEY from .env)
ai = genai.Client()
GEMINI_MODEL = "gemini-3.5-flash"

THRESHOLD = 0.40  # calibrated in Day 2 testing — below this, route to SPECIAL

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

embed_model = SentenceTransformer('all-MiniLM-L6-v2')
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="prospectus", metadata={"hnsw:space": "cosine"})

# ---- OAuth Flow for Gmail ----
creds = None
if os.path.exists('token.json'):
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)

if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
    with open('token.json', 'w') as token:
        token.write(creds.to_json())

# ---- Connect to Services ----
gmail = build('gmail', 'v1', credentials=creds)

print("Connecting to Google Sheets via Service Account...")
gc = gspread.service_account(filename='service_account.json')
sheet = gc.open_by_key(os.getenv("SHEET_ID")).sheet1
print("Successfully connected to the spreadsheet!")


def log_to_sheet(subject, sender, similarity, decision, replied):
    sheet.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        subject,
        sender,
        f"{similarity:.2f}",
        decision,
        "Yes" if replied else "No"
    ])


def get_or_create_special_label():
    labels = gmail.users().labels().list(userId='me').execute().get('labels', [])
    for label in labels:
        if label['name'] == 'SPECIAL':
            return label['id']
    new_label = gmail.users().labels().create(
        userId='me', body={'name': 'SPECIAL', 'labelListVisibility': 'labelShow', 'messageListVisibility': 'show'}
    ).execute()
    return new_label['id']


SPECIAL_LABEL_ID = get_or_create_special_label()


def get_unread_emails():
    today_str = datetime.now().strftime("%Y/%m/%d")
    query = f'category:primary after:{today_str}'
    results = gmail.users().messages().list(
        userId='me',
        labelIds=['UNREAD', 'INBOX'],
        q=query
    ).execute()
    return results.get('messages', [])


def get_full_message(msg_id):
    """Fetch the full message once and pull out everything we need — subject,
    sender, snippet, current label IDs, and thread ID — in a single API call.
    The label IDs let us check whether this email was already processed
    (already carries the SPECIAL label) in a previous polling cycle."""
    msg = gmail.users().messages().get(userId='me', id=msg_id, format='full').execute()
    snippet = msg.get('snippet', '')
    sender = next((h['value'] for h in msg['payload']['headers'] if h['name'] == 'From'), '')
    subject = next((h['value'] for h in msg['payload']['headers'] if h['name'] == 'Subject'), '')
    label_ids = msg.get('labelIds', [])
    thread_id = msg.get('threadId')
    return subject, sender, snippet, label_ids, thread_id


def retrieve_context(email_text):
    """Retrieve the top 3 most relevant chunks instead of just 1, so the LLM
    sees a fuller picture of the topic instead of a single random fragment."""
    query_embedding = embed_model.encode([email_text]).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=3)
    chunks = results['documents'][0]
    top_similarity = 1 - results['distances'][0][0]
    combined_context = "\n\n---\n\n".join(chunks)
    return combined_context, top_similarity


def generate_reply(email_text, context):
    prompt = f"""You are an admissions assistant for Foundation University Islamabad.
Using ONLY the context below, write a short, professional reply to the student's email.

IMPORTANT: If the context does not contain enough information to fully and
confidently answer the question, respond with EXACTLY this single line and
nothing else:
INSUFFICIENT_CONTEXT

Do not write a partial answer, do not mention "team member follow up",
do not apologize — just output that exact line if you cannot answer fully.
Otherwise, write the complete, confident reply using only the context given.

Context:
{context}

Student's email:
{email_text}

Reply:"""

    response = ai.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    return response.text

def looks_like_fallback(reply_text):
    """Reliable check: Gemini is instructed to output this exact marker
    when it can't confidently answer from the given context. No more
    guessing at phrases — this is deterministic."""
    return "INSUFFICIENT_CONTEXT" in reply_text.strip()

def send_reply(to, subject, body, thread_id):
    message = MIMEText(body)
    message['to'] = to
    message['subject'] = f"Re: {subject}"
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    gmail.users().messages().send(userId='me', body={'raw': raw, 'threadId': thread_id}).execute()


def apply_special_label(msg_id):
    gmail.users().messages().modify(
        userId='me', id=msg_id, body={'addLabelIds': [SPECIAL_LABEL_ID]}
    ).execute()


def process_emails():
    messages = get_unread_emails()
    print(f"Checking inbox — {len(messages)} unread email(s) found.")

    for m in messages:
        msg_id = m['id']
        subject, sender, email_text, label_ids, thread_id = get_full_message(msg_id)

        # Skip anything already labeled SPECIAL in a previous cycle — it's
        # correctly left unread for staff, but we don't want to keep
        # re-processing and re-logging it forever every 60 seconds.
        if SPECIAL_LABEL_ID in label_ids:
            continue

        context, similarity = retrieve_context(email_text)

        print(f"\nEmail: '{subject}' from {sender}")
        print(f"Similarity: {similarity:.2f}")

        if similarity >= THRESHOLD:
            reply = generate_reply(email_text, context)

            if looks_like_fallback(reply):
                apply_special_label(msg_id)
                print("DECISION: SPECIAL (Gemini declined despite high similarity)")
                log_to_sheet(subject, sender, similarity, "SPECIAL", False)
            else:
                send_reply(sender, subject, reply, thread_id)
                gmail.users().messages().modify(
                    userId='me', id=msg_id, body={'removeLabelIds': ['UNREAD']}
                ).execute()
                print("DECISION: AUTO-REPLIED")
                log_to_sheet(subject, sender, similarity, "AUTO-REPLIED", True)
        else:
            apply_special_label(msg_id)
            print("DECISION: SPECIAL — left for human review")
            log_to_sheet(subject, sender, similarity, "SPECIAL", False)


if __name__ == "__main__":
    print("Admissions bot started. Polling every 60 seconds. Press Ctrl+C to stop.")
    while True:
        process_emails()
        time.sleep(60)
