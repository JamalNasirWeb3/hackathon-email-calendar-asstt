import google.generativeai as genai
import os.path
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os
import json
import re
import json
from textblob import TextBlob

SCOPES = ["https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/gmail.send"]

from googleapiclient.discovery import build

# ...

def authenticate_gmail():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    # ✅ RETURN THE SERVICE, NOT JUST CREDENTIALS
    return build("gmail", "v1", credentials=creds)





def is_urgent_email(email):
    """Detect if an email is urgent based on keywords (case-insensitive)."""
    urgent_keywords = ["urgent", "asap", "immediate", "deadline", "time-sensitive"]
    
    # Ensure body is a valid string
    email_body = email.get("body", "").lower().strip()

    # Check using regex to catch word boundaries
    for keyword in urgent_keywords:
        if re.search(rf"\b{keyword}\b", email_body, re.IGNORECASE):
            return True
    return False


def is_frustrated_sender(email):
    """Detect if the sender is frustrated or upset based on sentiment analysis."""
    blob = TextBlob(email["body"])
    sentiment = blob.sentiment.polarity
    # Negative sentiment threshold
    return sentiment < -0.3


def detect_commitments(email):
    """Detect commitments made in the email."""
    commitment_keywords = ["i will", "promise", "commit", "ensure", "follow up"]
    commitments = []
    for keyword in commitment_keywords:
        if keyword in email["body"].lower():
            commitments.append(keyword)
    return commitments

# Function to detect positive feedback
def is_positive_feedback(email):
    """Detect positive feedback or congratulatory emails."""
    positive_keywords = ["congratulations", "great job", "well done", "thank you"]
    for keyword in positive_keywords:
        if keyword in email["body"].lower():
            return True
    return False

# Function to flag and prioritize emails
def flag_and_prioritize_email(email):
    flags = []
    email_body = email.get("body", "")

    if not email_body:
        print(f"⚠️ Email ID {email.get('id')} has no body.")
        return flags

    print(f"\nEmail ID: {email.get('id')}")
    print(f"Extracted Email Body:\n{email_body}\n")

    if is_urgent_email(email):
        flags.append("URGENT")
    if is_frustrated_sender(email):
        flags.append("FRUSTRATED SENDER")
    commitments = detect_commitments(email)
    if commitments:
        flags.append(f"COMMITMENTS: {', '.join(commitments)}")
    if is_positive_feedback(email):
        flags.append("POSITIVE FEEDBACK")

    return flags





def load_recipients():
    """Load recipient information from recipients.json."""
    with open("recipients.json", "r") as file:
        return json.load(file)

# Ensure folders exist based on recipient information
def ensure_folders_exist(recipients):
    """Ensure folders exist for each recipient."""
    for folder_name in recipients.keys():
        if not os.path.exists(folder_name):
            os.makedirs(folder_name)

# Check if an email belongs to a specific recipient
def get_email_folder(email, recipients):
    """Determine which folder an email belongs to based on the recipient."""
    for folder_name, domains in recipients.items():
        for domain in domains:
            if domain in email["from"].lower():
                return folder_name
    return None

# Save email to the appropriate folder
def save_email_to_folder(email, folder_name):
    """Save the email content to a file in the specified folder."""
    filename = f"{folder_name}/email_{email['id']}.txt"
    with open(filename, "w", encoding="utf-8") as file:
        file.write(f"From: {email['from']}\n")
        file.write(f"Subject: {email['subject']}\n")
        file.write(f"Body:\n{email['body']}\n")

# Authenticate with Gmail API
def authenticate_gmail():
    """Authenticate with Gmail API using OAuth 2.0."""
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return creds

# Fetch emails from Gmail
def fetch_emails(service, max_results=10):
    """Fetch emails from the user's Gmail inbox."""
    # Don't overwrite 'service' here!
    results = service.users().messages().list(userId="me", maxResults=max_results).execute()
    messages = results.get("messages", [])
    emails = []

    recipients = load_recipients()
    ensure_folders_exist(recipients)

    for message in messages:
        msg = service.users().messages().get(userId="me", id=message["id"]).execute()
        email_data = {
            "id": msg["id"],
            "subject": next((header["value"] for header in msg["payload"]["headers"] if header["name"] == "Subject"), "No Subject"),
            "from": next((header["value"] for header in msg["payload"]["headers"] if header["name"] == "From"), "Unknown Sender"),
            "snippet": msg.get("snippet", ""),
            "body": get_email_body(msg["payload"]),
            "flags": flag_and_prioritize_email(msg)
        }
        emails.append(email_data)

    return emails

# Extract email body from payload
import base64

def get_email_body(payload):
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain" and "data" in part["body"]:
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
        for part in payload["parts"]:
            if part.get("mimeType") == "text/html" and "data" in part["body"]:
                html_body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                return strip_html_tags(html_body)  # convert HTML to text
    elif "body" in payload and "data" in payload["body"]:
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
    return ""
import re

def strip_html_tags(html):
    return re.sub('<[^<]+?>', '', html).strip()



# Summarize email content using Gemini
def summarize_email(text):
    """Summarize email content using Gemini."""
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(f"Summarize the following email in 2-3 sentences:\n\n{text}")
    return response.text

#": summary,
#         })

#     # Render the template with summarized emails
#     return render_template("index.html", emails=summarized_emails)




