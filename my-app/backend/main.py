from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google import genai
from google.genai import types
from dotenv import load_dotenv
import os
import sys
import uvicorn
import requests
import json
import re
import logging

# Add backend directory to path to allow importing privacy_system
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from privacy_system import PrivacySystem
# Create the app
load_dotenv()

# Configure logging
# Log to both console and file
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
date_format = '%Y-%m-%d %H:%M:%S'

# Create logs directory if it doesn't exist
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

# Configure logging with both file and console handlers
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    datefmt=date_format,
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'app.log')),
        logging.StreamHandler()  # Console output
    ]
)
logger = logging.getLogger(__name__)
logger.info("Logging initialized - logs will appear in console and logs/app.log")

app = FastAPI()


@app.post("/api/login")
async def login(request: Request):
  data = await request.json()
  email = data.get('email')
  if not email:
    return JSONResponse({"error": "email required"}, status_code=400)
  # Set an HttpOnly cookie with the username (for dev/demo use). In production use a secure session or JWT.
  resp = JSONResponse({"ok": True, "username": email})
  resp.set_cookie(key="session_username", value=email, httponly=True, samesite="lax")
  return resp

schema_info = {
  "tables": {
    "Homework_Assignments": {
      "primary_key": ["homework_id"],
      "columns": {
        "homework_id":    { "type": "text" },
        "title":          { "type": "text" },
        "due_date":       { "type": "timestamptz" },
        "total_points":   { "type": "int8" },
        "average_grade":  { "type": "int8" }
      }
    },

    "student_homeworks": {
      "primary_key": ["student_id", "homework_id"],
      "columns": {
        "student_id":   { "type": "int8" },
        "homework_id":  { "type": "text" },
        "grade":        { "type": "float8" }
      },
      "foreign_keys": {
        "student_id":   "student_information.buid",
        "homework_id":  "Homework_Assignments.homework_id"
      }
    },

    "student_information": {
      "primary_key": ["buid"],
      "columns": {
        "buid":   { "type": "int8" },
        "name":   { "type": "text" },
        "email":  { "type": "text", "sensitive": "true" }
      }
    },

    "user_information": {
      "primary_key": ["username"],
      "columns": {
        "username":     { "type": "text" },
        "password":     { "type": "varchar", "sensitive": "true" },
        "buid":         { "type": "int8" },
        "Student_Name": { "type": "text" },
        "role":         { "type": "text" }
      },
      "foreign_keys": {
        "buid": "student_information.buid"
      }
    }
  },

  "relationships": [
    {
      "from_table": "student_homeworks",
      "from_column": "student_id",
      "to_table": "student_information",
      "to_column": "buid"
    },
    {
      "from_table": "student_homeworks",
      "from_column": "homework_id",
      "to_table": "Homework_Assignments",
      "to_column": "homework_id"
    },
    {
      "from_table": "user_information",
      "from_column": "buid",
      "to_table": "student_information",
      "to_column": "buid"
    }
  ]
}




app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    # your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    
)

