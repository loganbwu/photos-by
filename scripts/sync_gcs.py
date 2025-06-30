import os
import sys
import json
from google.cloud import storage
from PIL import Image
from io import BytesIO
import datetime

# --- Configuration ---
GCS_BUCKET_NAME = "photos-by-logan-content"
LOCAL_STAGING_DIR = "backend/gcs_local_staging"
# ---------------------

def get_exif_date(image_bytes):
    """Extracts the creation date from image EXIF data."""
    try:
        img = Image.open(BytesIO(image_bytes))
        exif_data = img._getexif()
        if exif_data and 36867 in exif_data:
            # EXIF tag 36867 is DateTimeOriginal
            date_str = exif_data[36867]
            return datetime.datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
    except Exception as e:
        print(f"Could not read EXIF data: {e}")
    return None

def sync_client_folder_to_gcs(client_folder_name):
    """
    Synchronizes a single client's local folder to GCS and generates a manifest
    sorted by EXIF date, falling back to local file modification time.
    """
    local_path = os.path.join(LOCAL_STAGING_DIR, client_folder_name)
    gcs_prefix = f"{client_folder_name}/"

    if not os.path.isdir(local_path):
        print(f"Skipping '{client_folder_name}': Local path '{local_path}' is not a directory.")
        return False

    print(f"\nSynchronizing local folder '{local_path}' to GCS prefix '{gcs_prefix}'...")

    try:
        # Explicitly use the service account key for authentication
        sa_key_path = os.path.join(os.path.dirname(__file__), '..', 'backend', 'gcp-sa-key.json')
        if not os.path.exists(sa_key_path):
            print(f"ERROR: Service account key not found at '{sa_key_path}'")
            print("Please follow the setup instructions to create the key file.")
            return False
            
        storage_client = storage.Client.from_service_account_json(sa_key_path)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)

        # 1. Collect image information from local files first.
        image_info = []
        local_files = [
            f for f in os.listdir(local_path) 
            if os.path.isfile(os.path.join(local_path, f)) and f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
        ]

        if not local_files:
            print(f"No images found in '{local_path}'. Skipping manifest generation.")
            return True

        print(f"Found {len(local_files)} images. Reading metadata...")
        for filename in local_files:
            local_item_path = os.path.join(local_path, filename)
            with open(local_item_path, 'rb') as f:
                image_bytes = f.read()
            
            exif_date = get_exif_date(image_bytes)
            # Fallback to local file modification time if EXIF fails
            mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(local_item_path))
            
            image_info.append({
                "name": filename,
                "local_path": local_item_path,
                "timestamp": exif_date or mod_time
            })

        # 2. Sort images by the collected timestamp.
        image_info.sort(key=lambda x: x["timestamp"])
        
        # 3. Upload sorted files to GCS.
        print(f"Uploading {len(image_info)} images in sorted order...")
        for img_data in image_info:
            blob = bucket.blob(f"{gcs_prefix}{img_data['name']}")
            blob.upload_from_filename(img_data['local_path'])
            blob.make_public()
            print(f"Uploaded '{img_data['name']}'.")

        # 4. Generate and upload the manifest from the sorted list.
        print(f"Generating manifest for '{client_folder_name}'...")
        sorted_filenames = [img["name"] for img in image_info]
        
        manifest_blob = bucket.blob(f"{gcs_prefix}manifest.json")
        manifest_blob.upload_from_string(
            json.dumps(sorted_filenames, indent=2),
            content_type='application/json'
        )
        manifest_blob.make_public()
        print(f"Successfully generated and uploaded manifest for '{client_folder_name}'.")
        
        print(f"Successfully synchronized '{client_folder_name}'.")
        return True

    except Exception as e:
        print(f"An unexpected error occurred during sync for '{client_folder_name}': {e}")
        return False

def main():
    """Main function to iterate through client folders and sync them."""
    print("Starting GCS synchronization process...")
    print(f"Local staging directory: '{os.path.abspath(LOCAL_STAGING_DIR)}'")
    print(f"Target GCS Bucket: 'gs://{GCS_BUCKET_NAME}/'")
    print("-" * 30)

    if GCS_BUCKET_NAME == "YOUR_GCS_BUCKET_NAME_HERE":
        print("ERROR: Please update GCS_BUCKET_NAME in this script with your actual GCS bucket name.")
        sys.exit(1)

    if not os.path.isdir(LOCAL_STAGING_DIR):
        print(f"ERROR: Local staging directory '{LOCAL_STAGING_DIR}' not found.")
        sys.exit(1)

    client_folders = [
        d for d in os.listdir(LOCAL_STAGING_DIR)
        if os.path.isdir(os.path.join(LOCAL_STAGING_DIR, d))
    ]

    if not client_folders:
        print(f"No client folders found in '{LOCAL_STAGING_DIR}'. Nothing to sync.")
        sys.exit(0)

    print(f"Found client folders to sync: {', '.join(client_folders)}")

    successful_syncs = 0
    failed_syncs = 0

    for folder_name in client_folders:
        if sync_client_folder_to_gcs(folder_name):
            successful_syncs += 1
        else:
            failed_syncs += 1
    
    print("-" * 30)
    print("Synchronization summary:")
    print(f"Successfully synced folders: {successful_syncs}")
    print(f"Failed to sync folders: {failed_syncs}")

    if failed_syncs > 0:
        print("\nSome synchronizations failed. Please review the logs above.")
        sys.exit(1)
    else:
        print("\nAll synchronizations completed successfully.")
        sys.exit(0)

if __name__ == "__main__":
    main()
