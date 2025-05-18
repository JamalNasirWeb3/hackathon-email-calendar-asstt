import gradio as gr
import dateutil.parser
from datetime import datetime, timedelta
import calendar
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from calendar_utils import create_event, fetch_busy_slots, find_available_slots, get_week_date_range,reschedule_event,cancel_event
from nlp_parser import parse_user_input
from email_utils import fetch_emails, summarize_email,save_email_to_folder, authenticate_gmail
import os
import google.generativeai as genai
import speech_recognition as sr
import tempfile

from db import init_db, save_meeting, fetch_meetings
init_db()  # Call once at startup
if os.getenv("GEMINI_API_KEY"):
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Global Memory
meeting_history = []
proposed_slots_memory = []
proposed_participants_memory = []

# Google Calendar Setup
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
   
    "https://www.googleapis.com/auth/gmail.modify", 
    "https://www.googleapis.com/auth/gmail.send"]


creds = Credentials.from_authorized_user_file('token.json', SCOPES)
service = build('calendar', 'v3', credentials=creds)
service_mail = build('gmail', 'v1', credentials=creds)

# def speech_to_text(audio):
#     recognizer = sr.Recognizer()
#     with tempfile.NamedTemporaryFile(delete=True, suffix=".wav") as temp_audio:
#         temp_audio.write(audio)
#         temp_audio.flush()
#         with sr.AudioFile(temp_audio.name) as source:
#             audio_data = recognizer.record(source)
#             try:
#                 return recognizer.recognize_google(audio_data)
#             except sr.UnknownValueError:
#                 return "❌ Could not understand audio."
#             except sr.RequestError as e:
#                 return f"❌ API error: {str(e)}"

            
# def handle_voice(audio_file_path):
#     recognizer = sr.Recognizer()
#     try:
#         with sr.AudioFile(audio_file_path) as source:
#             audio = recognizer.record(source)
#         command_text = recognizer.recognize_google(audio)
#         response = chatbot_response(command_text, [])
#         return command_text, response
#     except Exception as e:
#         return "Voice recognition failed", f"❌ {str(e)}"

# Helper Functions
def get_dynamic_year(target_month_name):
    target_month_num = list(calendar.month_name).index(target_month_name)
    today = datetime.now()
    current_month = today.month
    current_year = today.year

    # Infer next year only if month has passed
    return current_year + 1 if target_month_num < current_month else current_year


# from datetime import datetime
# import dateutil.parser

# def parse_with_correct_year(date_str):
#     dt = dateutil.parser.parse(date_str, fuzzy=True)
#     now = datetime.now()

#     # Only adjust if the parsed date is in the past (relative to now)
#     if dt < now:
#         try:
#             dt = dt.replace(year=now.year + 1)
#         except ValueError:
#             # Handle Feb 29 leap year edge case
#             dt = dt.replace(month=3, day=1, year=now.year + 1)

#     return dt


# from datetime import datetime
# import dateutil.parser

def parse_with_correct_year(date_str):
    try:
        parsed = dateutil.parser.parse(date_str, default=datetime.now())
        # If the user didn't specify the year, parsed.year will be current year (good)
        # You can optionally handle logic if needed to bump to next year in special cases
        return parsed
    except Exception as e:
        print(f"[Error parsing date]: {e}")
        return None



