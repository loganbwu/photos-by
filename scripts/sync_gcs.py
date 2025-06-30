import os
import subprocess
import sys

# --- Configuration ---
# !!! IMPORTANT: Replace with your actual GCS bucket name !!!
GCS_BUCKET_NAME = "photos-by-logan-content"
# Local directory containing client folders (named by password)
LOCAL_STAGING_DIR = "backend/gcs_local_staging"
# ---------------------

def check_gsutil_installed():
    """Checks if gsutil is installed and in PATH."""
    try:
        subprocess.run(["gsutil", "--version"], capture_output=True, check=True, text=True)
        return True
    except FileNotFoundError:
        print("ERROR: gsutil command not found. Please ensure the Google Cloud SDK is installed and configured correctly.")
        print("Installation guide: https://cloud.google.com/sdk/docs/install")
        return False
    except subprocess.CalledProcessError as e:
        print(f"ERROR: gsutil found but returned an error: {e.stderr}")
        return False

def sync_client_folder_to_gcs(client_folder_name):
    """
    Synchronizes a single client's local folder to GCS using gsutil rsync.
    The client_folder_name is also the GCS prefix (folder).
    """
    local_path = os.path.join(LOCAL_STAGING_DIR, client_folder_name)
    gcs_path = f"gs://{GCS_BUCKET_NAME}/{client_folder_name}/"

    if not os.path.isdir(local_path):
        print(f"Skipping '{client_folder_name}': Local path '{local_path}' is not a directory.")
        return False

    print(f"\nSynchronizing local folder '{local_path}' to GCS path '{gcs_path}'...")

    # gsutil rsync command:
    # -d: delete extra files at destination
    # -r: recursive
    # -c: checksum check (slower but more reliable for changes) - optional, consider for your needs
    # -m: run in parallel (for many files) - optional
    # Add -C to continue on error for individual files if preferred
    command = [
        "gsutil",
        "-m",
        "rsync",
        "-d",
        "-r",
        "-a", "public-read",
        local_path,
        gcs_path,
    ]

    try:
        # It's good practice to ensure the user is aware of potential deletions.
        print(f"This will synchronize '{local_path}' with '{gcs_path}'.")
        print("Files present locally but not in GCS will be uploaded.")
        print("Files present in GCS under this path but not locally WILL BE DELETED from GCS.")
        
        # Optional: Add a confirmation prompt
        # confirm = input("Proceed with sync? (yes/no): ").lower()
        # if confirm != 'yes':
        #     print("Sync aborted by user.")
        #     return False

        process = subprocess.run(command, capture_output=True, text=True, check=False) # check=False to handle errors manually

        if process.returncode == 0:
            print(f"Successfully synchronized '{client_folder_name}'.")
            if process.stdout:
                print("gsutil output:\n", process.stdout)
            return True
        else:
            print(f"ERROR: gsutil rsync failed for '{client_folder_name}' with exit code {process.returncode}.")
            if process.stdout:
                print("gsutil stdout:\n", process.stdout)
            if process.stderr:
                print("gsutil stderr:\n", process.stderr)
            return False
    except FileNotFoundError:
        print("ERROR: gsutil command not found during rsync. This check should have been caught earlier.")
        return False
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

    if not check_gsutil_installed():
        sys.exit(1)

    if not os.path.isdir(LOCAL_STAGING_DIR):
        print(f"ERROR: Local staging directory '{LOCAL_STAGING_DIR}' not found.")
        print(f"Please create it and add client subfolders (e.g., '{LOCAL_STAGING_DIR}/client_password_1/').")
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
