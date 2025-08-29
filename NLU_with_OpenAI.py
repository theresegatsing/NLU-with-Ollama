# nlu_extract.py
import os
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
# Create client (reads OPENAI_API_KEY from your environment)
load_dotenv()  # read .env

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    project=os.getenv("OPENAI_PROJECT")  # <- you need to set this too
)


# ---------- NLU: extract intent + slots via tool calling ----------
def extract_event(utterance: str, user_tz: str = "America/New_York") -> dict:
    """
    Calls OpenAI to parse natural language into a structured event dict.
    Returns keys like: intent, title, start, end, duration_minutes, timezone, attendees, etc.
    """
    now = datetime.now(ZoneInfo(user_tz)).isoformat()

    system = (
        "You extract calendar intents and slots from natural language. "
        "Resolve relative dates/times to absolute RFC3339 WITH timezone offset "
        "using the provided reference_time and timezone. "
        "If only a duration is given (e.g., 'for 45 minutes'), return duration_minutes. "
        "If info is missing, return what you're confident about. Do not invent emails."
    )

    tools = [{
        "type": "function",
        "function": {
            "name": "extract_event",
            "description": "Return calendar intent and slots as structured JSON.",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "enum": ["CreateEvent", "MoveEvent", "CancelEvent", "AddInvitees", "QueryFreeTime"]
                    },
                    "title": { "type": "string" },
                    "start": { "type": "string", "description": "RFC3339 e.g. 2025-09-03T16:00:00-04:00" },
                    "end":   { "type": "string", "description": "RFC3339 e.g. 2025-09-03T16:45:00-04:00" },
                    "duration_minutes": { "type": "integer" },
                    "timezone": { "type": "string", "default": "America/New_York" },
                    "location": { "type": "string" },
                    "attendees": {
                        "type": "array",
                        "items": { "type": "string", "description": "email or name as provided" }
                    },
                    "recurrence": { "type": "string", "description": "RFC5545 RRULE (optional)" },
                    "reminders": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "method": { "type": "string", "enum": ["popup", "email"] },
                                "minutes": { "type": "integer" }
                            },
                            "required": ["method", "minutes"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["intent"],
                "additionalProperties": False
            },
            "strict": True
        }
    }]

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"reference_time={now}\ntimezone={user_tz}\nutterance={utterance}"}
    ]

    resp = client.chat.completions.create(
        model="gpt-4o-mini",  # or "gpt-4.1-mini"
        messages=messages,
        tools=tools,
        tool_choice={"type": "function", "function": {"name": "extract_event"}},
        temperature=0
    )

    tool_calls = resp.choices[0].message.tool_calls
    if not tool_calls:
        return {"intent": "QueryFreeTime"}  # safe minimal fallback

    args_json = tool_calls[0].function.arguments
    try:
        data = json.loads(args_json)
    except Exception:
        data = {"intent": "QueryFreeTime"}

    return data

# ---------- Mapper: NLU -> Google Calendar payload ----------
def to_gcal_event(nlu: dict) -> dict:
    """
    Transforms the NLU dict into a Google Calendar events().insert body.
    Computes end if only start + duration_minutes are present.
    """
    tz = nlu.get("timezone", "America/New_York")
    start = nlu.get("start")
    end = nlu.get("end")
    duration = nlu.get("duration_minutes")

    # Compute end from duration if needed
    if start and not end and duration:
        try:
            start_dt = datetime.fromisoformat(start)  # RFC3339 with offset
            end_dt = start_dt + timedelta(minutes=int(duration))
            end = end_dt.isoformat()
        except Exception:
            end = None  # leave None; your app can ask user later

    event = {
        "summary": nlu.get("title", "(No title)"),
        "start": {"dateTime": start, "timeZone": tz} if start else None,
        "end":   {"dateTime": end,   "timeZone": tz} if end else None,
    }

    if nlu.get("location"):
        event["location"] = nlu["location"]

    attendees = nlu.get("attendees")
    if attendees:
        event["attendees"] = [{"email": a} for a in attendees]

    if nlu.get("recurrence"):
        event["recurrence"] = [nlu["recurrence"]]

    if nlu.get("reminders"):
        event["reminders"] = {"useDefault": False, "overrides": nlu["reminders"]}

    # Strip None values
    return {k: v for k, v in event.items() if v is not None}

# ---------- Optional: helper to print and spot missing fields ----------
def print_result(nlu: dict, event_body: dict):
    print("\n=== NLU RESULT ===")
    print(nlu)
    print("\n=== GOOGLE CALENDAR PAYLOAD ===")
    print(event_body)

    missing = []
    if nlu.get("intent") == "CreateEvent":
        if not nlu.get("title"): missing.append("title")
        if not nlu.get("start") and not nlu.get("duration_minutes"):
            missing.append("start or duration_minutes")
        if not nlu.get("end") and not nlu.get("duration_minutes"):
            missing.append("end or duration_minutes")
    if missing:
        print("\n[Note] Missing critical fields:", ", ".join(missing),
              "- you may need a follow-up question.")

# ---------- Demo run ----------
if __name__ == "__main__":
    # Try your own utterances here:
    utterance = "book a sprint planning next Wednesday at 4pm for 45 minutes with maya@ex.com and leo@ex.com"

    nlu = extract_event(utterance, user_tz="America/New_York")
    event_body = to_gcal_event(nlu)
    print_result(nlu, event_body)

    # If you want to actually insert to Google Calendar:
    # gcal.events().insert(calendarId="primary", body=event_body).execute()
