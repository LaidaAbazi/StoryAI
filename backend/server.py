from flask import Flask, jsonify, send_from_directory, request, send_file, session
import requests
import os
from datetime import datetime, timedelta, UTC  # Add UTC import
from dotenv import load_dotenv
from fpdf import FPDF
import re
import uuid
import json
from langdetect import detect
from db import SessionLocal, init_db
from models import (
    User,
    CaseStudy,
    SolutionProviderInterview,
    ClientInterview,
    InviteToken,
    Label,
    Feedback
)
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError
from functools import wraps
from flask_jwt_extended import jwt_required, get_jwt_identity
import matplotlib
matplotlib.use('Agg')  # Use non-GUI backend to avoid Tkinter and main thread errors
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import plotly.express as px
import io
import base64
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from flask_migrate import Migrate



load_dotenv()
app = Flask(__name__, static_folder='../frontend', static_url_path='')

# JWT configuration
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "dev_jwt_secret")  # Use a strong secret in production!
app.config["JWT_TOKEN_LOCATION"] = ["headers"]  # Tell Flask-JWT-Extended to look for JWTs in headers

# HeyGen API configuration
HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY")
HEYGEN_API_BASE_URL = "https://api.heygen.com/v2"
HEYGEN_AVATAR_ID = "Juan_standing_office_front"
HEYGEN_VOICE_ID = "1edc5e7338eb4e37b26dc8eb3f9b7e9c"  # Your specified voice ID

init_db()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Security configurations
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=24),
    MAX_LOGIN_ATTEMPTS=5,
    LOGIN_LOCKOUT_DURATION=timedelta(minutes=15)
)

app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key")  # Use a strong secret in production!

openai_config = {
    "model": "gpt-4",
    "temperature": 0.5,        # Balanced creativity for conversational flow
    "top_p": 0.9,              # Allows controlled variation
    "presence_penalty": 0.2,   # Slightly discourages repetition
    "frequency_penalty": 0.2   # Keeps phrasing varied
}

# Initialize feedback sessions dictionary
feedback_sessions = {}

def clean_text(text):
    return (
        text.replace("•", "-")  
            .replace("—", "-")
            .replace("–", "-")
            .replace(""", '"')
            .replace(""", '"')
            .replace("'", "'")
            .replace("'", "'")
            .replace("£", "GBP ")
    )

def extract_names_from_case_study(text):
    # normalize dashes
    text = text.replace("—", "-").replace("–", "-")
    lines = text.splitlines()
    if lines:
        first = lines[0].strip()
        # strip markdown bold if present
        if first.startswith("**") and first.endswith("**"):
            first = first[2:-2].strip()

        # now expect "Provider x Client: Project Name"
        if ":" in first:
            left, proj = first.split(":", 1)
            proj = proj.strip()
            if " x " in left:
                provider, client = left.split(" x ", 1)
            else:
                provider, client = left.strip(), ""
            return {
                "lead_entity": provider.strip() or "Unknown",
                "partner_entity": client.strip(),
                "project_title": proj or "Unknown Project"
            }

    # fallback to old logic (if you really need it)
    return {
        "lead_entity": "Unknown",
        "partner_entity": "",
        "project_title": "Unknown Project"
    }


@app.route("/")
def serve_index():
    return send_from_directory(app.static_folder, "login.html")

@app.route("/session")
def create_session():
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    data = {
        "model": "gpt-4o-realtime-preview-2024-12-17",
        "voice": "coral"
    }
    response = requests.post("https://api.openai.com/v1/realtime/sessions", headers=headers, json=data)
    return jsonify(response.json())

@app.route("/save_transcript", methods=["POST"])
def save_transcript():
    session = SessionLocal()
    try:
        raw_transcript = request.get_json()
        transcript_lines = []
        buffer = {"ai": "", "user": ""}
        last_speaker = None

        for entry in raw_transcript:
            speaker = entry.get("speaker", "").lower()
            text = entry.get("text", "").strip()
            if not text:
                continue
            if speaker != last_speaker and last_speaker is not None:
                if buffer[last_speaker]:
                    transcript_lines.append(f"{last_speaker.upper()}: {buffer[last_speaker].strip()}")
                    buffer[last_speaker] = ""
            buffer[speaker] += " " + text
            last_speaker = speaker

        if last_speaker and buffer[last_speaker]:
            transcript_lines.append(f"{last_speaker.upper()}: {buffer[last_speaker].strip()}")

        full_transcript = "\n".join(transcript_lines)

        # ⚠️ Assume provider_session_id is passed from frontend!
        provider_session_id = request.args.get("provider_session_id")
        if not provider_session_id:
            return jsonify({"status": "error", "message": "Missing provider_session_id"}), 400

        # Store in DB
        interview = session.query(SolutionProviderInterview).filter_by(session_id=provider_session_id).first()
        if interview:
            interview.transcript = full_transcript
            session.commit()

        return jsonify({"status": "success", "message": "Transcript saved to DB"})

    except Exception as e:
        session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        session.close()

from langdetect import detect

def detect_language(text):
    try:
        # Get the language code
        lang_code = detect(text)
        
        # Map language codes to full names
        language_map = {
            'en': 'English',
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
            'it': 'Italian',
            'pt': 'Portuguese',
            'ru': 'Russian',
            'zh': 'Chinese',
            'ja': 'Japanese',
            'ko': 'Korean',
            'ar': 'Arabic',
            'hi': 'Hindi',
            'pl': 'Polish',
            'sq': 'Albanian',  # Added Albanian
            # Add more languages as needed
        }
        
        return language_map.get(lang_code, 'English')  # Default to English if language not in map
    except:
        return 'English'  # Default to English if detection fails

@app.route("/generate_summary", methods=["POST"])
def generate_summary():
    try:
        data = request.get_json()
        transcript = data.get("transcript", "")

        if not transcript:
            return jsonify({"status": "error", "message": "Transcript is missing."}), 400

        # Detect language from transcript
        detected_language = detect_language(transcript)
        print(detected_language)
        
        # Use the detected language in the prompt
        prompt = f"""
        You are a professional case study writer. Your job is to generate a **rich, structured, human-style business case study** from a transcript of a real voice interview.

        IMPORTANT: Write the entire case study in {detected_language}. This includes all sections, quotes, and any additional content.
        This is an **external project**: the speaker is the solution provider describing a project they delivered to a client. Your task is to write a clear, emotionally intelligent case study from their perspective—based **ONLY** on what's in the transcript.

        --- 

        ❌ **DO NOT INVENT ANYTHING**  
        - Do NOT fabricate dialogue or add made-up details  
        - Do NOT simulate the interview format  
        - Do NOT assume or imagine info not explicitly said  

        ✅ **USE ONLY what's really in the transcript.** If a piece of information (like a client quote) wasn't provided, **craft** a brief, realistic-sounding quote that captures the client's sentiment based on what they did say.

        --- 

        ### ✍️ CASE STUDY STRUCTURE (MANDATORY)

        **Title** (first line only—no extra formatting):Format: **[Solution Provider] x [Client]: [Project/product/service/strategy]**

        --- 

        **Hero Paragraph (no header)**  
        3–4 sentences introducing the client, their industry, and their challenge; then introduce the provider and summarize the delivery.

        --- 

        **Section 1 – The Challenge**  
        - What problem was the client solving?  
        - Why was it important?  
        - Any context on scale, goals, or mission

        --- 

        **Section 2 – The Solution**  
        - Describe the delivered product/service/strategy  
        - Break down key components and clever features

        --- 

        **Section 3 – Implementation & Collaboration**  
        - How was it rolled out?  
        - What was the teamwork like?  
        - Any turning points or lessons learned

        --- 

        **Section 4 – Results & Impact**  
        - What changed for the client?  
        - Include any real metrics (e.g., "40% faster onboarding")  
        - Mention qualitative feedback if shared

        --- 

        **Section 5 – Client Quote**  
        - If the transcript contains a **direct, verbatim quote** from the client or solution provider, include it as spoken.  
        - If no direct quote is present, compose **one elegant sentence** in quotation marks from the client's or provider's perspective. Use only language, tone, and key points found in the transcript to craft a testimonial that feels genuine, highlights the solution's impact, and reads like a professional endorsement.

        --- 

        **Section 6 – Reflections & Closing**  
        - What did this mean for the provider's team?  
        - End with a warm, forward-looking sentence.

        --- 

        🎯 **GOAL:**  
        A vivid, accurate, human-sounding case study grounded entirely in the transcript.

        Transcript:
        {transcript}
        """

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": openai_config["model"],
            "messages": [{"role": "system", "content": prompt}],
            "temperature": openai_config["temperature"],
            "top_p": openai_config["top_p"],
            "presence_penalty": openai_config["presence_penalty"],
            "frequency_penalty": openai_config["frequency_penalty"]
        }

        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        result = response.json()
        case_study = result["choices"][0]["message"]["content"]
        cleaned = clean_text(case_study)
        names = extract_names_from_case_study(cleaned)
        # First save to DB and get case_study_id
        provider_session_id = str(uuid.uuid4())  # 🔁 Generate a session ID now
        case_study_id = store_solution_provider_session(provider_session_id, cleaned)

        return jsonify({
            "status": "success",
            "text": cleaned,
            "names": names,
            "provider_session_id": provider_session_id,
            "case_study_id": case_study_id
        })




    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/save_provider_summary", methods=["POST"])
