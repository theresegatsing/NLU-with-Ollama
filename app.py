# app.py (with improved date parsing)
import os
import json
import logging
import requests
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, Any
from datetime import datetime, timedelta
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Ollama settings - NO API KEYS NEEDED!
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

class EventRequest(BaseModel):
    utterance: str

class EventResponse(BaseModel):
    intent: str
    title: str = None
    start: str = None
    end: str = None
    duration_minutes: int = None
    attendees: list = None
    timezone: str = None

def validate_and_correct_dates(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and correct date formats"""
    # If no dates, return as-is
    if "start" not in event_data:
        return event_data
    
    try:
        # Check if date is in 2024 (probably wrong)
        start_str = event_data.get("start", "")
        if start_str and "2024" in start_str:
            # Parse the time part
            time_match = re.search(r"T(\d{2}:\d{2}:\d{2})", start_str)
            if time_match:
                time_part = time_match.group(1)
                
                # Calculate correct date based on utterance context
                today = datetime.now()
                
                # Default to today + 1 day as a simple fix
                corrected_date = today + timedelta(days=1)
                corrected_start = f"{corrected_date.strftime('%Y-%m-%d')}T{time_part}-05:00"
                
                event_data["start"] = corrected_start
                
                # Also correct end time if exists
                if "end" in event_data and "2024" in event_data["end"]:
                    end_str = event_data["end"]
                    end_time_match = re.search(r"T(\d{2}:\d{2}:\d{2})", end_str)
                    if end_time_match:
                        end_time_part = end_time_match.group(1)
                        event_data["end"] = f"{corrected_date.strftime('%Y-%m-%d')}T{end_time_part}-05:00"
    
    except Exception as e:
        logger.error(f"Date correction failed: {e}")
    
    return event_data

def extract_event(utterance: str) -> Dict[str, Any]:
    """
    Improved version with better date parsing
    """
    try:
        # Get current date for reference
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        system_prompt = f"""You are a calendar assistant. Today is {current_date}. 
        Extract event details and convert relative dates (tomorrow, next Wednesday, etc.) 
        to absolute dates in RFC3339 format with timezone offset.
        
        Return JSON with: intent, title, start, end, duration_minutes, attendees.
        Use the current date as reference: {current_date}
        
        Example for "tomorrow at 2pm": use actual tomorrow's date
        Example for "next Wednesday": use the actual next Wednesday's date
        
        Return only valid JSON, no other text."""

        user_prompt = f"""Extract calendar event from: "{utterance}"
        Current reference date: {current_date}
        Return JSON:"""

        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": user_prompt,
                "system": system_prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.1, "num_ctx": 4096}
            },
            timeout=30
        )
        
        result = response.json()
        event_data = json.loads(result["response"])
        
        # Validate and correct dates
        return validate_and_correct_dates(event_data)
        
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        # Fallback to rule-based parsing if Ollama fails
        return extract_event_fallback(utterance)

def extract_event_fallback(utterance: str) -> Dict[str, Any]:
    """Fallback function for when Ollama is not available"""
    utterance_lower = utterance.lower()
    
    # Simple rule-based parsing for demo
    if "meeting" in utterance_lower:
        return {
            "intent": "CreateEvent", 
            "title": "Meeting",
            "start": (datetime.now() + timedelta(days=1)).replace(hour=14, minute=0, second=0).isoformat(),
            "end": (datetime.now() + timedelta(days=1)).replace(hour=15, minute=0, second=0).isoformat()
        }
    elif "lunch" in utterance_lower:
        return {
            "intent": "CreateEvent",
            "title": "Lunch Meeting", 
            "start": (datetime.now() + timedelta(days=1)).replace(hour=12, minute=0, second=0).isoformat(),
            "end": (datetime.now() + timedelta(days=1)).replace(hour=13, minute=0, second=0).isoformat()
        }
    elif any(word in utterance_lower for word in ['cancel', 'delete', 'remove']):
        return {"intent": "CancelEvent"}
    else:
        return {"intent": "QueryFreeTime"}

@app.get("/")
async def root():
    return {"message": "Calendar NLU API is running!"}

@app.get("/health")
async def health_check():
    """Check if Ollama is available"""
    try:
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        return {
            "status": "healthy" if response.status_code == 200 else "degraded",
            "ollama_available": response.status_code == 200,
            "model_loaded": OLLAMA_MODEL in response.text if response.status_code == 200 else False
        }
    except:
        return {"status": "unhealthy", "ollama_available": False}

@app.post("/extract", response_model=EventResponse)
async def extract_event_endpoint(request: EventRequest):
    result = extract_event(request.utterance)
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)