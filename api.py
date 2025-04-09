import os
from flask import Flask, request, jsonify
from api_helper import process_query, parse_recommendations  

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"}), 200

@app.route('/recommend', methods=['POST'])
def recommend():
    data = request.get_json()
    if not data or "query" not in data:
        return jsonify({"error": "Missing 'query' field in JSON payload"}), 400

    query = data["query"]


    os.environ["HF_TOKEN"] = os.environ.get("HF_TOKEN", "")
    os.environ["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY", "")


    response_text = process_query(query)
    if response_text is None:
        return jsonify({"error": "Unable to process query"}), 500


    recommendations = parse_recommendations(response_text)
    return jsonify(recommendations), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))