def save_provider_summary():
    session = SessionLocal()
    try:
        data = request.get_json()
        provider_session_id = data.get("provider_session_id")
        updated_summary = data.get("summary")

        if not provider_session_id or not updated_summary:
            return jsonify({"status": "error", "message": "Missing data"}), 400

        # Get interview from DB
        interview = session.query(SolutionProviderInterview).filter_by(session_id=provider_session_id).first()
        if not interview:
            return jsonify({"status": "error", "message": "Session not found"}), 404

        # ✅ Update summary
        interview.summary = updated_summary

        # ✅ Extract names from the new summary
        names = extract_names_from_case_study(updated_summary)
        lead_entity = names["lead_entity"]
        partner_entity = names["partner_entity"]
        project_title = names["project_title"]
        new_title = f"{lead_entity} x {partner_entity}: {project_title}"

        # ✅ Update CaseStudy title too
        case_study = session.query(CaseStudy).filter_by(id=interview.case_study_id).first()
        if case_study:
            case_study.title = new_title

        session.commit()

        return jsonify({
            "status": "success",
            "message": "Summary and title updated",
            "names": names,
            "case_study_id": case_study.id,
            "provider_session_id": provider_session_id
        })

    except Exception as e:
        session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        session.close()


@app.route("/save_client_transcript", methods=["POST"])
def save_client_transcript():
    session = SessionLocal()
    try:
        raw_transcript = request.get_json()
        transcript_lines = []
        buffer = {"ai": "", "user": ""}
        last_speaker = None

        for entry in raw_transcript:
            speaker = entry.get("speaker", "").lower()
            text = entry.get("text", "").strip()
            if not text:
                continue
            if speaker != last_speaker and last_speaker is not None:
                if buffer[last_speaker]:
                    transcript_lines.append(f"{last_speaker.upper()}: {buffer[last_speaker].strip()}")
                    buffer[last_speaker] = ""
            buffer[speaker] += " " + text
            last_speaker = speaker

        if last_speaker and buffer[last_speaker]:
            transcript_lines.append(f"{last_speaker.upper()}: {buffer[last_speaker].strip()}")

        full_transcript = "\n".join(transcript_lines)

        # ⚠️ Get token from query string
        token = request.args.get("token")
        if not token:
            return jsonify({"status": "error", "message": "Missing token"}), 400

        # Get case_study_id from token
        invite = session.query(InviteToken).filter_by(token=token).first()
        if not invite:
            return jsonify({"status": "error", "message": "Invalid token"}), 404

        # Create or update ClientInterview
        client_session_id = str(uuid.uuid4())
        interview = session.query(ClientInterview).filter_by(case_study_id=invite.case_study_id).first()

        if interview:
            interview.transcript = full_transcript
        else:
            interview = ClientInterview(
                case_study_id=invite.case_study_id,
                session_id=client_session_id,
                transcript=full_transcript
            )
            session.add(interview)

        session.commit()
        return jsonify({"status": "success", "message": "Client transcript saved", "session_id": client_session_id})

    except Exception as e:
        session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        session.close()


@app.route("/extract_names", methods=["POST"])
def extract_names():
    try:
        data = request.get_json()
        summary = data.get("summary", "")
        if not summary:
            return jsonify({"status": "error", "message": "Missing summary"}), 400

        names = extract_names_from_case_study(summary)
        return jsonify({"status": "success", "names": names})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/generate_client_summary", methods=["POST"])
def generate_client_summary():
    session = SessionLocal()
    try:
        data = request.get_json()
        transcript = data.get("transcript", "")
        token = request.args.get("token")

        if not transcript:
            return jsonify({"status": "error", "message": "Transcript is missing."}), 400
        if not token:
            return jsonify({"status": "error", "message": "Missing token"}), 400
        detected_language = detect_language(transcript)
        print(detected_language)
        

        prompt = f"""
You are a professional case study writer. Your job is to generate a **rich, human-style client perspective** on a project delivered by a solution provider.
IMPORTANT: Write the entire case study in {detected_language}. This includes all sections, quotes, and any additional content.
        - DO NOT include the transcript itself in the output.

This is a **client voice** case study — the transcript you're given is from the client who received the solution. You will create a short, structured reflection based entirely on what they shared.

---

✅ Use only the information provided in the transcript  
❌ Do NOT invent or assume missing details

---

### Structure:

**Section 1 – Project Reflection (Client Voice)**  
A warm, professional 3–5 sentence paragraph that shares:  
- What the project was  
- What the client's experience was like  
- The results or value they got  
- A light personal note if they gave one

---

**Section 2 – Client Quote**  
Include a short quote from the client (verbatim if given, otherwise craft one from the content).  
Make it feel authentic, appreciative, and aligned with their actual words.

---

🎯 GOAL:  
Provide a simple, balanced, human-sounding reflection from the client that complements the full case study.

Transcript:
{transcript}
"""

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": openai_config["model"],
            "messages": [
                {"role": "system", "content": prompt},
            ],
            "temperature": openai_config["temperature"],
            "top_p": openai_config["top_p"],
            "presence_penalty": openai_config["presence_penalty"],
            "frequency_penalty": openai_config["frequency_penalty"]
        }

        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        result = response.json()
        summary = result["choices"][0]["message"]["content"]
        cleaned = clean_text(summary)

        invite = session.query(InviteToken).filter_by(token=token).first()
        if not invite:
            return jsonify({"status": "error", "message": "Invalid token"}), 404

        client_interview = session.query(ClientInterview).filter_by(case_study_id=invite.case_study_id).first()
        if client_interview:
            client_interview.summary = cleaned
            session.commit()

        return jsonify({
            "status": "success",
            "text": cleaned,
            "case_study_id": invite.case_study_id  # ✅ added
        })


    except Exception as e:
        session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        session.close()

