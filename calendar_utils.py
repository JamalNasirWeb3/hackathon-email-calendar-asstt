from datetime import datetime, timedelta
import dateutil.parser
import calendar

# calendar_utils.py



def reschedule_event(service, participant, old_start, new_start, new_end):
    events_result = service.events().list(
        calendarId='primary',
        timeMin=(old_start - timedelta(days=1)).isoformat() + 'Z',
        timeMax=(old_start + timedelta(days=1)).isoformat() + 'Z',
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    for event in events:
        if participant.lower() in event.get('summary', '').lower():
            event['start']['dateTime'] = new_start.isoformat()
            event['end']['dateTime'] = new_end.isoformat()
            updated_event = service.events().update(
                calendarId='primary',
                eventId=event['id'],
                body=event
            ).execute()
            return updated_event['htmlLink']
    
    raise Exception("Meeting not found to reschedule.")


def cancel_event(service, participant_name, date_time):
    events_result = service.events().list(
        calendarId='primary',
        timeMin=date_time.isoformat() + 'Z',
        timeMax=(date_time + timedelta(hours=2)).isoformat() + 'Z',
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    for event in events:
        if participant_name.lower() in event.get('summary', '').lower():
            service.events().delete(calendarId='primary', eventId=event['id']).execute()
            return True

    return False

# service will be passed dynamically
def get_week_date_range(year, month_name, week_number):
    month_number = list(calendar.month_name).index(month_name)
    first_day_of_month = datetime(year, month_number, 1)

    # Find the Monday of the requested week
    first_weekday = first_day_of_month.weekday()  # Monday = 0, Sunday = 6
    start_offset = (week_number - 1) * 7
    start_date = first_day_of_month + timedelta(days=start_offset)

    # If start date overflows into next month, adjust
    if start_date.month != month_number:
        start_date = datetime(year, month_number, calendar.monthrange(year, month_number)[1]) - timedelta(days=6)

    end_date = start_date + timedelta(days=6)
    return start_date, end_date


def create_event(service, summary, start_time, end_time, attendees=[]):
    event = {
        "summary": summary,
        "start": {"dateTime": start_time, "timeZone": "Asia/Karachi"},
        "end": {"dateTime": end_time, "timeZone": "Asia/Karachi"},
        "attendees": [{"email": email} for email in attendees] if attendees else [],
    }
    created_event = service.events().insert(calendarId='primary', body=event).execute()
    return created_event.get('htmlLink')

def fetch_busy_slots(service, start_date, end_date):
    events_result = service.events().list(
        calendarId='primary',
        timeMin=start_date.isoformat() + 'Z',
        timeMax=end_date.isoformat() + 'Z',
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    busy_times = []
    for event in events:
        start = event['start'].get('dateTime')
        end = event['end'].get('dateTime')
        if start and end:
            busy_times.append((
                dateutil.parser.parse(start),
                dateutil.parser.parse(end)
            ))
    return busy_times

def parse_with_correct_year(date_str):
    try:
        parsed = dateutil.parser.parse(date_str, default=datetime.now())
        # If the user didn't specify the year, parsed.year will be current year (good)
        # You can optionally handle logic if needed to bump to next year in special cases
        return parsed
    except Exception as e:
        print(f"[Error parsing date]: {e}")
        return None
    

def find_available_slots(start_date, end_date, busy_times, workout_start, workout_end, slot_duration_minutes=60):
    slots = []
    current = start_date

    while current < end_date:
        if current.weekday() == 6:
            current += timedelta(days=1)
            continue

        work_start = current.replace(hour=9, minute=0)
        work_end = current.replace(hour=17, minute=0)
        time_cursor = work_start

        while time_cursor + timedelta(minutes=slot_duration_minutes) <= work_end:
            workout_conflict = workout_start.time() <= time_cursor.time() <= workout_end.time()
            conflict = any(bs <= time_cursor <= be for bs, be in busy_times)

            if not workout_conflict and not conflict:
                slots.append(time_cursor)

            time_cursor += timedelta(minutes=30)

        current += timedelta(days=1)

    return slots