# Main Chatbot Function
def chatbot_response(user_message, history):
    global proposed_slots_memory, proposed_participants_memory
    try:
        parsed = parse_user_input(user_message)
        action = parsed.get("action")

        # Slot Confirmation
        if proposed_slots_memory:
            for slot in proposed_slots_memory:
                slot_str = slot.strftime('%A, %d %B %Y at %I:%M %p').lower()
                if all(word in slot_str for word in user_message.lower().split()):
                    dt_start = slot
                    dt_end = dt_start + timedelta(minutes=60)

                    event_link = create_event(
                        service,
                        summary=f"Meeting with {', '.join(proposed_participants_memory)}",
                        start_time=dt_start.isoformat(),
                        end_time=dt_end.isoformat(),
                        attendees=[]
                    )

                    save_meeting(', '.join(proposed_participants_memory), dt_start.strftime("%Y-%m-%d"),
                                 dt_start.strftime("%H:%M"), "Scheduled", event_link)

                    proposed_slots_memory.clear()
                    proposed_participants_memory.clear()

                    return f"""✅ **Meeting Booked Successfully!**

- **Participants**: {', '.join(proposed_participants_memory)}
- **Date**: {dt_start.strftime('%A, %d %B %Y')}
- **Time**: {dt_start.strftime('%I:%M %p')}

👉 [**View Event in Google Calendar**]({event_link})
"""

        # Scheduling
        if action == "schedule":
            participants = parsed.get("participants", [])
            date_time = parsed.get("date_time")
            month = parsed.get("target_month")
            week = parsed.get("target_week")

            if date_time:
                dt_start = parse_with_correct_year(date_time)
                dt_end = dt_start + timedelta(minutes=parsed.get("duration", 60))

                event_link = create_event(
                    service,
                    summary=f"Meeting with {', '.join(participants)}",
                    start_time=dt_start.isoformat(),
                    end_time=dt_end.isoformat(),
                    attendees=[]
                )

                save_meeting(', '.join(participants), dt_start.strftime("%Y-%m-%d"),
                             dt_start.strftime("%H:%M"), "Scheduled", event_link)

                return f"""✅ **Meeting Scheduled Successfully!**

- **Participants**: {', '.join(participants)}
- **Date**: {dt_start.strftime('%A, %d %B %Y')}
- **Time**: {dt_start.strftime('%I:%M %p')}

👉 [**View Event in Google Calendar**]({event_link})
"""

            elif month and week:
                year = get_dynamic_year(month)
                start_date, end_date = get_week_date_range(year, month, week)

                busy_times = fetch_busy_slots(service, start_date, end_date)

                workout_start = datetime.now().replace(hour=7, minute=0, second=0, microsecond=0)
                workout_end = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)

                available_slots = find_available_slots(start_date, end_date, busy_times, workout_start, workout_end)

                if not available_slots:
                    return "❗ No available slots found in the requested week."

                proposed_slots_memory.clear()
                proposed_slots_memory.extend(available_slots)
                proposed_participants_memory.clear()
                proposed_participants_memory.extend(participants)

                slots_formatted = "\n".join([
                    f"📅 {slot.strftime('%A, %d %B %Y at %I:%M %p')}"
                    for slot in available_slots[:5]
                ])

                return f"""✅ **Available Slots:**

{slots_formatted}

👉 Please reply like "**Book Tuesday at 2PM**" to confirm!
"""

            else:
                return "❗ I couldn't understand your preferred time. Please clarify."

        # Rescheduling
        elif action == "reschedule":
            participants = parsed.get("participants", [])
            old_dt = parsed.get("date_time")
            new_dt = parsed.get("new_time")

            if not (old_dt and new_dt):
                return "❗ I couldn't understand both the old and new times. Please clarify."

            old_start = parse_with_correct_year(old_dt)
            new_start = parse_with_correct_year(new_dt)
            new_end = new_start + timedelta(minutes=parsed.get("duration", 60))

            try:
                event_link = reschedule_event(service, participants[0], old_start, new_start, new_end)

                save_meeting(participants[0], new_start.strftime("%Y-%m-%d"),
                             new_start.strftime("%H:%M"), "Rescheduled", event_link)

                return f"""🔄 **Meeting Rescheduled Successfully!**

- **Participant**: {participants[0]}
- **Old Date**: {old_start.strftime('%A, %d %B %Y')}
- **New Time**: {new_start.strftime('%I:%M %p')}

👉 [**View Updated Event**]({event_link})
"""
            except Exception as e:
                return f"❌ Reschedule failed: {str(e)}"

        # Cancelling
        elif action == "cancel":
            participants = parsed.get("participants", [])
            date_time = parsed.get("date_time")

            if not (participants and date_time):
                return "❗ I couldn't understand the participant or date/time to cancel. Please clarify."

            dt_start = parse_with_correct_year(date_time)
            success = cancel_event(service, participants[0], dt_start)

            if success:
                return f"""🗑️ **Meeting Cancelled Successfully!**

- **Participant**: {participants[0]}
- **Date**: {dt_start.strftime('%A, %d %B %Y')}
- **Time**: {dt_start.strftime('%I:%M %p')}
"""
            else:
                return "❌ No matching meeting found to cancel."

        # Unknown action
        else:
            return "🔧 Feature not implemented yet."

    except Exception as e:
        return f"❌ Error: {str(e)}"