def store_client_summary(case_study_id, client_summary):
    session = SessionLocal()
    try:
        client_interview = session.query(ClientInterview).filter_by(case_study_id=case_study_id).first()
        if client_interview:
            client_interview.summary = client_summary
            session.commit()
    except Exception as e:
        session.rollback()
        print("❌ Error saving client summary:", str(e))
    finally:
        session.close()



@app.route("/download/<filename>")
def download_pdf(filename):
    return send_file(os.path.join("generated_pdfs", filename), as_attachment=True)

def store_solution_provider_session(provider_session_id, cleaned_case_study):
    session_db = SessionLocal()
    try:
        extracted_names = extract_names_from_case_study(cleaned_case_study)
        # Use the currently logged-in user
        from flask import session as flask_session
        user_id = flask_session.get('user_id')
        if not user_id:
            raise Exception('No user is logged in.')
        user = session_db.query(User).filter_by(id=user_id).first()
        if not user:
            raise Exception('Logged-in user not found.')

        # Create the CaseStudy (links to user)
        case_study = CaseStudy(
            user_id=user.id,
            title=f"{extracted_names['lead_entity']} x {extracted_names['partner_entity']}: {extracted_names['project_title']}",
            final_summary=None  # We fill this later, after full doc is generated
        )
        session_db.add(case_study)
        session_db.commit()

        # Create the SolutionProviderInterview
        provider_interview = SolutionProviderInterview(
            case_study_id=case_study.id,
            session_id=provider_session_id,
            transcript="",  # You can store transcript here later if needed
            summary=cleaned_case_study
        )
        session_db.add(provider_interview)
        session_db.commit()
        print(f"✅ Solution provider interview saved (ID: {provider_session_id})")

        return case_study.id  # Return case_study.id to be used for next step

    except Exception as e:
        session_db.rollback()
        print("❌ Error saving provider session:", str(e))
        raise
    finally:
        session_db.close()



def create_client_session(case_study_id):
    session = SessionLocal()
    try:
        token = str(uuid.uuid4())
        invite_token = InviteToken(
            case_study_id=case_study_id,
            token=token,
            used=False
        )
        session.add(invite_token)
        session.commit()
        print(f"✅ Client invite token created: {token}")
        return token
    except Exception as e:
        session.rollback()
        print("❌ Error creating client invite token:", str(e))
        return None
    finally:
        session.close()


@app.route("/client-interview/<token>", methods=["GET"])
def client_interview(token):
    session = SessionLocal()
    try:
        # 1. Fetch InviteToken by token
        invite = session.query(InviteToken).filter_by(token=token).first()
        if not invite or invite.used:
            return jsonify({"status": "error", "message": "Invalid or expired link"}), 404

        # 2. Fetch CaseStudy and linked SolutionProviderInterview
        case_study = session.query(CaseStudy).filter_by(id=invite.case_study_id).first()
        if not case_study:
            return jsonify({"status": "error", "message": "Case study not found"}), 404

        provider_interview = case_study.solution_provider_interview
        if not provider_interview:
            return jsonify({"status": "error", "message": "Provider interview not found"}), 404

        # 3. Mark the invite token as used
        invite.used = True
        session.commit()

        # 4. Extract info
        provider_name = provider_interview.summary  # or parse for name, or add a name field
        client_name = case_study.title.split(" x ")[1].split(":")[0] if " x " in case_study.title else ""
        project_name = case_study.title.split(":")[-1].strip() if ":" in case_study.title else ""
        provider_summary = provider_interview.summary

        return jsonify({
            "status": "success",
            "provider_name": provider_name,
            "client_name": client_name,
            "project_name": project_name,
            "provider_summary": provider_summary
        })
    except Exception as e:
        session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        session.close()

@app.route("/client/<token>")
def serve_client_interview(token):
    return send_from_directory(app.static_folder, "client.html")



@app.route("/generate_client_interview_link", methods=["POST"])
def generate_client_interview_link():
    session = SessionLocal()
    try:
        data = request.get_json()
        case_study_id = data.get("case_study_id")
        if not case_study_id:
            return jsonify({"status": "error", "message": "Missing case_study_id."}), 400

        # Make sure this case study exists
        case_study = session.query(CaseStudy).filter_by(id=case_study_id).first()
        if not case_study:
            return jsonify({"status": "error", "message": "Invalid case study ID."}), 400

        token = create_client_session(case_study_id)
        if not token:
            return jsonify({"status": "error", "message": "Failed to create client session."}), 500
        
        BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:10000")
        interview_link = f"{BASE_URL}/client/{token}"
        provider_interview = session.query(SolutionProviderInterview).filter_by(case_study_id=case_study_id).first()
        if provider_interview:
            provider_interview.client_link_url = interview_link
            session.commit()

        return jsonify({"status": "success", "interview_link": interview_link})
    except Exception as e:
        session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        session.close()

