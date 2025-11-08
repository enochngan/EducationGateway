from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from dotenv import load_dotenv
import os
import uvicorn
import requests
import json
import re
# Create the app
load_dotenv()

app = FastAPI()

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
    data  = await request.json()
    
    user_message = data.get('input')
    supabase_url = os.environ['NEXT_PUBLIC_SUPABASE_URL']
    supabase_key = os.environ['NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY']
    
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
    print(f"SQl Query: {sql_query}")
    query_resp = requests.post(
        f"{supabase_url}/rest/v1/rpc/run_sql",
        headers=headers,
        json={"sql": sql_query}
    )
    print(f"query response: {query_resp.json()}")
    query_resp = json.dumps(query_resp.json(), indent= 2)
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
    supabase_url = os.environ['NEXT_PUBLIC_SUPABASE_URL']
    supabase_key = os.environ['NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY']
    
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
    print(f"SQl Query: {sql_query}")
    query_resp = requests.post(
        f"{supabase_url}/rest/v1/rpc/run_sql",
        headers=headers,
        json={"sql": sql_query}
    )
    print(f"query response: {query_resp.json()}")
    query_resp = json.dumps(query_resp.json(), indent= 2)
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
    