import os
import sqlite3
import uuid
from flask import Flask, render_template, request, jsonify, make_response
from groq import Groq

app = Flask(__name__)

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
DB_FILE = "chat_history.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Table for active chat sessions/tabs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_cookie TEXT,
            title TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Table for individual messages inside those sessions
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
    user_cookie = request.cookies.get('user_cookie')
    response = make_response(render_template('index.html'))
    if not user_cookie:
        user_cookie = str(uuid.uuid4())
        response.set_cookie('user_cookie', user_cookie, max_age=60*60*24*365)
    return response

@app.route('/get_sessions', methods=['GET'])
def get_sessions():
    user_cookie = request.cookies.get('user_cookie')
    if not user_cookie:
        return jsonify([])
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM sessions WHERE user_cookie = ? ORDER BY created_at DESC", (user_cookie,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{"id": row[0], "title": row[1]} for row in rows])

@app.route('/create_session', methods=['POST'])
def create_session():
    user_cookie = request.cookies.get('user_cookie')
    if not user_cookie:
        return jsonify({"error": "No user identification found"}), 400
    
    session_id = str(uuid.uuid4())
    title = request.json.get('title', 'New Chat')
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO sessions (id, user_cookie, title) VALUES (?, ?, ?)", (session_id, user_cookie, title))
    conn.commit()
    conn.close()
    return jsonify({"session_id": session_id, "title": title})

@app.route('/get_history/<session_id>', methods=['GET'])
def get_history(session_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT sender, text FROM messages WHERE session_id = ? ORDER BY timestamp ASC", (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{"sender": row[0], "text": row[1]} for row in rows])

@app.route('/chat/<session_id>', methods=['POST'])
def chat(session_id):
    user_message = request.json.get('message')
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Update session title if it's the very first user message
    cursor.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,))
    if cursor.fetchone()[0] == 0:
        short_title = user_message[:20] + "..." if len(user_message) > 20 else user_message
        cursor.execute("UPDATE sessions SET title = ? WHERE id = ?", (short_title, session_id))

    # Save user message
    cursor.execute("INSERT INTO messages (session_id, sender, text) VALUES (?, ?, ?)", (session_id, 'user', user_message))
    conn.commit()

    # Get logs context
    cursor.execute("SELECT sender, text FROM messages WHERE session_id = ? ORDER BY timestamp ASC LIMIT 20", (session_id,))
    rows = cursor.fetchall()
    conn.close()

    messages_payload = [{"role": "system", "content": "You are a helpful assistant for Class 8B students."}]
    for row in rows:
        role = "user" if row[0] == "user" else "assistant"
        messages_payload.append({"role": role, "content": row[1]})

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages_payload
        )
        ai_response = completion.choices[0].message.content

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO messages (session_id, sender, text) VALUES (?, ?, ?)", (session_id, 'bot', ai_response))
        conn.commit()
        conn.close()

        return jsonify({"response": ai_response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/clear_session/<session_id>', methods=['POST'])
def clear_session(session_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})

if __name__ == '__main__':
    app.run(debug=True)
