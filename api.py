import os
from flask import Flask, request, jsonify
from app_streamlit import process_query 
import streamlit as st  
from contextlib import nullcontext

app = Flask(__name__)

@app.route('/recommend', methods=['GET'])
def recommend():
    query = request.args.get('query')
    if not query:
        return jsonify({"error": "Missing 'query' parameter in URL"}), 400

    
    st.status = lambda *args, **kwargs: nullcontext()
    st.spinner = lambda *args, **kwargs: nullcontext()
    st.error = lambda x: print(f"Streamlit Error in API: {x}")

    
    os.environ["HF_TOKEN"] = os.environ.get("HF_TOKEN", "")
    os.environ["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY", "")
    st.secrets["HF_TOKEN"] = os.environ["HF_TOKEN"]
    st.secrets["GEMINI_API_KEY"] = os.environ["GEMINI_API_KEY"]

    
    response = process_query(query)
    return jsonify({"result": response})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
