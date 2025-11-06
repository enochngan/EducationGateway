from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from dotenv import load_dotenv
import os
import uvicorn
# Create the app
load_dotenv()

app = FastAPI()



app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    # your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    
)

@app.post("/api/chat")
async def chat(request: Request):
    data  = await request.json()
    user_message = data.get("input")
    if user_message: 
        print(f"Received Message from User: {user_message} ")
    client = genai.Client(api_key = os.environ["GEMINI_API_KEY"])
    
    response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=user_message,
    
    
)
    return {"reply": response.text}
def chat():
    user_message = 'hi'
    client = genai.Client(api_key = os.environ["GEMINI_API_KEY"])
    
    response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=user_message,
    
    
)
    return response.text
if __name__ == "__main__":
   # print(chat())
    uvicorn.run(
        "main:app", 
        host = "0.0.0.0", 
        port = 8000, 
        reload = True,
    )
    