import os
import hashlib
import logging
from flask import Flask, request, jsonify
from instagrapi import Client

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("InstagramAPI")

SESSIONS_DIR = "sessions"

def ensure_session_dir():
    if not os.path.exists(SESSIONS_DIR):
        os.makedirs(SESSIONS_DIR, mode=0o700)  # Secure permissions
        logger.info(f"Created session directory: {SESSIONS_DIR}")

def get_session_file(username: str) -> str:
    # Hash username for filename safety & privacy
    hashed = hashlib.sha256(username.encode("utf-8")).hexdigest()
    return os.path.join(SESSIONS_DIR, f"{hashed}_session.json")

def get_client(username: str, password: str) -> Client:
    ensure_session_dir()
    session_file = get_session_file(username)
    cl = Client()

    if os.path.exists(session_file):
        try:
            cl.load_settings(session_file)
            logger.info(f"Loaded Instagram session for user {username}")
        except Exception as e:
            logger.warning(f"Failed loading session for {username}: {e}")

    try:
        cl.login(username, password)
        cl.dump_settings(session_file)
        logger.info(f"Logged in and saved session for {username}")
    except Exception as e:
        logger.error(f"Login failed for {username}: {e}")
        raise

    return cl

@app.route("/post-image", methods=["POST"])
def post_image():
    try:
        data = request.get_json(force=True)
        username = data.get("username")
        password = data.get("password")
        image_path = data.get("image_path")
        caption = data.get("caption", "")

        if not username or not password or not image_path:
            return jsonify({"error": "username, password, and image_path are required"}), 400

        if not os.path.isfile(image_path):
            return jsonify({"error": f"Image file not found: {image_path}"}), 400

        cl = get_client(username, password)
        media = cl.photo_upload(image_path, caption)

        logger.info(f"User {username} posted image: {media.pk}")
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
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    ensure_session_dir()
    # Production use: disable debug, consider using gunicorn or uWSGI behind nginx
    app.run(host="0.0.0.0", port=5000, debug=False)
