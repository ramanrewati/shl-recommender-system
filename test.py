import os
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY")) 


for model_info in genai.list_models():
    print(model_info.name)