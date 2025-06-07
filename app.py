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
        # Validate URL format
        if not image_url.startswith(('http://', 'https://')):
            raise ValueError("Invalid URL scheme - must be http:// or https://")

        # Ensure temp directory exists
        os.makedirs(TEMP_DIR, exist_ok=True)

        # Download the image
        response = requests.get(image_url, stream=True, timeout=10)
        response.raise_for_status()  # Raises HTTPError for bad responses

        # Extract and sanitize file extension
        parsed_url = urlparse(image_url)
        base_name = os.path.basename(parsed_url.path)
        ext = os.path.splitext(base_name)[1][1:]  # Get extension without dot
        
        # Validate extension
        if not ext or len(ext) > 5 or not ext.isalnum():
            ext = 'jpg'  # Default fallback

        # Generate safe filename
        filename = f"{uuid4().hex}.{ext.lower()}"
        local_path = os.path.join(TEMP_DIR, filename)

        # Save the image
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:  # Filter out keep-alive chunks
                    f.write(chunk)

        # Verify file was written
        if not os.path.exists(local_path):
            raise IOError("Failed to save downloaded image")

        return local_path

    except requests.exceptions.RequestException as e:
        raise Exception(f"Network error downloading image: {str(e)}")
    except IOError as e:
        raise Exception(f"Filesystem error saving image: {str(e)}")
    except Exception as e:
        raise Exception(f"Unexpected error downloading image: {str(e)}")

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