#

# Helper for History Search
def get_meetings_by_month(month):
    return [m for m in meeting_history if m["date"].split("-")[1] == month.zfill(2)]

def get_meetings_by_participant(participant_name):
    return [m for m in meeting_history if participant_name.lower() in m["participant"].lower()]

def format_meetings_for_dataframe(meetings):
    if not meetings:
        return [["No records found", "", "", "", ""]]
    # return [
    #     [m["participant"], m["date"], m["time"], m["status"], m["link"]]
    #     for m in meetings
    # ]

    return [
    ["Participant", "Date", "Time", "Status", "Google Calendar Link"]
] + [
    [m[0], m[1], m[2], m[3], m[4]]
    for m in meetings
]

#








####
# Gradio UI
with gr.Blocks() as iface:
    
    with gr.Tab("📅 Smart Calendar Assistant"):
        chatbot = gr.ChatInterface(
            fn=chatbot_response,
            title="📅 Smart Calendar Assistant",
            theme="default",
            examples=[
                ["Schedule meeting with John next Tuesday at 3 PM"],
                ["Reschedule meeting with Sarah to next Friday 11 AM"],
                ["Find slot with Alex in third week of August"]
            ]
        )

    with gr.Tab("📖 Meeting History"):
        gr.Markdown("### 📚 Full Meeting History (Scheduled and Rescheduled)")

        with gr.Row():
            month_input = gr.Textbox(label="Enter Month (e.g., 05 for May)")
            participant_input = gr.Textbox(label="Enter Participant Name")

        with gr.Row():
            search_button = gr.Button("🔎 Search Meetings")

        output_box = gr.Dataframe(
            headers=["Participant", "Date", "Time", "Status", "Google Calendar Link"],
            datatype=["str", "str", "str", "str", "str"],
            interactive=False
        )

        def search_meetings(month, participant):
            results = fetch_meetings(month, participant)
            return format_meetings_for_dataframe(results)

        search_button.click(search_meetings, inputs=[month_input, participant_input], outputs=output_box)

    # ✅ FIX: This tab should be at root level
    with gr.Tab("📥 Email Summarizer"):
        gr.Markdown("### ✉️ Summarize & Reply to Emails")

        email_output = gr.HTML(label="Summarized Emails")
        load_button = gr.Button("📨 Load Emails")

        def display_emails():
            service = authenticate_gmail()
            emails = fetch_emails(service_mail, max_results=10)
            html_output = ""
            for email in emails:
                summary = summarize_email(email["body"])
                flags = email.get("flags", [])
                html_output += f"<div><strong>From:</strong> {email['from']}<br>"
                html_output += f"<strong>Subject:</strong> {email['subject']}<br>"
                html_output += f"<strong>Summary:</strong> {summary}<br>"
                html_output += f"<strong>Flags:</strong> {', '.join(flags)}</div><hr>"
            return html_output

        load_button.click(display_emails, outputs=email_output)

        gr.Markdown("### ✍️ Generate Reply")
        email_body_input = gr.Textbox(label="Paste email body here")
        generate_button = gr.Button("🧠 Generate Reply")
        reply_output = gr.Textbox(label="AI-Generated Reply", lines=6)

        def generate_reply_interface(body):
            prompt = f"""
            You are a professional email assistant. 
            Write a polite, respectful, and to-the-point reply for the following email:

            Email Body:
            {body}

            Reply:
            """
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            return response.text.strip()

        generate_button.click(generate_reply_interface, inputs=email_body_input, outputs=reply_output)


