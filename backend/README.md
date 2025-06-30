# Private Gallery Backend (Rye Managed)

This directory contains the FastAPI backend application for the private gallery feature, managed by [Rye](https://rye-up.com/). This version integrates directly with Google Cloud Storage (GCS), using GCS folder names (prefixes) as client passwords.

## Overview

The backend is responsible for:
1.  **Password/Prefix Verification:** The "password" submitted by the client is treated as a GCS folder name (prefix).
2.  **Secure Image Access:** Listing images within the specified GCS folder/prefix and generating secure, temporary (signed) URLs for them.

The frontend (GitHub Pages site) makes requests to this backend.

## Setup and Running Locally (with Rye)

1.  **Prerequisites:**
    *   **Rye installed:** [https://rye-up.com/guide/installation/](https://rye-up.com/guide/installation/)
    *   **Google Cloud SDK installed and configured:** Required for `gsutil` and Application Default Credentials (ADC).
        *   Install: [https://cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install)
        *   Initialize: `gcloud init`
        *   Authenticate for ADC: `gcloud auth application-default login`

2.  **Configure Scripts:**
    *   Ensure your `GCS_BUCKET_NAME` is set correctly in both `scripts/sync_gcs.py` and `backend/main.py`.

3.  **Install Dependencies:**
    *   Navigate to the `backend` directory and run `rye sync`. This command creates the virtual environment and installs all dependencies.
    ```bash
    cd backend
    rye sync
    ```

4.  **Prepare & Sync Local Photos:**
    *   Create and populate the `gcs_local_staging/` directory.
    *   From the `backend` directory, run the sync script:
    ```bash
    rye run sync-gcs
    ```

5.  **Run the Backend Development Server:**
    *   From the `backend` directory, run the `start` script:
    ```bash
    rye run start
    ```
    *   The application will be accessible at `http://localhost:8001`.

## Publishing a New Private Gallery

The "password" for a private gallery is simply the name of a folder in your GCS bucket. The `sync_gcs.py` script is used to upload photos from your local machine to GCS.

1.  **Create a Client Folder:**
    *   Inside the `backend/gcs_local_staging/` directory, create a new folder.
    *   The name you give this folder will be the password for the private gallery (e.g., `client-jane-doe`).

2.  **Add Photos:**
    *   Copy the client's photos into the new folder you just created.

3.  **Run the Sync Script:**
    *   From the `backend` directory, run the `sync-gcs` command:
    ```bash
    rye run sync-gcs
    ```
    *   This script will upload the new folder and its contents to your GCS bucket.

4.  **Access the Gallery:**
    *   The gallery will now be accessible on your website using the folder name as the password.

## Deployment to Google Cloud Functions (2nd Gen)

This backend is deployed to Google Cloud Functions (2nd Gen). The authentication method uses the function's runtime service account, which is the recommended and most secure method.

### 1. Deploy the Function

The deployment process is managed by the `deploy.sh` script.

Run the `deploy` script from within the `backend` directory:
```bash
cd backend
rye run deploy
```
The script will:
1.  Ensure the virtual environment is correctly built with `rye sync`.
2.  Generate the `requirements.txt` file.
3.  Deploy the function to Google Cloud.

**Note:** All deployment configuration is contained within `backend/deploy.sh`.

### 2. Configure the Frontend
After the deployment command finishes, it will output a **Trigger URL**. This is the public URL for your new backend service.

1.  Copy this URL.
2.  Open `assets/js/private-gallery.js`.
3.  Update the `backendUrl` variable with your new URL:
    ```javascript
    const backendUrl = 'YOUR_NEW_CLOUD_FUNCTION_URL';
    ```
4.  Run the build script to apply the change:
    ```bash
    node scripts/build.js
    ```
5.  Commit and push your changes to GitHub to update the live site.

## Security Notes
*   **CORS:** Remember to update the `origins` list in `backend/main.py` to your specific frontend domain(s) for production to enhance security.
*   **IAM Permissions:** The service account used by the function needs the following roles:
    *   **`Storage Object Viewer`**: To list and read files from the GCS bucket.
    *   **`Service Account Token Creator`**: To create signed URLs.
*   **Service Account Key:** No service account key file is needed for this authentication method.
