import os
import base64
from flask import Flask, request, jsonify, render_template_string
from groq import Groq

app = Flask(__name__)

# Paste your private Groq API key here!
GROQ_API_KEY = "YOUR_GROQ_API_KEY_HERE"
client = Groq(api_key="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")

# Simple trick to turn a uploaded picture file into format the AI can read
def encode_image(file_storage):
    return base64.b64encode(file_storage.read()).decode('utf-8')

@app.route('/')
def home():
    # Serves your layout from index.html
    with open('index.html', 'r', encoding='utf-8') as f:
        return render_template_string(f.read())

@app.route('/ask', methods=['POST']) # Handles incoming messages
def ask():
    user_message = request.form.get('message', '')
    image_file = request.files.get('image') # Grabs the image if uploaded

    try:
        # Build the message format Groq needs
        content_payload = [{"type": "text", "text": user_message if user_message else "What is in this image?"}]
        
        if image_file and image_file.filename != '':
            base64_image = encode_image(image_file)
            content_payload.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image_file.content_type};base64,{base64_image}"
                }
            })

        # Ask the ultra-fast Llama 4 Vision model
        chat_completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": content_payload
                }
            ],
            max_tokens=1024
        )
        
        ai_response = chat_completion.choices[0].message.content
        return jsonify({"response": ai_response})

    except Exception as e:
        return jsonify({"response": f"System error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)