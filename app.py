import os
import sqlite3
import uuid

from flask import Flask, render_template, request, jsonify
from groq import Groq

app = Flask(__name__)

client = Groq(
    api_key=os.environ.get("GROQ_API_KEY")
)

@app.route('/chat/<room_id>', methods=['POST'])
def chat(room_id):
    user_message = request.json.get('message', '')
    image_b64 = request.json.get('image')

    if not user_message and not image_b64:
        return jsonify({"error": "Empty message"}), 400

    log_text = user_message if user_message else "[Sent a picture]"

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Save user message
    cursor.execute(
        "INSERT INTO messages (room_id, sender, text) VALUES (?, ?, ?)",
        (room_id, 'user', log_text)
    )

    # Set chat title from first message
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

    messages_payload = [
        {
            "role": "system",
            "content": "You are a smart, friendly AI assistant for Class 8B students. Help them understand school questions, math, and diagrams easily."
        }
    ]

    # Add previous messages
    for sender, text in history:
        role = "assistant" if sender == "bot" else "user"
        messages_payload.append({
            "role": role,
            "content": text
        })

    # If the current message contains an image, replace the last user
    # message with the multimodal version.
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
            model="llama-3.2-11b-vision-preview",
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
