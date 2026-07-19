import os
import sqlite3
import uuid
import base64

from flask import Flask, render_template, request, jsonify

from groq import Groq
from google import genai

app = Flask(__name__)

# -----------------------------
# Initialize AI Clients
# -----------------------------

# Groq (Text Chat)
groq_client = Groq(
    api_key=os.environ.get("GROQ_API_KEY")
)

# Gemini (Image Understanding)
gemini_client = genai.Client(
    api_key=os.environ.get("GEMINI_API_KEY")
)

DB_FILE = "chat_history.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id TEXT,
            sender TEXT,
            text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


init_db()


@app.route('/')
def home():
    return render_template("index.html")


@app.route('/get_sessions', methods=['GET'])
def get_sessions():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, title FROM rooms ORDER BY created_at DESC"
    )

    rows = cursor.fetchall()
    conn.close()

    return jsonify([
        {
            "id": row[0],
            "title": row[1]
        }
        for row in rows
    ])


@app.route('/create_session', methods=['POST'])
def create_session():
    room_id = str(uuid.uuid4())
    title = request.json.get("title", "New Chat")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO rooms (id, title) VALUES (?, ?)",
        (room_id, title)
    )

    conn.commit()
    conn.close()

    return jsonify({
        "session_id": room_id
    })


@app.route('/get_history/<room_id>', methods=['GET'])
def get_history(room_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT sender, text FROM messages WHERE room_id = ? ORDER BY timestamp ASC",
        (room_id,)
    )

    rows = cursor.fetchall()
    conn.close()

    return jsonify([
        {
            "sender": row[0],
            "text": row[1]
        }
        for row in rows
    ])

@app.route('/chat/<room_id>', methods=['POST'])
def chat(room_id):
    user_message = request.json.get("message", "")
    image_b64 = request.json.get("image")

    if not user_message and not image_b64:
        return jsonify({"error": "Empty message"}), 400

    log_text = user_message if user_message else "[Sent a picture]"

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Save user message
    cursor.execute(
        "INSERT INTO messages (room_id, sender, text) VALUES (?, ?, ?)",
        (room_id, "user", log_text)
    )

    # Set chat title from first message
    cursor.execute(
        "SELECT COUNT(*) FROM messages WHERE room_id = ?",
        (room_id,)
    )

    if cursor.fetchone()[0] == 1 and user_message:
        short_title = (
            user_message[:20] + "..."
            if len(user_message) > 20
            else user_message
        )

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

    # -----------------------------
    # SYSTEM PROMPT
    # -----------------------------
    system_prompt = """
You are a smart, friendly AI assistant for Class 8B students.

Your job is to help students with:
- Mathematics
- Science
- English
- Social Studies
- Coding
- Diagrams
- General Knowledge
- Homework and study tips

Always explain answers clearly and simply.

If you do not know an answer, say so honestly.

Never reveal your reasoning, thinking process, analysis, planning, or chain of thought.

Only provide the final answer.

Never pretend to forget previous messages in the current chat.

If a user asks:
- Who is Ishaan?
- Who created you?
- Who made this AI?
- Who is your developer?

Reply exactly:

"This AI was developed by Ishaan Gopisetty from Group Two, a student who built this AI by spending time and concentration with all of his focus to complete this project for the class and his own group."

Do not mention Ishaan unless asked.

Be polite, friendly, accurate and helpful.
"""

    # -----------------------------
    # IMAGE REQUEST → GEMINI
    # -----------------------------
    if image_b64:

        if "," in image_b64:
            image_b64 = image_b64.split(",")[1]

        try:

            image_bytes = base64.b64decode(image_b64)

            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    user_message or "Describe this image in detail.",
                    {
                        "mime_type": "image/jpeg",
                        "data": image_bytes
                    }
                ]
            )

            ai_response = response.text

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # -----------------------------
    # TEXT REQUEST → GROQ
    # -----------------------------
    else:

        messages_payload = [
            {
                "role": "system",
                "content": system_prompt
            }
        ]

        for sender, text in history:
            role = "assistant" if sender == "bot" else "user"

            messages_payload.append(
                {
                    "role": role,
                    "content": text
                }
            )

        try:

            completion = groq_client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=messages_payload,
                temperature=0.7,
                max_tokens=1024
            )

            ai_response = completion.choices[0].message.content

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # -----------------------------
    # SAVE AI RESPONSE
    # -----------------------------

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO messages (room_id, sender, text) VALUES (?, ?, ?)",
        (room_id, "bot", ai_response)
    )

    conn.commit()
    conn.close()

    return jsonify(
        {
            "response": ai_response
        }
    )

@app.route('/clear_session/<room_id>', methods=['POST'])
def clear_session(room_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM rooms WHERE id = ?",
        (room_id,)
    )

    cursor.execute(
        "DELETE FROM messages WHERE room_id = ?",
        (room_id,)
    )

    conn.commit()
    conn.close()

    return jsonify({
        "status": "success"
    })


if __name__ == "__main__":
    app.run(debug=True)
