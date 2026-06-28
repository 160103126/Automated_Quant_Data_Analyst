from __future__ import annotations

import google.auth
from langchain_google_genai import ChatGoogleGenerativeAI
from .config import Settings

def create_gemini_model(settings: Settings) -> ChatGoogleGenerativeAI:
    credentials, project_id = google.auth.default()
    
    kwargs = {
        "model": settings.gemini_model,
        "temperature": settings.llm_temperature,
        "credentials": credentials,
    }
    
    return ChatGoogleGenerativeAI(**kwargs)
