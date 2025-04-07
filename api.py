import os
from flask import Flask, request, jsonify
from api_helper import process_query  # Your custom function

app = Flask(__name__)

@app.route('/recommend', methods=['GET'])
def recommend():
    query = request.args.get('query')
    if not query:
        return jsonify({"error": "Missing 'query' parameter in URL"}), 400

    # Set up environment variables for use inside app_streamlit
    os.environ["HF_TOKEN"] = os.environ.get("HF_TOKEN", "")
    os.environ["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY", "")

    response = process_query(query)
    return jsonify({"result": response})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))