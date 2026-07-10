import os
import sqlite3
import uuid
from flask import Flask, render_template, request, jsonify, make_response
from groq import Groq

# We added template_folder='.' so Flask looks in your main folder for index.html!
app = Flask(__name__, template_folder='.')

# Initialize Groq client
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

DB_FILE = "chat_history.db"

def init_db():
    """Creates the database table if it doesn't exist."""
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
    # Track unique users using a browser cookie
    session_id = request.cookies.get('session_id')
    response = make_response(render_template('index.html'))
    
    if not session_id:
        session_id = str(uuid.uuid4())
        response.set_cookie('session_id', session_id, max_age=60*60*24*365) # 1 year expiry
        
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
    
    history = [{"sender": row[0], "text": row[1]} for row in rows]
    return jsonify(history)

@app.route('/chat', methods=['POST'])
def chat():
    session_id = request.cookies.get('session_id')
    if not session_id:
        return jsonify({"error": "No session found"}), 400

    user_message = request.json.get('message')
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    # 1. Save user message to database
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (session_id, sender, text) VALUES (?, ?, ?)", (session_id, 'user', user_message))
    conn.commit()

    # 2. Fetch recent chat logs for context so the AI remembers the past conversation
    cursor.execute("SELECT sender, text FROM messages WHERE session_id = ? ORDER BY timestamp ASC LIMIT 20", (session_id,))
    rows = cursor.fetchall()
    conn.close()

    # Format history for Groq
    messages_payload = [{"role": "system", "content": "You are a helpful assistant for Class 8B students."}]
    for row in rows:
        role = "user" if row[0] == "user" else "assistant"
        messages_payload.append({"role": role, "content": row[1]})

    try:
        # 3. Get AI response
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages_payload
        )
        ai_response = completion.choices[0].message.content

        # 4. Save AI response to database
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO messages (session_id, sender, text) VALUES (?, ?, ?)", (session_id, 'bot', ai_response))
        conn.commit()
        conn.close()

        return jsonify({"response": ai_response})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/clear_history', methods=['POST'])
def clear_history():
    session_id = request.cookies.get('session_id')
    if session_id:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()
    return jsonify({"status": "cleared"})

if __name__ == '__main__':
    app.run(debug=True)
