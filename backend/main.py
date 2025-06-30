import functions_framework
from google.cloud import storage
import datetime
import os
from flask import jsonify
import google.auth
from google.auth.transport import requests

# --- Configuration ---
# The GCS bucket name is now set via an environment variable.
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "default-bucket-name")
# ---------------------

def verify_album_exists(bucket_name: str, prefix: str):
    """
    Verifies if an album (GCS prefix) exists by checking for the presence
    of any objects under that prefix.
    """
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix=prefix, max_results=1)
        return any(True for _ in blobs)
    except Exception as e:
        print(f"Error verifying album existence for prefix '{prefix}': {e}")
        return False

def list_gcs_images(bucket_name: str, prefix: str):
    """
    Lists image filenames in a GCS bucket under a given prefix.
    """
    if not prefix.endswith('/'):
        prefix += '/'

    image_filenames = []
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix=prefix)

        for blob in blobs:
            if blob.name == prefix and blob.size == 0:
                continue
            
            if blob.name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                image_filenames.append(os.path.basename(blob.name))
        
        if not image_filenames:
            print(f"No image files found in GCS bucket '{bucket_name}' with prefix '{prefix}'.")

    except Exception as e:
        print(f"An unexpected error occurred when accessing GCS for prefix '{prefix}': {e}")
        return None, 500
    
    return image_filenames, 200 if image_filenames else 404

@functions_framework.http
def private_gallery_backend(request):
    """HTTP Cloud Function.
    Args:
        request (flask.Request): The request object.
    Returns:
        The response text, or any set of values that can be turned into a
        Response object using `make_response`.
    """
    # Set CORS headers for the preflight request
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    # Set CORS headers for the main request
    headers = {
        'Access-Control-Allow-Origin': '*'
    }

    if request.method != 'POST':
        return ('Method Not Allowed', 405, headers)

    request_json = request.get_json(silent=True)
    
    if not request_json or 'album_name' not in request_json:
        return (jsonify({"detail": "Album name is required."}), 400, headers)

    album_name = request_json['album_name']
    
    if not album_name:
        return (jsonify({"detail": "Album name cannot be empty."}), 400, headers)

    print(f"Verifying existence of album: '{album_name}'")

    if not GCS_BUCKET_NAME:
        print("Error: GCS_BUCKET_NAME environment variable not set.")
        return jsonify({"detail": "Server configuration error."}), 500, headers

    # Step 1: Verify the album exists. This is a quick check.
    if not verify_album_exists(bucket_name=GCS_BUCKET_NAME, prefix=album_name):
        return jsonify({"detail": "Gallery not found or album name incorrect."}), 404, headers

    # Step 2: If it exists, now get the list of images.
    image_filenames, status_code = list_gcs_images(
        bucket_name=GCS_BUCKET_NAME,
        prefix=album_name
    )

    if status_code == 500:
        return jsonify({"detail": "Error retrieving gallery images."}), 500, headers
    
    if status_code == 404: # Should be rare due to the check above, but handle it.
        return jsonify({"detail": "Gallery not found or is empty."}), 404, headers

    # Construct the public base URL for the images
    base_image_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{album_name}/"

    return jsonify({
        "base_url": base_image_url,
        "images": image_filenames
    }), 200, headers
