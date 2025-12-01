from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google import genai
from google.genai import types
from dotenv import load_dotenv
import os
import uvicorn
import requests
import json
import re
import logging
# Create the app
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    "Student_Information": {
      "columns": {
        "student_id": "bigint PRIMARY KEY",
        "name": "text",
        "email": "text UNIQUE"
      },
      "description": "Stores basic student info, including name and email."
    },
    "Homework_Assignments": {
      "columns": {
        "homework_id": "text PRIMARY KEY",
        "title": "text",
        "due_date": "timestamptz",
        "total_points": "int",
        "average_grade": "int"
      },
      "description": "Each homework assignment with metadata like title, total points, average grade, and due date."
    },
    "student_homeworks": {
      "columns": {
        "student_id": "bigint (FK -> Student_Information.student_id)",
        "homework_id": "text (FK -> Homework_Assignments.homework_id)",
        "grade": "float8"
      },
      "primary_key": ["student_id", "homework_id"],
      "description": "Join table mapping students to homework assignments with their individual grade."
    },
    "user_information": {
      "columns": {
        "username": "varchar PRIMARY KEY",
        "password": "varchar",
        "buid": "text UNIQUE",
        "Student_Name": "text"
      },
      "description": "Stores app login credentials and user metadata (BU ID and linked student name)."
    }
  },
  "relationships": [
    {
      "from_table": "student_homeworks",
      "from_column": "student_id",
      "to_table": "Student_Information",
      "to_column": "student_id",
      "relationship_type": "many-to-one"
    },
    {
      "from_table": "student_homeworks",
      "from_column": "homework_id",
      "to_table": "Homework_Assignments",
      "to_column": "homework_id",
      "relationship_type": "many-to-one"
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

    translate_prompt = f"""
    You are a text-to-SQL assistant for a Supabase/PostgreSQL database.
    The schema is:
      {schema_info}
    
    Important guidelines:
    - When the user asks for "my grade" or "my homework", query the student_homeworks table directly
    - DO NOT use placeholders like 'CURRENT_USER' - the student_id will be provided separately
    - Keep queries simple and direct
    - Only query student_homeworks, Homework_Assignments, and Student_Information tables
    
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
    # Extract requested student_id (req_id) from generated SQL or the original message
    buid_match = re.search(r"\b(\d{7,9})\b", sql_query)
    req_id = buid_match.group(1) if buid_match else None
    if not req_id:
      buid_match_msg = re.search(r"\b(\d{7,9})\b", user_message)
      req_id = buid_match_msg.group(1) if buid_match_msg else None

    # If still no req_id, assume the user meant themselves
    if not req_id:
      req_id = caller_buid

    logger.info(f"[AUTHORIZATION] req_id={req_id}, caller_buid={caller_buid}, caller_role={caller_role}")
    
    # Authorization: non-admins may only query their own buid
    if caller_role != 'admin':
      if not caller_buid:
        return {"reply": "Caller BU ID unknown; cannot authorize request."}
      if not req_id:
        return {"reply": "Could not determine target BU ID from your request. Please include the student's BU ID."}
      if str(caller_buid) != str(req_id):
        return {"reply": "Sorry, you are not allowed to see that."}
    
    # CRITICAL: Force inject student_id filter for non-admin users to prevent data leaks
    # This ensures users can ONLY see their own data regardless of what SQL the LLM generates
    if caller_role != 'admin' and 'student_homeworks' in sql_query.lower():
      # Check if student_id filter already exists with the correct value
      if f"student_id = {req_id}" not in sql_query and f"student_id={req_id}" not in sql_query:
        # Inject student_id constraint
        if 'where' in sql_query.lower():
          # Append to existing WHERE - find the WHERE clause and add condition
          sql_query = re.sub(
            r'(WHERE|where)\s+',
            f'WHERE student_id = {req_id} AND ',
            sql_query,
            count=1
          )
        else:
          # Add new WHERE clause - insert before ORDER BY, LIMIT, or at end
          if 'order by' in sql_query.lower() or 'limit' in sql_query.lower():
            sql_query = re.sub(
              r'(ORDER BY|order by|LIMIT|limit)',
              f'WHERE student_id = {req_id} \\1',
              sql_query,
              count=1
            )
          else:
            sql_query = sql_query + f" WHERE student_id = {req_id}"
    
    logger.info(f"[SQL FINAL] {sql_query}")
    
    headers = {"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"}
    print(f"Using Supabase URL: {supabase_url}")
    print(f"Using Supabase Key: {'SUPABASE_SERVICE_ROLE_KEY' if os.environ.get('SUPABASE_SERVICE_ROLE_KEY') else 'NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY'}")
    print(f"SQL Query: {sql_query}")
    query_resp = requests.post(
      f"{supabase_url}/rest/v1/rpc/run_sql",
      headers=headers,
      json={"sql": sql_query}
    )
    # Log status and raw body for easier debugging
    print(f"Supabase HTTP status: {query_resp.status_code}")
    print(f"Supabase raw body: {query_resp.text}")
    try:
      resp_json = query_resp.json()
    except ValueError:
      resp_json = {"raw": query_resp.text}
    print(f"query response json: {resp_json}")
    
    # CRITICAL SAFETY CHECK: For non-admin users, verify response only contains their data
    if caller_role != 'admin' and isinstance(resp_json, list):
      # Check if response contains student_id field
      if resp_json and isinstance(resp_json[0], dict) and 'student_id' in resp_json[0]:
        # Filter to only include rows matching caller's BUID
        filtered = [row for row in resp_json if str(row.get('student_id')) == str(caller_buid)]
        if len(filtered) != len(resp_json):
          logger.warning(f"[SECURITY] Filtered {len(resp_json) - len(filtered)} unauthorized rows from response")
          resp_json = filtered
        # If no rows match caller's BUID after filtering, return error
        if not resp_json:
          return {"reply": "No data found for your account."}
    
    query_resp_text = json.dumps(resp_json, indent=2)

    natural_language = f"""
    Youre task is to convert the following output for a postgres database to a formatted natural language response: 

    {query_resp_text}

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
    