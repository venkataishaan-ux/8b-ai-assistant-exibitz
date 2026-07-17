import os
import sqlite3
import uuid
from flask import Flask, render_template, request, jsonify
from groq import Groq

app = Flask(__name__)

# Initialize Groq client securely using environment variables
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

DB_FILE = "chat_history.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rooms (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT,
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
    return render_template('index.html')

@app.route('/get_sessions', methods=['GET'])
def get_sessions():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM rooms ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{"id": row[0], "title": row[1]} for row in rows])

@app.route('/create_session', methods=['POST'])
def create_session():
    room_id = str(uuid.uuid4())
    title = request.json.get('title', 'New Chat')
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO rooms (id, title) VALUES (?, ?)", (room_id, title))
    conn.commit()
    conn.close()
    return jsonify({"session_id": room_id})

@app.route('/get_history/<room_id>', methods=['GET'])
def get_history(room_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT sender, text FROM messages WHERE room_id = ? ORDER BY timestamp ASC", (room_id,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{"sender": row[0], "text": row[1]} for row in rows])

@app.route('/chat/<room_id>', methods=['POST'])
def chat(room_id):
    user_message = request.json.get('message', '')
    image_b64 = request.json.get('image')

    if not user_message and not image_b64:
        return jsonify({"error": "Empty message"}), 400

    log_text = user_message if user_message else "[Sent a picture]"

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Save the user's message
    cursor.execute(
        "INSERT INTO messages (room_id, sender, text) VALUES (?, ?, ?)",
        (room_id, "user", log_text)
    )

    # Set the chat title from the first message
    cursor.execute("SELECT COUNT(*) FROM messages WHERE room_id = ?", (room_id,))
    if cursor.fetchone()[0] == 1 and user_message:
        short_title = user_message[:20] + "..." if len(user_message) > 20 else user_message
        cursor.execute(
            "UPDATE rooms SET title = ? WHERE id = ?",
            (short_title, room_id)
        )

    conn.commit()

    # Load previous conversation
    cursor.execute(
        "SELECT sender, text FROM messages WHERE room_id = ? ORDER BY timestamp ASC",
        (room_id,)
    )
    history = cursor.fetchall()

    conn.close()

    # Build message history
   messages_payload = [
    {
        "role": "system",
        "content": """
You are a smart, friendly AI assistant for Class 8B students.

If a user asks:
- "Who is Ishaan?"
- "Who created you?"
- "Who made this AI?"
- "Who is your developer?"

Reply that:

"This AI was developed by Ishaan Gopisetty, a student who built it using Python, Flask, SQLite, and the Groq API. He designed the application and improved it with AI assistance for debugging and development."

Do not mention Ishaan unless the user asks about him or who created the AI.
"""
    }
]
    # Replace the last user message with image + text if an image was sent
    if image_b64:
        if "," in image_b64:
            image_b64 = image_b64.split(",")[1]

        messages_payload[-1] = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": user_message
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_b64}"
                    }
                }
            ]
        }

    try:
        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=messages_payload,
            temperature=0.7,
            max_tokens=1024
        )

        ai_response = completion.choices[0].message.content

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO messages (room_id, sender, text) VALUES (?, ?, ?)",
            (room_id, "bot", ai_response)
        )

        conn.commit()
        conn.close()

        return jsonify({"response": ai_response})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": "Failed to process request"}), 500
@app.route('/clear_session/<room_id>', methods=['POST'])
def clear_session(room_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
    cursor.execute("DELETE FROM messages WHERE room_id = ?", (room_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True)
