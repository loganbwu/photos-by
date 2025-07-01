import os
import sys
import json
from google.cloud import storage
from PIL import Image
from io import BytesIO
import datetime
from tqdm import tqdm

# --- Configuration ---
GCS_BUCKET_NAME = "photos-by-logan-content"
# Construct the absolute path to the staging directory relative to the script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_STAGING_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "backend", "gcs_local_staging"))
# ---------------------

def get_exif_date(image_bytes):
    """
    Extracts the creation date from image EXIF data by checking multiple tags.
    It checks for DateTimeOriginal, DateTimeDigitized, and DateTime tags in that order.
    """
    try:
        img = Image.open(BytesIO(image_bytes))
        exif_data = img._getexif()
        if exif_data:
            # EXIF tags for date/time, in order of preference.
            # 36867: DateTimeOriginal, 36868: DateTimeDigitized, 306: DateTime
            for tag in [36867, 36868, 306]:
                if tag in exif_data:
                    date_str = exif_data[tag]
                    if date_str and isinstance(date_str, str):
                        date_str = date_str.strip().replace('\x00', '')
                        if date_str:
                            return datetime.datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
    except Exception:
        # Suppressing EXIF read errors for a cleaner progress bar experience
        pass
    return None

def main():
    """Main function to discover all images, process them with a global progress bar, and sync."""
    print("Starting GCS synchronization process...")
    print(f"Local staging directory: '{os.path.abspath(LOCAL_STAGING_DIR)}'")
    print(f"Target GCS Bucket: 'gs://{GCS_BUCKET_NAME}/'")
    print("-" * 30)

    if GCS_BUCKET_NAME == "YOUR_GCS_BUCKET_NAME_HERE":
        print("ERROR: Please update GCS_BUCKET_NAME in this script.", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(LOCAL_STAGING_DIR):
        print(f"ERROR: Local staging directory '{LOCAL_STAGING_DIR}' not found.", file=sys.stderr)
        sys.exit(1)

    # --- 1. Discover all image files across all client folders ---
    all_files_to_process = []
    client_folders = [d for d in os.listdir(LOCAL_STAGING_DIR) if os.path.isdir(os.path.join(LOCAL_STAGING_DIR, d))]
    client_folders.sort()  # Sort folders alphabetically

    if not client_folders:
        print("No client folders found. Nothing to sync.")
        sys.exit(0)

    print(f"Found client folders: {', '.join(client_folders)}")
    for folder_name in client_folders:
        local_path = os.path.join(LOCAL_STAGING_DIR, folder_name)
        image_files = [f for f in os.listdir(local_path) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))]
        for filename in image_files:
            all_files_to_process.append({
                "folder": folder_name,
                "name": filename,
                "local_path": os.path.join(local_path, filename)
            })

    if not all_files_to_process:
        print("No image files found in any client folder. Nothing to sync.")
        sys.exit(0)

    # --- 2. Read metadata for all files with a global progress bar ---
    images_by_folder = {folder: [] for folder in client_folders}
    print(f"\nReading metadata for {len(all_files_to_process)} images...")
    with tqdm(total=len(all_files_to_process), desc="Reading metadata", unit="file") as pbar:
        for file_info in all_files_to_process:
            with open(file_info["local_path"], 'rb') as f:
                image_bytes = f.read()
            
            exif_date = get_exif_date(image_bytes)
            mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_info["local_path"]))
            
            file_info["timestamp"] = exif_date or mod_time
            images_by_folder[file_info["folder"]].append(file_info)
            pbar.update(1)

    # --- 3. Sort images within each folder and prepare for upload ---
    for folder in images_by_folder:
        images_by_folder[folder].sort(key=lambda x: x["timestamp"])

    # --- 4. Upload all files with a global progress bar and generate manifests ---
    try:
        sa_key_path = os.path.join(SCRIPT_DIR, '..', 'backend', 'gcp-sa-key.json')
        if not os.path.exists(sa_key_path):
            print(f"ERROR: Service account key not found at '{sa_key_path}'", file=sys.stderr)
            sys.exit(1)
            
        storage_client = storage.Client.from_service_account_json(sa_key_path)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)

        print(f"\nUploading {len(all_files_to_process)} images to GCS...")
        with tqdm(total=len(all_files_to_process), desc="Uploading to GCS", unit="file") as pbar:
            for folder_name in client_folders:  # Iterate using the sorted list
                image_list = images_by_folder[folder_name]
                if not image_list:
                    continue

                gcs_prefix = f"{folder_name}/"
                for img_data in image_list:
                    blob = bucket.blob(f"{gcs_prefix}{img_data['name']}")
                    blob.upload_from_filename(img_data['local_path'])
                    blob.make_public()
                    pbar.update(1)
                
                # Generate and upload manifest for the folder
                sorted_filenames = [img["name"] for img in image_list]
                manifest_blob = bucket.blob(f"{gcs_prefix}manifest.json")
                manifest_blob.upload_from_string(
                    json.dumps(sorted_filenames, indent=2),
                    content_type='application/json'
                )
                manifest_blob.make_public()
        
        print("\nAll synchronizations completed successfully.")
        sys.exit(0)

    except Exception as e:
        print(f"\nAn unexpected error occurred during GCS upload: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
