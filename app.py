# app.py (simplified for local development)
import os
import json
import logging
import requests
from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

class EventRequest(BaseModel):
    utterance: str

class EventResponse(BaseModel):
    intent: str
    title: str = None
    start: str = None
    end: str = None

def extract_event(utterance: str):
    """Mock function for testing - replace with Ollama later"""
    # Simple rule-based parsing for demo
    if "meeting" in utterance.lower():
        return {
            "intent": "CreateEvent", 
            "title": "Meeting",
            "start": "2024-01-10T14:00:00-05:00",
            "end": "2024-01-10T15:00:00-05:00"
        }
    elif "lunch" in utterance.lower():
        return {
            "intent": "CreateEvent",
            "title": "Lunch Meeting", 
            "start": "2024-01-10T12:00:00-05:00",
            "end": "2024-01-10T13:00:00-05:00"
        }
    else:
        return {"intent": "QueryFreeTime"}

@app.get("/")
async def root():
    return {"message": "Calendar NLU API is running!"}

@app.post("/extract")
async def extract_event_endpoint(request: EventRequest):
    result = extract_event(request.utterance)
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)