import os
import hashlib
import logging
from uuid import uuid4
from flask import Flask, request, jsonify
from instagrapi import Client
from flasgger import Swagger, swag_from

app = Flask(__name__)
swagger = Swagger(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("InstagramAPI")

SESSIONS_DIR = "sessions"
TEMP_DIR = "temp_images"

def ensure_directories():
    for dir_path in [SESSIONS_DIR, TEMP_DIR]:
        os.makedirs(dir_path, mode=0o700, exist_ok=True)
        logger.info(f"Ensured directory: {dir_path}")

def get_session_file(username: str) -> str:
    hashed = hashlib.sha256(username.encode("utf-8")).hexdigest()
    return os.path.join(SESSIONS_DIR, f"{hashed}_session.json")

def get_client(username: str, password: str) -> Client:
    session_file = get_session_file(username)
    cl = Client()

    if os.path.exists(session_file):
        try:
            cl.load_settings(session_file)
            cl.get_timeline_feed()  # test session validity
            logger.info(f"Loaded valid session for {username}")
            return cl
        except Exception as e:
            logger.warning(f"Session invalid or expired: {e}")

    # Fallback to login
    cl.login(username, password)
    cl.dump_settings(session_file)
    logger.info(f"Logged in and saved session for {username}")
    return cl

@app.route("/post-image", methods=["POST"])
@swag_from({
    'tags': ['Instagram'],
    'consumes': ['multipart/form-data'],
    'parameters': [
        {'name': 'username', 'in': 'formData', 'type': 'string', 'required': True},
        {'name': 'password', 'in': 'formData', 'type': 'string', 'required': True},
        {'name': 'caption', 'in': 'formData', 'type': 'string'},
        {'name': 'image', 'in': 'formData', 'type': 'file', 'required': True}
    ],
    'responses': {
        200: {
            'description': 'Image posted successfully',
            'schema': {
                'type': 'object',
                'properties': {
                    'status': {'type': 'string', 'example': 'success'},
                    'media_id': {'type': 'integer', 'example': 123456789},
                    'caption': {'type': 'string'}
                }
            }
        },
        400: {
            'description': 'Bad request',
            'schema': {'type': 'object', 'properties': {'error': {'type': 'string'}}}
        },
        500: {
            'description': 'Internal error',
            'schema': {'type': 'object', 'properties': {'error': {'type': 'string'}}}
        }
    }
})
def post_image():
    try:
        username = request.form.get("username")
        password = request.form.get("password")
        caption = request.form.get("caption", "")
        image = request.files.get("image")

        if not username or not password or not image:
            return jsonify({"error": "username, password, and image are required"}), 400

        ensure_directories()
        ext = os.path.splitext(image.filename)[1] or ".jpg"
        image_path = os.path.join(TEMP_DIR, f"{uuid4().hex}{ext}")
        image.save(image_path)

        cl = get_client(username, password)
        media = cl.photo_upload(image_path, caption)

        os.remove(image_path)

        return jsonify({
            "status": "success",
            "media_id": media.pk,
            "caption": caption
        })

    except Exception as e:
        logger.error(f"Error in post-image: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health_check():
    """
    Health check
    ---
    responses:
      200:
        description: OK
        schema:
          type: object
          properties:
            status:
              type: string
              example: ok
    """
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    ensure_directories()
    app.run(host="0.0.0.0", port=5000, debug=False)
