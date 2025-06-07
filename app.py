import os
import hashlib
import logging
import requests
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
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, mode=0o700)
            logger.info(f"Created directory: {dir_path}")

def get_session_file(username: str) -> str:
    hashed = hashlib.sha256(username.encode("utf-8")).hexdigest()
    return os.path.join(SESSIONS_DIR, f"{hashed}_session.json")

def get_client(username: str, password: str) -> Client:
    ensure_directories()
    session_file = get_session_file(username)
    cl = Client()

    if os.path.exists(session_file):
        try:
            cl.load_settings(session_file)
            logger.info(f"Loaded session for {username}")
        except Exception as e:
            logger.warning(f"Could not load session: {e}")

    try:
        cl.login(username, password)
        cl.dump_settings(session_file)
        logger.info(f"Logged in and saved session for {username}")
    except Exception as e:
        logger.error(f"Login failed: {e}")
        raise

    return cl

def download_image(image_url: str) -> str:
    try:
        response = requests.get(image_url, stream=True)
        if response.status_code != 200:
            raise Exception("Failed to download image")

        ext = image_url.split(".")[-1].split("?")[0]
        filename = f"{uuid4().hex}.{ext}"
        local_path = os.path.join(TEMP_DIR, filename)

        with open(local_path, "wb") as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)

        return local_path
    except Exception as e:
        raise Exception(f"Image download failed: {e}")

@app.route("/post-image", methods=["POST"])
@swag_from({
    'tags': ['Instagram'],
    'parameters': [
        {
            'name': 'body',
            'in': 'body',
            'required': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'username': {'type': 'string', 'example': 'your_instagram_username'},
                    'password': {'type': 'string', 'example': 'your_instagram_password'},
                    'image_url': {'type': 'string', 'example': 'https://example.com/image.jpg'},
                    'caption': {'type': 'string', 'example': 'This is a caption'}
                },
                'required': ['username', 'password', 'image_url']
            }
        }
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
            'description': 'Invalid input',
            'schema': {
                'type': 'object',
                'properties': {
                    'error': {'type': 'string'}
                }
            }
        },
        500: {
            'description': 'Internal server error',
            'schema': {
                'type': 'object',
                'properties': {
                    'error': {'type': 'string'}
                }
            }
        }
    }
})
def post_image():
    try:
        data = request.get_json(force=True)
        username = data.get("username")
        password = data.get("password")
        image_url = data.get("image_url")
        caption = data.get("caption", "")

        if not username or not password or not image_url:
            return jsonify({"error": "username, password, and image_url are required"}), 400

        image_path = download_image(image_url)
        cl = get_client(username, password)
        media = cl.photo_upload(image_path, caption)

        logger.info(f"Posted image by {username}, media ID: {media.pk}")

        os.remove(image_path)  # Clean up
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
    Health check endpoint
    ---
    responses:
      200:
        description: Service is healthy
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