@app.route("/generate_full_case_study", methods=["POST"])
def generate_full_case_study():
    session = SessionLocal()
    try:
        data = request.get_json()
        case_study_id = data.get("case_study_id")

        if not case_study_id:
            return jsonify({"status": "error", "message": "Missing case_study_id"}), 400

        case_study = session.query(CaseStudy).filter_by(id=case_study_id).first()
        if not case_study:
            return jsonify({"status": "error", "message": "Case study not found"}), 404

        provider_interview = case_study.solution_provider_interview
        client_interview = case_study.client_interview
        

        if not provider_interview or not client_interview:
            return jsonify({"status": "error", "message": "Both summaries are required."}), 400

        provider_summary = provider_interview.summary or ""
        client_summary = client_interview.summary or ""
        detected_language = detect_language(provider_summary)
        print(detected_language)
        full_prompt = f"""
        You are a top-tier business case study writer, creating professional, detailed, and visually attractive stories for web or PDF (inspired by Storydoc, Adobe, and top SaaS companies).

        IMPORTANT: Write the entire case study in {detected_language}. This includes all sections, quotes, and any additional content.

        Your job is to read the full Solution Provider and Client summaries below, and **merge them into a single, rich, multi-perspective case study**—not just by pasting, but by synthesizing their insights, stories, and data into one engaging narrative.

        ---

        **Instructions:**
        - The **Solution Provider version is your base**; the Client version should *enhance, correct, or add* to it.
        - If the client provides a correction, update, or different number/fact for something from the provider, ALWAYS use the client's corrected version in the main story (unless it is unclear; then flag for review).
        - In the "Corrected & Conflicted Replies" section, list each specific fact, number, or point that the client corrected, changed, or disagreed with.
        - Accuracy is CRITICAL: Double-check every fact, number, quote, and piece of information. Do NOT make any mistakes or subtle errors in the summary. Every detail must match the input summaries exactly unless you are synthesizing clearly from both. If you are unsure about a detail, do NOT invent or guess; either omit or flag it for clarification.
        - If the Client provided information that contradicts, corrects, or expands on the Provider's version, **create a special section titled "Corrected & Conflicted Replies"**. In this section, briefly and clearly list the key areas where the Client said something different, added, corrected, or removed a point. This should be a concise summary (bullets or short sentences) so the provider can easily see what changed.
        - In the main story, **merge and synthesize all available details and insights** from both the Solution Provider and Client summaries: background, challenges, solutions, process, collaboration, data, quotes, and results. Do not repeat information—combine and paraphrase to build a seamless narrative.
        - **Quotes:**  
            - Include exactly ONE impactful quote from the client in the "Customer/Client Reflection" section
            - Include exactly ONE impactful quote from the provider in the "Testimonial/Provider Reflection" section
            - These should be the most powerful, representative quotes
            - Keep them concise and impactful
        - Write in clear, engaging business English. Use a mix of paragraphs, bold section headers, and bullet points.
        - Include real numbers, testimonials, collaboration stories, and unique project details whenever possible.
        - Start with a punchy title and bold hero statement summarizing the main impact.
        - Make each section distinct and visually scannable (use bold, bullet points, metrics, and quotes).
        - Make the results section full of specifics: show metrics, improvements, and qualitative outcomes.
        - End with a call to action for future collaboration, demo, or contact.
        - DO NOT use asterisks or Markdown stars (**) in your output. Section headers should be in ALL CAPS or plain text only.


        ---

        **CASE STUDY STRUCTURE:**

        1. **Logo & Title Block**
        - [Logo or company name]
        - Title: [Provider] & [Client]: [Project or Transformation]
        - Date (Month, Year)
        - Avg. Reading Time (if provided)

        2. **Hero Statement / Banner**
        - One-sentence summary of the most important impact or achievement.

        3. **Introduction**
        - 2–3 sentence overview, combining both perspectives. Who are the companies? What problem did they tackle together? What was the outcome?

        4. **Methodology** (optional)
        - Brief on how the project was researched, developed, or analyzed (interviews, surveys, analytics, etc).

        5. **Background**
        - The client's story, their industry, goals, and challenges before the project.
        - Why did they choose the solution provider? Add context from both summaries.

        6. **Challenges**
        - List the main problems the client faced (use bullet points).
        - Include quantitative data and qualitative pain points from both perspectives.

        7. **The Solution (Provider's Perspective)**
        - Detail what was delivered, how it worked, and what made it unique.
        - Include technical innovations, special features, and design choices.
        - Reference the provider's process, methods, and expertise.

        8. **Implementation & Collaboration (Process)**
        - Describe how both teams worked together: communication style, project management, user testing, sprints, workshops, etc.
        - Highlight teamwork, feedback, and any challenges overcome together.
        - Use insights and anecdotes from both provider and client summaries.

        9. **Results & Impact**
        - Specific metrics (growth, satisfaction, time saved, revenue, etc) and qualitative outcomes.
        - Make this section detailed: include before/after numbers, quotes, and proof points.
        - Summarize what changed for the client, and what the provider is proud of.

        10. **Customer/Client Reflection**
            - One paragraph (from the client summary) about their experience, feelings, and results in their own words.
            - Include a client quote if provided.

        11. **Testimonial/Provider Reflection**
            - Provider's own short reflection or quote about the partnership and success.

        12. **Corrected & Conflicted Replies**
            - *(Only for the solution provider's view, not in the published story for the client.)*
            - Briefly summarize any specific facts, numbers, or perspectives that the client corrected, contradicted, or added, compared to the provider's summary.
            - Use a bulleted list or short sentences:  
            - "Client stated project delivered in 7 weeks, not 6."  
            - "Client mentioned additional integration with Shopify, not noted by provider."  
            - "Provider said client satisfaction 95%, client said 89%."  
            - "Client removed/clarified certain benefits."
            - This is a quick-reference "diff" so the provider can see at a glance where their and the client's stories differ or align.

        13. **Call to Action**
            - Friendly invitation to book a meeting, see a demo, or contact for partnership.
            - Include links or contact info if available.

        ---

        **Style Notes:**

        - Make it detailed—avoid generic statements.
        - Merge, paraphrase, and connect ideas to create a seamless, compelling story from both sides.
        - Use real data and anecdotes whenever possible.
        - Bold section headers, bullet points for lists, and visual cues for metrics.
        - Ensure the story flows logically and keeps the reader engaged.
        - The output should be ready for use as a visually attractive PDF or web story.

        ---

        **INPUT DATA:**

        Now, generate the complete, detailed case study as described above, using both summaries in every section, following these instructions exactly.

        **Provider Summary:**  
        {provider_summary}

        ---

        **Client Summary:**  
        {client_summary}

        **IMPORTANT QUOTE STRUCTURE:**
        1. **Main Story Quotes** (Only these should appear in the main story):
            - Include exactly ONE impactful quote from the client in the "Customer/Client Reflection" section
            - Include exactly ONE impactful quote from the provider in the "Testimonial/Provider Reflection" section
            - These should be the most powerful, representative quotes
            - Keep them concise and impactful

        2. **Additional Quotes** (These will appear ONLY in the meta data):
            - After the main story, provide a section titled "Quotes Highlights"
            - Include 2-3 additional meaningful quotes that were NOT used in the main story
            - These should be different from the main quotes above
            - Format each as:
              - **Client:** "Their exact words or close paraphrase"
              - **Provider:** "Their exact words or close paraphrase"
            - Focus on quotes that:
              - Highlight specific results or metrics
              - Show unique insights about the collaboration
              - Express satisfaction or key learnings
              - Reveal interesting challenges overcome

        Example of Additional Quotes (for meta data only):
        - **Client:** "What surprised us most was the 80% reduction in manual work."
        - **Provider:** "The client's feedback helped us refine the solution in unexpected ways."
        """

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": openai_config["model"],
            "messages": [
                {"role": "system", "content": full_prompt},
            ],
            "temperature": 0.5,
            "top_p": 0.9
        }

        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        result = response.json()
        case_study_text = result["choices"][0]["message"]["content"]
        cleaned = clean_text(case_study_text)

        def draft_quote_from_summary(summary, speaker="Client"):
            # Simple template-based fallback if OpenAI is not available
            # You can make this smarter or use OpenAI if you wish
            return f"As a {speaker.lower()}, I can say this project made a real difference for us. We're very happy with the results."

        def extract_and_remove_metadata_sections(text, client_summary=None):
            # Patterns to extract meta sections
            conflict_pattern = r"(?:\*\*|__)?Corrected\s*&\s*Conflicted Replies(?:\*\*|__)?\s*[\r\n]+(.*?)(?=(?:\*\*|__)?Quotes? Highlights(?:\*\*|__)?|$)"
            quotes_pattern = r"(?:\*\*|__)?Quotes? Highlights(?:\*\*|__)?\s*[\r\n\-:]*([\s\S]*?)(?=(?:\*\*|__)?[A-Z][^:]*:|$)"
            
            # Extract meta sections
            conflict_match = re.search(conflict_pattern, text, re.IGNORECASE | re.DOTALL)
            quotes_match = re.search(quotes_pattern, text, re.IGNORECASE | re.DOTALL)
            corrected_conflicts = conflict_match.group(1).strip() if conflict_match else ""
            quote_highlights = quotes_match.group(1).strip() if quotes_match else ""

            # Fallback: if quote_highlights is empty, try to extract blockquotes or bulleted quotes
            if not quote_highlights:
                # Try to extract lines like: - **Client:** "Quote here..."
                blockquote_lines = re.findall(r'- \*\*(Client|Provider)\*\*:\s*["""]([\s\S]*?)["""]', text)
                if blockquote_lines:
                    quote_highlights = "\n".join(f'- **{who}:** "{q.strip()}"' for who, q in blockquote_lines)
                else:
                    # Fallback: extract multi-line quotes between quotes
                    multiline_quotes = re.findall(r'["""]([\s\S]*?)["""]', text)
                    if multiline_quotes:
                        quote_highlights = "\n".join(f'- "{q.strip()}"' for q in multiline_quotes)
                    elif client_summary:
                        # Draft a quote from the client summary
                        drafted = draft_quote_from_summary(client_summary, speaker="Client")
                        quote_highlights = f'- "{drafted}"'

            # Remove meta sections from the main story
            text = re.sub(conflict_pattern, "", text, flags=re.IGNORECASE | re.DOTALL)
            text = re.sub(quotes_pattern, "", text, flags=re.IGNORECASE | re.DOTALL)
            
            # Extract key takeaways
            client_takeaways = extract_client_takeaways(client_summary) if client_summary else ""

            # Ensure sentiment analysis is included in meta data
            sentiment = analyze_sentiment(client_summary) if client_summary else {}

            return text.strip(), {
                "corrected_conflicts": corrected_conflicts,
                "quote_highlights": quote_highlights,
                "sentiment": sentiment,
                "client_takeaways": client_takeaways,
                # Add other meta data fields as needed
            }

        def extract_client_takeaways(client_summary):
            """Extract key takeaways from client interview using OpenAI."""
            try:
                prompt = f"""
                Analyze the following client interview summary and extract the 3-5 most important key takeaways.
                Focus on:
                - Main pain points or challenges they faced
                - Most valued aspects of the solution
                - Key benefits or improvements they experienced
                - Their overall satisfaction level
                - Any specific metrics or results they mentioned

                Format the response as a bullet-point list.

                Client Summary:
                {client_summary}
                """

                headers = {
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                }

                payload = {
                    "model": openai_config["model"],
                    "messages": [{"role": "system", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 500
                }

                response = requests.post("https://api.openai.com/v1/chat/completions", 
                                      headers=headers, 
                                      json=payload)
                result = response.json()
                return result["choices"][0]["message"]["content"].strip()
            except Exception as e:
                print(f"Error extracting client takeaways: {str(e)}")
                return "Unable to extract key takeaways."

        def generate_sentiment_chart(sentiment_score, output_dir="generated_pdfs"):
            # Create a simple horizontal bar chart for sentiment
            fig, ax = plt.subplots(figsize=(4, 1.5))
            color = 'green' if sentiment_score > 6 else 'yellow' if sentiment_score > 4 else 'red'
            ax.barh(['Sentiment'], [sentiment_score], color=color)
            ax.set_xlim(0, 10)
            ax.set_xlabel('Score (0-10)')
            ax.set_title('Sentiment Score')
            plt.tight_layout()
            # Save to a unique file
            os.makedirs(output_dir, exist_ok=True)
            filename = f"sentiment_chart_{uuid.uuid4().hex}.png"
            filepath = os.path.join(output_dir, filename)
            plt.savefig(filepath)
            plt.close(fig)
            return filename

        def extract_client_satisfaction(client_summary):
            # Define categories and keywords
            categories = [
                ("Very Bad", ["terrible", "awful", "horrible", "very disappointed", "extremely dissatisfied", "never again", "worst"]),
                ("Bad", ["bad", "disappointed", "dissatisfied", "not happy", "not satisfied", "issues", "problems", "concerns"]),
                ("Neutral", ["okay", "neutral", "average", "fine", "acceptable", "neither good nor bad"]),
                ("Good", ["good", "satisfied", "happy", "pleased", "helpful", "positive", "recommend", "valuable", "improved", "great help"]),
                ("Very Good", ["excellent", "outstanding", "amazing", "fantastic", "very happy", "very satisfied", "delighted", "impressed", "exceptional", "game changer", "highly recommend", "best"])
            ]
            summary_lower = client_summary.lower()
            found_category = "Neutral"
            for cat, keywords in categories:
                for kw in keywords:
                    if kw in summary_lower:
                        found_category = cat
                        break
                if found_category != "Neutral":
                    break

            # Try to extract a satisfaction sentence
            satisfaction_sentence = ""
            for cat, keywords in categories:
                for kw in keywords:
                    match = re.search(r'([^.]*\b' + re.escape(kw) + r'\b[^.]*)\.', client_summary, re.IGNORECASE)
                    if match:
                        satisfaction_sentence = match.group(1).strip()
                        break
                if satisfaction_sentence:
                    break

            return {
                "category": found_category,
                "statement": satisfaction_sentence or "No explicit satisfaction statement found."
            }

        def generate_client_satisfaction_gauge(category):
            # Map categories to values and colors for the gauge
            category_map = {
                "Very Bad": (1, "#ef4444"),
                "Bad": (3, "#f59e42"),
                "Neutral": (5, "#fbbf24"),
                "Good": (7, "#a3e635"),
                "Very Good": (9, "#22c55e")
            }
            value, color = category_map.get(category, (5, "#fbbf24"))
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=value,
                number={'valueformat': '', 'font': {'size': 1}, 'suffix': ''},  # Hide the number
                title={'text': f"Client Satisfaction: <b>{category}</b>", 'font': {'size': 22}},
                gauge={
                    'axis': {'range': [0, 10], 'tickvals': [1, 3, 5, 7, 9], 'ticktext': ["Very Bad", "Bad", "Neutral", "Good", "Very Good"], 'tickwidth': 2, 'tickcolor': "#888"},
                    'bar': {'color': color, 'thickness': 0.3},
                    'steps': [
                        {'range': [0, 2], 'color': "#ef4444"},
                        {'range': [2, 4], 'color': "#f59e42"},
                        {'range': [4, 6], 'color': "#fbbf24"},
                        {'range': [6, 8], 'color': "#a3e635"},
                        {'range': [8, 10], 'color': "#22c55e"},
                    ],
                    'threshold': {
                        'line': {'color': "black", 'width': 8},
                        'thickness': 0.9,
                        'value': value
                    }
                }
            ))
            fig.update_layout(height=300, margin=dict(t=40, b=0, l=0, r=0))
            return fig.to_json()

        def analyze_sentiment(client_summary):
            try:
                analyzer = SentimentIntensityAnalyzer()
                scores = analyzer.polarity_scores(client_summary)
                compound = scores['compound']
                if compound >= 0.05:
                    sentiment = "positive"
                elif compound <= -0.05:
                    sentiment = "negative"
                else:
                    sentiment = "neutral"

                final_analysis = {
                    "overall_sentiment": {
                        "sentiment": sentiment,
                        "confidence": abs(compound),
                        "score": round((compound + 1) * 5, 2)  # scale -1..1 to 0..10
                    },
                    "emotional_analysis": {
                        "primary_emotion": sentiment,
                        "secondary_emotions": [],
                        "emotional_intensity": max(scores['pos'], scores['neg'])
                    },
                    "key_points": {
                        "positive": [],
                        "negative": []
                    },
                    "metrics": [],
                    "satisfaction": {
                        "score": 0,
                        "confidence": abs(compound),
                        "key_factors": [],
                        "statement": ""
                    },
                    "visualizations": {}
                }
                # Generate and attach the sentiment chart image
                sentiment_score = final_analysis["overall_sentiment"]["score"]
                chart_filename = generate_sentiment_chart(sentiment_score)
                final_analysis["visualizations"]["sentiment_chart_img"] = f"/generated_pdfs/{chart_filename}"

                # Add client satisfaction analysis
                satisfaction_info = extract_client_satisfaction(client_summary)
                final_analysis["satisfaction"]["category"] = satisfaction_info["category"]
                final_analysis["satisfaction"]["statement"] = satisfaction_info["statement"]

                # Generate and attach the Plotly gauge for client satisfaction
                gauge_json = generate_client_satisfaction_gauge(satisfaction_info["category"])
                final_analysis["visualizations"]["client_satisfaction_gauge"] = gauge_json

                return final_analysis
            except Exception as e:
                print(f"Error in sentiment analysis: {str(e)}")
                return {
                    "overall_sentiment": {
                        "sentiment": "unknown",
                        "confidence": 0,
                        "score": 0
                    },
                    "emotional_analysis": {
                        "primary_emotion": "unknown",
                        "secondary_emotions": [],
                        "emotional_intensity": 0
                    },
                    "key_points": {
                        "positive": [],
                        "negative": []
                    },
                    "metrics": [],
                    "satisfaction": {
                        "score": 0,
                        "confidence": 0,
                        "key_factors": [],
                        "statement": "No explicit satisfaction statement found."
                    },
                    "visualizations": {}
                }

        main_story, meta_data = extract_and_remove_metadata_sections(cleaned, client_summary)
        print("Meta data being saved:", meta_data)
        case_study.final_summary = main_story
        case_study.meta_data_text = json.dumps(meta_data, ensure_ascii=False, indent=2)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"final_case_study_{timestamp}.pdf"
        pdf_path = os.path.join("generated_pdfs", pdf_filename)
        os.makedirs("generated_pdfs", exist_ok=True)

        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_font("Arial", size=12)
        for line in main_story.split("\n"):
            pdf.multi_cell(0, 10, line)

        pdf.output(pdf_path)

        case_study.final_summary_pdf_path = pdf_path
        session.commit()

        return jsonify({
            "status": "success",
            "text": main_story,
            "pdf_url": f"/download/{pdf_filename}"
        })

    except Exception as e:
        session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        session.close()

