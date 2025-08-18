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
    It also attempts to get sub-second precision.
    """
    try:
        img = Image.open(BytesIO(image_bytes))
        exif_data = img._getexif()
        if exif_data:
            # EXIF tags for date/time, in order of preference.
            # 36867: DateTimeOriginal, 37521: SubSecTimeOriginal
            # 36868: DateTimeDigitized, 37522: SubSecTimeDigitized
            # 306: DateTime
            date_str = None
            sub_sec_str = None

            if 36867 in exif_data:
                date_str = exif_data[36867]
                if 37521 in exif_data:
                    sub_sec_str = exif_data[37521]
            elif 36868 in exif_data:
                date_str = exif_data[36868]
                if 37522 in exif_data:
                    sub_sec_str = exif_data[37522]
            elif 306 in exif_data:
                date_str = exif_data[306]

            if date_str and isinstance(date_str, str):
                date_str = date_str.strip().replace('\x00', '')
                if date_str:
                    full_date_str = date_str
                    if sub_sec_str and isinstance(sub_sec_str, str):
                        # Ensure sub_sec_str is not empty and contains only digits
                        sub_sec_str = sub_sec_str.strip().replace('\x00', '')
                        if sub_sec_str.isdigit():
                            full_date_str += '.' + sub_sec_str
                    
                    # Try parsing with and without fractional seconds
                    for fmt in ('%Y:%m:%d %H:%M:%S.%f', '%Y:%m:%d %H:%M:%S'):
                        try:
                            return datetime.datetime.strptime(full_date_str, fmt)
                        except ValueError:
                            continue
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

    # --- Check for case-insensitive folder name clashes ---
    print("Checking for folder name clashes (case-insensitive)...")
    seen_folders = {}
    for folder in client_folders:
        lower_folder = folder.lower()
        if lower_folder in seen_folders:
            print(f"ERROR: Clash detected. Folders '{seen_folders[lower_folder]}' and '{folder}' are the same when case is ignored.", file=sys.stderr)
            print("Please rename one of the folders and try again.", file=sys.stderr)
            sys.exit(1)
        seen_folders[lower_folder] = folder
    print("No clashes found.")
    # ----------------------------------------------------

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
        images_by_folder[folder].sort(key=lambda x: (x["timestamp"], x["name"]))

    # --- 4. Upload all files with a global progress bar and generate manifests ---
    try:
        sa_key_path = os.path.join(SCRIPT_DIR, '..', 'backend', 'gcp-sa-key.json')
        if not os.path.exists(sa_key_path):
            print(f"ERROR: Service account key not found at '{sa_key_path}'", file=sys.stderr)
            sys.exit(1)
            
        storage_client = storage.Client.from_service_account_json(sa_key_path)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)

        # --- 4. Delete old folders/files from GCS ---
        print("\nChecking GCS for old folders and files to delete...")
        gcs_blobs = list(bucket.list_blobs())
        gcs_folders = set()
        gcs_files = set()

        for blob in gcs_blobs:
            parts = blob.name.split('/')
            if len(parts) > 1:
                gcs_folders.add(parts[0])
                gcs_files.add(blob.name)

        local_client_folders_set_lower = {f.lower() for f in client_folders}
        local_gcs_paths_set = set()
        for file_info in all_files_to_process:
            # Use lowercase folder name for the GCS path
            local_gcs_paths_set.add(f"{file_info['folder'].lower()}/{file_info['name']}")
        
        # Add manifests to local_gcs_paths_set for existing local folders
        for folder_name in local_client_folders_set_lower:
            local_gcs_paths_set.add(f"{folder_name}/manifest.json")

        # Identify folders to delete
        folders_to_delete = gcs_folders - local_client_folders_set_lower
        if folders_to_delete:
            print(f"Found GCS folders to delete: {', '.join(folders_to_delete)}")
            with tqdm(total=len(folders_to_delete), desc="Deleting GCS folders", unit="folder") as pbar:
                for folder_to_del in folders_to_delete:
                    # List blobs with prefix and delete them
                    blobs_to_delete_in_folder = list(bucket.list_blobs(prefix=f"{folder_to_del}/"))
                    if blobs_to_delete_in_folder:
                        bucket.delete_blobs(blobs_to_delete_in_folder)
                    pbar.update(1)
        else:
            print("No old GCS folders to delete.")

        # Identify individual files to delete within existing folders
        files_to_delete = gcs_files - local_gcs_paths_set
        # Filter out files that are part of folders already marked for deletion
        files_to_delete_filtered = [
            f for f in files_to_delete if f.split('/')[0] not in folders_to_delete
        ]

        if files_to_delete_filtered:
            print(f"Found GCS files to delete: {', '.join(files_to_delete_filtered)}")
            with tqdm(total=len(files_to_delete_filtered), desc="Deleting GCS files", unit="file") as pbar:
                for file_to_del in files_to_delete_filtered:
                    blob = bucket.blob(file_to_del)
                    blob.delete()
                    pbar.update(1)
        else:
            print("No old GCS files to delete.")

        # --- 5. Upload all files with a global progress bar and generate manifests ---
        print(f"\nUploading {len(all_files_to_process)} images to GCS...")
        with tqdm(total=len(all_files_to_process), desc="Uploading to GCS", unit="file") as pbar:
            for folder_name in client_folders:  # Iterate using the sorted list
                image_list = images_by_folder[folder_name]
                if not image_list:
                    # If a folder exists locally but has no images, ensure its manifest is still created/updated
                    # This handles cases where a folder might temporarily be empty of images but still exists
                    manifest_blob = bucket.blob(f"{folder_name.lower()}/manifest.json")
                    manifest_blob.upload_from_string(
                        json.dumps([], indent=2), # Empty manifest for empty folder
                        content_type='application/json'
                    )
                    manifest_blob.make_public()
                    continue

                # Use the lowercase folder name for the GCS prefix
                gcs_prefix = f"{folder_name.lower()}/"
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
        print(f"\nAn unexpected error occurred during GCS synchronization: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
