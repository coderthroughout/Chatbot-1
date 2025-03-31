# app.py
from flask import Flask, request, jsonify
from supabase import create_client, Client
import os
import requests
import pandas as pd
from io import StringIO
from dotenv import load_dotenv
from flask_cors import CORS
import logging

load_dotenv()

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.DEBUG)

supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')
perplexity_api_key = os.getenv('PERPLEXITY_API_KEY')
claude_api_key = os.getenv('CLAUDE_API_KEY')

supabase: Client = create_client(supabase_url, supabase_key)


@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')
        user = supabase.auth.sign_up({
            "email": email,
            "password": password
        })
        return jsonify(user=user)
    except Exception as e:
        error_message = str(e)
        if "Email rate limit exceeded" in error_message:
            return jsonify(error="Email rate limit exceeded. Please try again later."), 429
        elif "rate limit" in error_message.lower():
            return jsonify(error="Rate limit exceeded. Please try again later."), 429
        logging.error(f"Error during registration: {e}")
        return jsonify(error=error_message), 500


@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')
        user = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        return jsonify(user=user)
    except Exception as e:
        logging.error(f"Error during login: {e}")
        return jsonify(error=str(e)), 500


@app.route('/query', methods=['POST'])
def query():
    try:
        data = request.json
        query = data.get('query')
        user_id = data.get('user_id')  # Assuming user_id is sent from the frontend

        # Check if query exists in Supabase
        query_data = supabase.table('queries').select('*').eq('user_id', user_id).eq('query', query).execute()
        if query_data.data:
            return jsonify(query_data.data[0]['response'])

        # Use Perplexity API to research
        headers = {
            "Authorization": f"Bearer {perplexity_api_key}"
        }
        perplexity_response = requests.post('https://api.perplexity.ai/research', json={"query": query},
                                            headers=headers)
        research_data = perplexity_response.json()

        # Save research data to CSV
        df = pd.DataFrame(research_data)
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_data = csv_buffer.getvalue()

        # Save CSV data to Supabase
        supabase.storage.from_('research_data').upload(f"{user_id}_{query}.csv", csv_data.encode('utf-8'))

        # Use Claude API to process and interact
        claude_response = requests.post('https://api.claude.ai/process', json={"researchData": research_data},
                                        headers={"Authorization": f"Bearer {claude_api_key}"})
        interaction_data = claude_response.json()

        # Save query and response to Supabase
        supabase.table('queries').insert([{
            "user_id": user_id,
            "query": query,
            "response": interaction_data
        }]).execute()

        return jsonify(interaction_data)
    except Exception as e:
        logging.error(f"Error during query processing: {e}")
        return jsonify(error=str(e)), 500


if __name__ == '__main__':
    app.run(port=3000)