@app.post("/api/chat")
async def query_database(request: Request):
  data = await request.json()

  user_message = data.get('input')
  if not user_message:
    return {"error": "no input provided"}

  # Resolve session username from server-side cookie
  session_username = request.cookies.get('session_username')
  if not session_username:
    return {"error": "Caller identity missing. Please login via the landing page."}

  # Resolve supabase connection info early
  supabase_url = os.environ.get('NEXT_PUBLIC_SUPABASE_URL') or os.environ.get('SUPABASE_URL')
  supabase_key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or os.environ.get('NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY')

  # Lookup the caller's buid and role from user_information
  identifier_safe = re.sub(r"[^A-Za-z0-9_@.\- ]", "", str(session_username))
  user_sql = f"SELECT buid, role FROM user_information WHERE username = '{identifier_safe}' LIMIT 1"
  logger.info(f"[USER LOOKUP] SQL: {user_sql}")
  user_resp = requests.post(f"{supabase_url}/rest/v1/rpc/run_sql", headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}", "Content-Type": "application/json"}, json={"sql": user_sql})
  try:
    user_json = user_resp.json()
  except ValueError:
    user_json = {"raw": user_resp.text}
  
  logger.info(f"[USER LOOKUP] Response: {user_json}")

  # Normalize possible shapes for a row
  user_row = None
  if isinstance(user_json, list) and user_json:
    if isinstance(user_json[0], dict):
      user_row = user_json[0]
  elif isinstance(user_json, dict):
    for k in ("rows", "data", "result"):
      if k in user_json and isinstance(user_json[k], list) and user_json[k]:
        user_row = user_json[k][0]
        break

  if not user_row:
    return {"error": "Unable to resolve caller identity from username. Please ensure your account exists."}

  caller_role = (user_row.get('role') or user_row.get('Role') or 'user')
  if isinstance(caller_role, str):
    caller_role = caller_role.lower()
  caller_buid = user_row.get('buid') or user_row.get('BUID') or user_row.get('student_id')
  
  logger.info(f"[IDENTITY] session_username={session_username}, caller_buid={caller_buid}, caller_role={caller_role}")

  # Only treat the message as a database query if it contains the word 'query' (case-insensitive).
  # Otherwise, behave as a regular LLM chat endpoint.
  if 'query' in user_message.lower():
    supabase_url = os.environ.get('NEXT_PUBLIC_SUPABASE_URL') or os.environ.get('SUPABASE_URL')
    # Prefer the service role key for server-side queries (bypasses RLS). Fall back to the publishable key if not set.
    supabase_key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or os.environ.get('NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY')

    # Initialize PrivacySystem
    privacy_system = PrivacySystem(supabase_url, supabase_key)
    
    # STEP 1: Create privacy views BEFORE query generation
    # This ensures sensitive columns are protected at the database level
    if not privacy_system.create_privacy_views(caller_role, caller_buid):
      logger.warning("[PRIVACY] Failed to create privacy views, continuing with query modification")

    translate_prompt = f"""
    You are a text-to-SQL assistant for a Supabase/PostgreSQL database.
    The schema is:
      {schema_info}
    
    Important guidelines:
    - When the user asks for "my grade" or "my homework", query the student_homeworks table directly
    - DO NOT use placeholders like 'CURRENT_USER' - the student_id will be provided separately
    - Keep queries simple and direct
    - Table names are all lowercase: student_homeworks, homework_assignments, student_information, user_information
    - DO NOT use capital letters in table names (e.g., use "user_information" NOT "User_Information")
    - Note: Sensitive columns (password, email, username, buid) are automatically protected by views
    
    Translate this natural language question into SQL:
    "{user_message}"
    
    Return only the SQL query without any placeholders for user identity.
    """

    if user_message:
      print(f"Received Message from User (query): {user_message}")

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    sql_query = client.models.generate_content(
      model="gemini-2.5-flash",
      contents=translate_prompt,
    )
    sql_query = sql_query.candidates[0].content.parts[0].text.strip("```sql").strip("```").strip().rstrip(";")
    logger.info(f"[SQL GENERATED] {sql_query}")
    
    # STEP 2: Modify query to use secure views (protects sensitive columns)
    sql_query = privacy_system.modify_query_for_privacy(sql_query, caller_role, caller_buid)
    
    logger.info(f"[SQL FINAL] {sql_query}")
    
    headers = {
    "apikey": supabase_key,
    "Authorization": f"Bearer {supabase_key}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}
    print(f"Using Supabase URL: {supabase_url}")
    print(f"Using Supabase Key: {'SERVICE_KEY' if os.environ.get('SUPABASE_SERVICE_ROLE_KEY') else 'PUBLISHABLE_KEY'}")
    print(f"SQL Query: {sql_query}")

    query_resp = requests.post(
        f"{supabase_url}/rest/v1/rpc/run_sql",
        headers=headers,
        json={"sql": sql_query}
    )

    print("Status:", query_resp.status_code)
    print("Response:", query_resp.text)

    # Log status and raw body for easier debugging
    print(f"Supabase HTTP status: {query_resp.status_code}")
    print(f"Query  response: {query_resp.json()}")
    print(f"Supabase raw body: {query_resp.text}")
    try:
      resp_json = query_resp.json()
    except ValueError:
      resp_json = {"raw": query_resp.text}
    print(f"query response json: {resp_json}")
    
    # Handle null/empty responses - might be due to views filtering too aggressively
    if resp_json is None or (isinstance(resp_json, list) and len(resp_json) == 0):
      logger.warning(f"[QUERY RESULT] Query returned null/empty. SQL: {sql_query}")
      # Try querying without views to see if data exists
      # This is a debug step - in production you might want to handle this differently
      if 'user_information_secure' in sql_query or 'student_information_secure' in sql_query:
        logger.info("[QUERY RESULT] Attempting to diagnose view filtering issue")
        # The views might be too restrictive - check if original tables have data
        return {"reply": "No data found. This might be due to privacy filtering. Please check your query or contact an administrator."}
    
    # STEP 4: Check authorization AFTER query execution (safety check)
    # All authorization logic is now handled in PrivacySystem
    is_authorized, auth_error = privacy_system.validate_query_authorization(sql_query, caller_role, caller_buid)
    if not is_authorized:
      return {"reply": auth_error or "Unauthorized access."}
    
    # STEP 5: Filter sensitive data and verify result authorization
    # Only process if we have actual data
    if resp_json is not None:
      resp_json, is_authorized = privacy_system.verify_result_authorization(resp_json, caller_role, caller_buid)
      if not is_authorized:
        return {"reply": "No data found for your account."}
      
      # Additional filtering of sensitive columns
      resp_json = privacy_system.filter_sensitive_data(resp_json, caller_role, caller_buid)
    else:
      return {"reply": "Query executed successfully but returned no data."}
    
    query_resp_text = json.dumps(resp_json, indent=2)

    # Get user's name for personalization (from the user_row we fetched earlier)
    user_name = user_row.get('Student_Name') or user_row.get('student_name') or user_row.get('name') if user_row else None
    
    # Build personalized context
    user_context = ""
    if user_name:
      user_context = f"The user asking this question is {user_name} (BU ID: {caller_buid}). "
    elif caller_buid:
      user_context = f"The user asking this question has BU ID: {caller_buid}. "
    
    user_context += "IMPORTANT: When presenting grades, homework, or student data, make it clear that this is THEIR OWN data. Use phrases like 'Your grade', 'Your homework', 'You have', 'You received', etc. Always personalize the response."

    natural_language = f"""
    Your task is to convert the following database query output into a clear, natural language response.
    
    {user_context}
    
    Database output:
    {query_resp_text}
    
    Instructions:
    - Always refer to the data as belonging to the user (use "your", "you", etc.)
    - Be clear and friendly
    - If showing grades, say "Your grade is..." or "You received..."
    - If showing multiple items, say "Your grades are..." or "You have..."
    - Make it personal and clear that this is their own information
    
    Convert the database output to natural language:
    """
    language_output = client.models.generate_content(
      model="gemini-2.5-flash",
      contents=natural_language,
    )
    language_output = language_output.candidates[0].content.parts[0].text.strip("```sql").strip("```").strip()
    return {"reply": language_output}

  # Non-query flow: regular conversational LLM
  try:
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    convo_prompt = f"""
    Respond concisely to the user's message as a helpful assistant.
    User: {user_message}
    """
    conv = client.models.generate_content(
      model="gemini-2.5-flash",
      contents=convo_prompt,
    )
    reply_text = conv.candidates[0].content.parts[0].text.strip()
    return {"reply": reply_text}
  except Exception as e:
    return {"error": f"LLM error: {str(e)}"}
# def chat():
#     user_message = 'hi'
#     client = genai.Client(api_key = os.environ["GEMINI_API_KEY"])
    
#     response = client.models.generate_content(
#     model="gemini-2.5-flash",
#     contents=user_message,
    
    
# )
#    return response.text
def query_database():
    #data  = "I want to see all user information"
    schema_info = ""
    with open('schema.json', 'r') as f:
        schema_info = f.read()
    
    user_message = "I want to see all the user information"
    supabase_url = os.environ.get('NEXT_PUBLIC_SUPABASE_URL') or os.environ.get('SUPABASE_URL')
    supabase_key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or os.environ.get('NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY')

    translate_prompt = f"""
    You are a text-to-SQL assistant for a Supabase/PostgreSQL database.
    The schema is:
        {schema_info}
    Translate this natural language question into SQL:
    "{user_message}"
    Return only the SQL query.
    """
    
    if user_message: 
        print(f"Received Message from User: {user_message} ")
        
        
    client = genai.Client(api_key = os.environ["GEMINI_API_KEY"])
    
    
    sql_query = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=translate_prompt,
    
)
    sql_query = sql_query.candidates[0].content.parts[0].text.strip("```sql").strip("```").strip().rstrip(";")
    headers = {"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"}
    print(f"Using Supabase URL: {supabase_url}")
    print(f"Using Supabase Key: {'SUPABASE_SERVICE_ROLE_KEY' if os.environ.get('SUPABASE_SERVICE_ROLE_KEY') else 'NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY'}")
    print(f"SQL Query: {sql_query}")
    query_resp = requests.post(
        f"{supabase_url}/rest/v1/rpc/run_sql",
        headers=headers,
        json={"sql": sql_query}
    )
    print(f"Supabase HTTP status: {query_resp.status_code}")
    print(f"Supabase raw body: {query_resp.text}")
    try:
        resp_json = query_resp.json()
    except ValueError:
        resp_json = {"raw": query_resp.text}
    print(f"query response json: {resp_json}")
    query_resp = json.dumps(resp_json, indent= 2)
    natural_language = f"""
    Youre task is to convert the following output for a postgres database to a formatted natural language response: 
    
    {query_resp}
    
    """
    language_output = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=natural_language,
    
)
    language_output = language_output.candidates[0].content.parts[0].text.strip("```sql").strip("```").strip()
    return {"reply": language_output}
if __name__ == "__main__":
    #print(chat())
    uvicorn.run(
        "main:app", 
        host = "0.0.0.0", 
        port = 8000, 
        reload = True,
    )
    query_database()
    