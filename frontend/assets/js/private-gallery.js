document.addEventListener('DOMContentLoaded', () => {
    const albumNameForm = document.getElementById('album-name-form');
    const albumNameInput = document.getElementById('album-name-input');
    const submitButton = document.getElementById('submit-album-name-button');
    const errorMessageElement = document.getElementById('error-message');
    const albumAccessSection = document.getElementById('album-access');
    const galleryContainer = document.getElementById('image-gallery-container');

    // --- Configuration ---
    // Replace this with your actual backend endpoint URL
    const backendUrl = 'https://australia-southeast1-photos-by-463514.cloudfunctions.net/private-gallery-backend'; 
    // Example: const backendUrl = 'https://your-service-name-abcdef.a.run.app/check-album';

    if (!albumNameForm || !albumNameInput || !submitButton || !errorMessageElement || !albumAccessSection || !galleryContainer) {
        console.error('Private gallery elements not found. Script will not run.');
        return;
    }

    albumNameForm.addEventListener('submit', async (event) => { // Changed to form submit
        event.preventDefault(); // Prevent default form submission
        const albumName = albumNameInput.value;
        if (!albumName) {
            displayError('Please enter an album name.');
            return;
        }

        hideError();
        submitButton.disabled = true;
        submitButton.textContent = 'Verifying...';

        try {
            const response = await fetch(backendUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ album_name: albumName }),
            });

            if (response.ok) {
                const data = await response.json();
                if (data.base_url && data.images && data.images.length > 0) {
                    albumAccessSection.style.display = 'none';
                    galleryContainer.style.display = ''; // Show gallery container
                    // Pass the manifest to the gallery population function
                    populateGallery(data.base_url, data.images, data.manifest);
                } else {
                    displayError('No images found for the provided album name, or the gallery is empty.');
                }
            } else {
                const errorData = await response.json().catch(() => null); // Try to parse error, but don't fail if no JSON body
                displayError(errorData?.detail || `Error: ${response.status} - ${response.statusText}`);
            }
        } catch (error) {
            console.error('Error submitting album name:', error);
            displayError('An error occurred. Please try again.');
        } finally {
            submitButton.disabled = false;
            submitButton.textContent = 'View Gallery';
        }
    });

    function populateGallery(baseUrl, images, manifest = null) {
        if (!galleryContainer) return;
        galleryContainer.innerHTML = ''; // Clear any existing content

        if (!images || images.length === 0) {
            displayError("No images to display.");
            return;
        }

        // If a manifest is provided, sort the images array before rendering
        if (manifest && Array.isArray(manifest) && manifest.length > 0) {
            console.log("Manifest found, sorting images before initial render.");
            const manifestOrder = manifest.reduce((acc, name, index) => {
                acc[name] = index;
                return acc;
            }, {});

            images.sort((a, b) => {
                const aIndex = manifestOrder[a];
                const bIndex = manifestOrder[b];
                // If a file isn't in the manifest, push it to the end.
                if (aIndex === undefined) return 1;
                if (bIndex === undefined) return -1;
                return aIndex - bIndex;
            });
        }

        images.forEach(imageName => {
            const imgElement = document.createElement('img');
            imgElement.className = 'gallery-image-source grid__item-image-lazy js-lazy';
            imgElement.src = `${baseUrl}${imageName}`;
            imgElement.alt = imageName; // Use filename as alt text
            galleryContainer.appendChild(imgElement);
        });

        // Now that the images are in the DOM, call the global function from gallery.js
        // to process them into the grid layout, passing the manifest.
        if (typeof window.processAndRenderGallery === 'function') {
            window.processAndRenderGallery(true, manifest); // Pass true for private galleries and the manifest
        } else {
            console.error('processAndRenderGallery function not found. The main gallery script may have failed to load.');
            displayError('Error displaying gallery. Please refresh and try again.');
        }
    }

    function displayError(message) {
        if (!errorMessageElement) return;
        errorMessageElement.textContent = message;
        errorMessageElement.style.display = 'block';
    }

    function hideError() {
        if (!errorMessageElement) return;
        errorMessageElement.style.display = 'none';
    }
});