@app.route("/download_full_summary_pdf")
def download_full_summary_pdf():
    case_study_id = request.args.get("case_study_id")
    if not case_study_id:
        return jsonify({"status": "error", "message": "Missing case_study_id"}), 400

    session = SessionLocal()
    try:
        case_study = session.query(CaseStudy).filter_by(id=case_study_id).first()

        # ✅ Check path existence
        if not case_study or not case_study.final_summary_pdf_path or not os.path.exists(case_study.final_summary_pdf_path):
            return jsonify({"status": "error", "message": "Final summary PDF not available"}), 404

        return jsonify({
            "status": "success",
            "pdf_url": f"/download/{os.path.basename(case_study.final_summary_pdf_path)}"
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        session.close()

def validate_password(password):
    """Validate password strength."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number"
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character"
    return True, ""

def validate_email(email):
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def sanitize_input(text):
    """Sanitize user input."""
    if not text:
        return ""
    # Remove any HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove any script tags
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL)
    return text.strip()

@app.route('/api/signup', methods=['POST'])
def api_signup():
    data = request.get_json()
    print("DEBUG SIGNUP DATA:", data)
    required = ['first_name', 'last_name', 'email', 'company', 'password']
    if not all(data.get(f) for f in required):
        print("DEBUG: Missing field in", data)
        for f in required:
            print(f"  {f}: {data.get(f) if data else None}")
        return jsonify({'success': False, 'message': 'All fields are required.'}), 400
    session_db = SessionLocal()
    try:
        user = User(
            first_name=data['first_name'].strip(),
            last_name=data['last_name'].strip(),
            email=data['email'].strip().lower(),
            company_name=data['company'].strip(),
            password_hash=generate_password_hash(data['password'])
        )
        session_db.add(user)
        session_db.commit()
        session['user_id'] = user.id
        session.permanent = True
        return jsonify({'success': True})
    except IntegrityError:
        session_db.rollback()
        return jsonify({'success': False, 'message': 'Email already registered.'}), 409
    except Exception as e:
        session_db.rollback()
        print("DEBUG: Exception during signup:", e)
        return jsonify({'success': False, 'message': 'An error occurred during signup.'}), 500
    finally:
        session_db.close()

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'success': False, 'message': 'Email and password are required.'}), 400

    session_db = SessionLocal()
    try:
        user = session_db.query(User).filter_by(email=email).first()
        
        # Check if account is locked
        if user and user.account_locked_until and user.account_locked_until > datetime.now():
            remaining_time = (user.account_locked_until - datetime.now()).seconds // 60
            return jsonify({
                'success': False, 
                'message': f'Account is locked. Try again in {remaining_time} minutes.'
            }), 401

        if user and check_password_hash(user.password_hash, password):
            # Reset failed attempts on successful login
            user.failed_login_attempts = 0
            user.last_login = datetime.now()
            user.account_locked_until = None
            session_db.commit()
            
            session['user_id'] = user.id
            session.permanent = True
            return jsonify({'success': True})
        else:
            if user:
                # Increment failed attempts
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= app.config['MAX_LOGIN_ATTEMPTS']:
                    user.account_locked_until = datetime.now() + app.config['LOGIN_LOCKOUT_DURATION']
                session_db.commit()
            
            return jsonify({'success': False, 'message': 'Invalid email or password.'}), 401
    finally:
        session_db.close()

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/case_studies')
def api_case_studies():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    label_id = request.args.get('label', type=int)
    db_session = SessionLocal()
    try:
        query = db_session.query(CaseStudy).filter_by(user_id=user_id)
        if label_id:
            query = query.join(CaseStudy.labels).filter(Label.id == label_id)
        case_studies = query.all()
        result = []
        for cs in case_studies:
            result.append({
                'id': cs.id,
                'title': cs.title,
                'solution_provider_summary': getattr(cs.solution_provider_interview, 'summary', None),
                'client_summary': getattr(cs.client_interview, 'summary', None),
                'final_summary': cs.final_summary,
                'meta_data_text': cs.meta_data_text,
                'linkedin_post': cs.linkedin_post,
                'labels': [{'id': l.id, 'name': l.name} for l in cs.labels],
                'client_link_url': getattr(cs.solution_provider_interview, 'client_link_url', None),  
                'video_url': cs.video_url,
                'video_id': cs.video_id,
                'video_status': cs.video_status,
                'video_created_at': cs.video_created_at.isoformat() if cs.video_created_at else None,
            })
        return jsonify({'success': True, 'case_studies': result})
    finally:
        db_session.close()

@app.route('/api/labels', methods=['GET'])
def get_labels():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    db_session = SessionLocal()
    try:
        labels = db_session.query(Label).filter_by(user_id=user_id).all()
        return jsonify({'success': True, 'labels': [{'id': l.id, 'name': l.name} for l in labels]})
    finally:
        db_session.close()

@app.route('/api/labels', methods=['POST'])
def create_label():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Label name required'}), 400
    db_session = SessionLocal()
    try:
        label = Label(name=name, user_id=user_id)
        db_session.add(label)
        db_session.commit()
        return jsonify({'success': True, 'label': {'id': label.id, 'name': label.name}})
    finally:
        db_session.close()

@app.route('/api/labels/<int:label_id>', methods=['PATCH'])
def rename_label(label_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    data = request.get_json()
    new_name = data.get('name', '').strip()
    if not new_name:
        return jsonify({'success': False, 'message': 'New label name required'}), 400
    db_session = SessionLocal()
    try:
        label = db_session.query(Label).filter_by(id=label_id, user_id=user_id).first()
        if not label:
            return jsonify({'success': False, 'message': 'Label not found'}), 404
        label.name = new_name
        db_session.commit()
        return jsonify({'success': True, 'label': {'id': label.id, 'name': label.name}})
    finally:
        db_session.close()

@app.route('/api/labels/<int:label_id>', methods=['DELETE'])
def delete_label(label_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    db_session = SessionLocal()
    try:
        label = db_session.query(Label).filter_by(id=label_id, user_id=user_id).first()
        if not label:
            return jsonify({'success': False, 'message': 'Label not found'}), 404
        db_session.delete(label)
        db_session.commit()
        return jsonify({'success': True})
    finally:
        db_session.close()

@app.route('/api/case_studies/<int:case_study_id>/labels', methods=['POST'])
def add_labels_to_case_study(case_study_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    data = request.get_json()
    label_ids = data.get('label_ids', [])
    label_names = data.get('label_names', [])
    db_session = SessionLocal()
    try:
        case_study = db_session.query(CaseStudy).filter_by(id=case_study_id, user_id=user_id).first()
        if not case_study:
            return jsonify({'success': False, 'message': 'Case study not found'}), 404
        # Add by IDs
        for lid in label_ids:
            label = db_session.query(Label).filter_by(id=lid, user_id=user_id).first()
            if label and label not in case_study.labels:
                case_study.labels.append(label)
        # Add by names (create if not exist)
        for name in label_names:
            name = name.strip()
            if not name:
                continue
            label = db_session.query(Label).filter_by(name=name, user_id=user_id).first()
            if not label:
                label = Label(name=name, user_id=user_id)
                db_session.add(label)
                db_session.commit()
            if label not in case_study.labels:
                case_study.labels.append(label)
        db_session.commit()
        return jsonify({'success': True, 'labels': [{'id': l.id, 'name': l.name} for l in case_study.labels]})
    finally:
        db_session.close()

@app.route('/api/case_studies/<int:case_study_id>/labels/<int:label_id>', methods=['DELETE'])
def remove_label_from_case_study(case_study_id, label_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    db_session = SessionLocal()
    try:
        case_study = db_session.query(CaseStudy).filter_by(id=case_study_id, user_id=user_id).first()
        if not case_study:
            return jsonify({'success': False, 'message': 'Case study not found'}), 404
        label = db_session.query(Label).filter_by(id=label_id, user_id=user_id).first()
        if not label or label not in case_study.labels:
            return jsonify({'success': False, 'message': 'Label not found on this case study'}), 404
        case_study.labels.remove(label)
        db_session.commit()
        return jsonify({'success': True, 'labels': [{'id': l.id, 'name': l.name} for l in case_study.labels]})
    finally:
        db_session.close()

@app.route('/api/user')
def api_user():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    db_session = SessionLocal()
    try:
        user = db_session.query(User).filter_by(id=user_id).first()
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        return jsonify({
            'success': True,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email
        })
    finally:
        db_session.close()

@app.route('/api/feedback/start', methods=['POST'])
def start_feedback_session():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    session_id = str(uuid.uuid4())
    feedback_sessions[session_id] = {
        'user_id': user_id,
        'start_time': datetime.utcnow(),
        'transcript': [],
        'status': 'active'
    }
    return jsonify({'session_id': session_id, 'status': 'started'})

@app.route('/api/feedback/submit', methods=['POST'])
def submit_feedback():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    data = request.json
    session_db = SessionLocal()
    try:
        feedback = Feedback(
            user_id=user_id,
            content=data.get('content'),
            rating=data.get('rating'),
            feedback_type=data.get('feedback_type', 'general')
        )
        session_db.add(feedback)
        session_db.commit()
        return jsonify(feedback.to_dict())
    except Exception as e:
        session_db.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        session_db.close()

@app.route('/api/feedback/history', methods=['GET'])
def get_feedback_history():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    session_db = SessionLocal()
    try:
        feedbacks = session_db.query(Feedback).filter_by(user_id=user_id).order_by(Feedback.created_at.desc()).all()
        return jsonify([feedback.to_dict() for feedback in feedbacks])
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        session_db.close()

@app.route("/get_provider_transcript", methods=["GET"])
def get_provider_transcript():
    session = SessionLocal()
    try:
        token = request.args.get("token")
        if not token:
            return jsonify({"status": "error", "message": "Missing token"}), 400

        # Get case_study_id from token
        invite = session.query(InviteToken).filter_by(token=token).first()
        if not invite:
            return jsonify({"status": "error", "message": "Invalid token"}), 404

        # Get the provider interview transcript
        provider_interview = session.query(SolutionProviderInterview).filter_by(case_study_id=invite.case_study_id).first()
        if not provider_interview or not provider_interview.transcript:
            return jsonify({"status": "error", "message": "Provider transcript not found"}), 404

        return jsonify({
            "status": "success",
            "transcript": provider_interview.transcript
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        session.close()

@app.route('/generated_pdfs/<filename>')
def serve_generated_file(filename):
    return send_from_directory('generated_pdfs', filename)

def generate_linkedin_post(case_study_text):
    """Generate a LinkedIn post from a case study using AI."""
    prompt = f"""
    You are writing a highly engaging LinkedIn post as the *solution provider* (e.g., tech company, agency, freelancer) who successfully delivered the project described below.

    Craft a LinkedIn post that:

    * Begins with a powerful hook: a thought-provoking question, intriguing fact, surprising insight, or bold statement that immediately grabs attention.
    * Clearly and concisely frames the specific challenge or problem your client was facing in relatable, human language.
    * Describes how your team approached this challenge, highlighting your unique methodology, collaboration process, or innovative thinking in a grounded, authentic way.
    * Shares specific measurable outcomes or meaningful feedback from your client (quantitative metrics like percentages, time saved, costs reduced, or qualitative insights like direct quotes or observed benefits).
    * Reflects genuine pride and insight into why this project mattered, showcasing real value without hype or sales clichés.
    * Includes a short, authentic quote from your client or your project lead if available, making the story more credible and engaging.
    * Ends with a thoughtful reflection or an engaging, open-ended question designed to spark conversation or encourage readers to share similar experiences or insights.
    * Uses a confident yet relatable tone: professional but human, insightful but not overly polished—like a respected founder or lead reflecting thoughtfully on a successful project.
    * Includes 3–5 targeted hashtags relevant to your industry or project focus (e.g., #DigitalTransformation, #AI, #CustomerSuccess, #Innovation, #TechLeadership).
    * Keeps the total length concise yet substantial, between 1000–1300 characters (including hashtags).

    Avoid jargon, buzzwords, or generic statements. Aim for clarity, authenticity, and storytelling excellence.

    Case Study:
    {case_study_text}

    LinkedIn Post:
    """


    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4",
        "messages": [{"role": "system", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 500
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    result = response.json()
    return result["choices"][0]["message"]["content"]

@app.route("/generate_linkedin_post", methods=["POST"])
def generate_linkedin_post_endpoint():
    session = SessionLocal()
    try:
        data = request.get_json()
        case_study_id = data.get("case_study_id")

        if not case_study_id:
            return jsonify({"status": "error", "message": "Missing case_study_id"}), 400

        case_study = session.query(CaseStudy).filter_by(id=case_study_id).first()
        if not case_study:
            return jsonify({"status": "error", "message": "Case study not found"}), 404

        if not case_study.final_summary:
            return jsonify({"status": "error", "message": "No final summary available"}), 400

        # Generate LinkedIn post
        linkedin_post = generate_linkedin_post(case_study.final_summary)
        
        # Save to database
        case_study.linkedin_post = linkedin_post
        session.commit()

        return jsonify({
            "status": "success",
            "linkedin_post": linkedin_post
        })

    except Exception as e:
        session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        session.close()

def generate_heygen_input_text(final_summary):
    """Generate optimized input text for HeyGen video using OpenAI."""
    try:
        prompt = f"""You are creating a script for a professional video presentation using an AI avatar. Your task is to transform this case study into an engaging, conversational script that will be delivered by an AI avatar.

IMPORTANT REQUIREMENTS:
- Maximum 1300 characters (strict limit)
- Natural, conversational tone that sounds human
- Clear, professional delivery style
- Focus on the most impactful parts of the story
- Include specific metrics and results
- Break into natural speaking patterns
- Avoid complex jargon or technical terms
- Keep sentences concise and easy to follow

SCRIPT STRUCTURE:
1. Opening Hook (1-2 sentences)
   - Grab attention with the most impressive result or achievement
   - Set the context briefly

2. Main Story (3-4 sentences)
   - Explain the challenge/problem
   - Describe the solution
   - Highlight key implementation details
   - Share specific results and metrics

3. Closing Impact (1-2 sentences)
   - Reinforce the main achievement
   - End with a memorable takeaway

TONE AND STYLE:
- Professional but warm and engaging
- Confident but not salesy
- Clear and direct
- Natural pauses for the avatar to breathe
- Avoid complex sentence structures
- Use active voice
- Include transition phrases for smooth delivery

Case Study Summary:
{final_summary}

Please format the response as a single, flowing paragraph optimized for video narration. Remember to stay within 1300 characters."""

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": openai_config["model"],
            "messages": [
                {"role": "system", "content": "You are a professional video script writer who specializes in creating engaging, conversational scripts for AI avatar presentations. Your scripts are known for being clear, impactful, and perfectly timed for avatar delivery."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }

        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        result = response.json()
        script = result["choices"][0]["message"]["content"].strip()
        
        # Ensure the script doesn't exceed 1300 characters
        if len(script) > 1300:
            script = script[:1297] + "..."
            
        return script
    except Exception as e:
        print(f"Error generating HeyGen input text: {str(e)}")
        return None

@app.route("/api/generate_video", methods=["POST"])
def generate_video():
    session_db = SessionLocal()
    try:
        data = request.get_json()
        case_study_id = data.get('case_study_id')
        
        if not case_study_id:
            return jsonify({"error": "Case study ID is required"}), 400
            
        case_study = session_db.query(CaseStudy).filter_by(id=case_study_id).first()
        if not case_study:
            return jsonify({"error": "Case study not found"}), 404
            
        if not case_study.final_summary:
            return jsonify({"error": "Final summary is required for video generation"}), 400

        # Prevent multiple video generations for the same case study
        if case_study.video_id:
            return jsonify({"error": "A video has already been generated for this case study."}), 400

        # Generate optimized input text for HeyGen
        input_text = generate_heygen_input_text(case_study.final_summary)
        if not input_text:
            return jsonify({"error": "Failed to generate optimized input text"}), 500

        # Prepare the request to HeyGen API V2
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "x-api-key": HEYGEN_API_KEY
        }
        
        payload = {
            "caption": False,
            "dimension": {
                "width": 1280,
                "height": 720
            },
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": HEYGEN_AVATAR_ID,
                        "scale": 1.0,
                        "avatar_style": "normal",
                        "offset": {
                            "x": 0.0,
                            "y": 0.0
                        }
                    },
                    "voice": {
                        "type": "text",
                        "voice_id": HEYGEN_VOICE_ID,
                        "input_text": input_text,
                        "speed": 1.0,
                        "pitch": 0
                    },
                    "background": {
                        "type": "color",
                        "value": "#f6f6fc"
                    }
                }
            ]
        }

        print("Sending request to HeyGen API...")
        response = requests.post(
            f"{HEYGEN_API_BASE_URL}/video/generate",
            headers=headers,
            json=payload
        )

        print(f"HeyGen API response status: {response.status_code}")
        print(f"HeyGen API response: {response.text}")

        if response.status_code == 200:
            video_data = response.json()
            video_id = video_data.get('data', {}).get('video_id')
            
            if not video_id:
                print("No video_id in response:", video_data)
                return jsonify({
                    "status": "error",
                    "error": "No video ID received from HeyGen API"
                }), 500
            
            # Update case study with video information
            case_study.video_id = video_id
            case_study.video_status = 'processing'
            case_study.video_created_at = datetime.now(UTC)  # Use timezone-aware datetime
            session_db.commit()
            print(f"Saved video_id {video_id} to case study {case_study.id}")
            
            return jsonify({
                "status": "success",
                "video_id": video_id,
                "message": "Video generation started"
            })
        else:
            error_message = f"HeyGen API error: {response.text}"
            print(error_message)
            return jsonify({
                "status": "error",
                "error": error_message
            }), response.status_code

    except Exception as e:
        session_db.rollback()
        print(f"Error in generate_video: {str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500
    finally:
        session_db.close()

@app.route("/api/video_status/<video_id>", methods=["GET"])
def check_video_status(video_id):
    if not video_id:
        return jsonify({"error": "Video ID is required"}), 400
        
    try:
        headers = {
            "accept": "application/json",
            "x-api-key": HEYGEN_API_KEY
        }
        
        print(f"Checking status for video ID: {video_id}")
        # Use the correct v1 endpoint for status check
        response = requests.get(
            f"https://api.heygen.com/v1/video_status.get",
            headers=headers,
            params={"video_id": video_id}
        )
        
        print(f"HeyGen API response status: {response.status_code}")
        print(f"HeyGen API response: {response.text}")
        
        if response.status_code == 404:
            print("HeyGen video not ready yet (404).")
            return jsonify({"status": "not_ready", "message": "Video not ready yet"}), 200
        
        if response.status_code != 200:
            error_msg = f"HeyGen API error: {response.text}"
            print(error_msg)
            return jsonify({"error": error_msg}), 500
            
        video_data = response.json()
        print(f"HeyGen video status response: {video_data}")
        
        # Update case study with video status and URL if completed
        session_db = SessionLocal()
        try:
            # Print all video IDs in DB for debugging
            all_ids = [cs.video_id for cs in session_db.query(CaseStudy).all()]
            print("All video IDs in DB:", all_ids)
            case_study = session_db.query(CaseStudy).filter_by(video_id=video_id).first()
            
            if case_study:
                # The status is in the data object
                status = video_data.get("data", {}).get("status")
                print(f"Video status from API: {status}")
                case_study.video_status = status
                
                if status == "completed":
                    # Get the video URL from the API response
                    video_url = video_data.get("data", {}).get("video_url")
                    print(f"Video URL from API: {video_url}")
                    
                    if video_url:
                        case_study.video_url = video_url
                        session_db.commit()
                        print(f"Video URL saved to database: {case_study.video_url}")
                        return jsonify({
                            "status": "completed",
                            "video_url": video_url
                        })
                    else:
                        print("Video completed but no URL in response")
                        return jsonify({
                            "status": "completed",
                            "message": "Video completed but URL not available yet"
                        })
                elif status == "failed":
                    error = video_data.get("data", {}).get("error")
                    return jsonify({
                        "status": "failed",
                        "message": f"Video generation failed: {error}" if error else "Video generation failed"
                    })
                elif status in ["processing", "pending"]:
                    return jsonify({
                        "status": status,
                        "message": "Video is being processed"
                    })
                else:
                    # For any other status, return it as is
                    return jsonify({
                        "status": status,
                        "message": f"Video is {status}"
                    })
                
                session_db.commit()
            
            print(f"No case study found for video ID: {video_id}")
            return jsonify(video_data)
            
        except Exception as db_error:
            session_db.rollback()
            print(f"Database error: {str(db_error)}")
            return jsonify({"error": "Database error occurred"}), 500
        finally:
            session_db.close()
            
    except requests.RequestException as e:
        print(f"Request error: {str(e)}")
        return jsonify({"error": f"Failed to connect to HeyGen API: {str(e)}"}), 500
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)