import os
import sqlite3
import uuid
import base64
from flask import Flask, render_template, request, jsonify, make_response
from groq import Groq

app = Flask(__name__)

# Initialize Groq client
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

DB_FILE = "chat_history.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            sender TEXT,
            text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    session_id = request.cookies.get('session_id')
    response = make_response(render_template('index.html'))
    if not session_id:
        session_id = str(uuid.uuid4())
        response.set_cookie('session_id', session_id, max_age=60*60*24*365)
    return response

@app.route('/get_history', methods=['GET'])
def get_history():
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify([])
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT sender, text FROM messages WHERE session_id = ? ORDER BY timestamp ASC", (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{"sender": row[0], "text": row[1]} for row in rows])

@app.route('/chat', methods=['POST'])
def chat():
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({"error": "No session found"}), 400

    user_message = request.json.get('message', '')
    image_b64 = request.json.get('image') # Base64 string from frontend

    if not user_message and not image_b64:
        return jsonify({"error": "Empty message"}), 400

    # Save text log to history
    log_text = user_message if user_message else "[Sent an image]"
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (session_id, sender, text) VALUES (?, ?, ?)", (session_id, 'user', log_text))
    conn.commit()
    conn.close()

    # Build multimodal payload for Groq Vision
    content_list = []
    if user_message:
        content_list.append({"type": "text", "text": user_message})
    if image_b64:
        content_list.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}
        })

    messages_payload = [
        {"role": "system", "content": "You are a smart, friendly AI assistant for Class 8B students. You can analyze both text and images."},
        {"role": "user", "content": content_list}
    ]

    try:
        # Using Groq's high-speed vision model
        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=messages_payload
        )
        ai_response = completion.choices[0].message.content
