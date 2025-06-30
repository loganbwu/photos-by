// Global variables to store image data and container for access by resize handler
let allImageObjects = [];
let galleryNode = null;
let isPrivateGalleryView = false; // Flag to control private gallery features
const SMALL_SCREEN_BREAKPOINT = 768; // px, screens narrower than this will show 2 images per row

// Debounce function to limit how often renderGallery is called on resize
function debounce(func, wait, immediate) {
    let timeout;
    return function() {
        const context = this, args = arguments;
        const later = function() {
            timeout = null;
            if (!immediate) func.apply(context, args);
        };
        const callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
        if (callNow) func.apply(context, args);
    };
}

function processAndRenderGallery(isPrivate = false, manifest = null) {
    isPrivateGalleryView = isPrivate;
    galleryNode = document.getElementById('image-gallery-container');
    if (!galleryNode) {
        console.warn('Gallery container #image-gallery-container not found. Script will not run.');
        return;
    }

    const imagesToProcess = Array.from(galleryNode.querySelectorAll('img.gallery-image-source'));
    if (imagesToProcess.length === 0) {
        return;
    }

    // Clear the gallery container of the placeholder images
    galleryNode.innerHTML = '';

    allImageObjects = []; // Reset the global store
    let loadedImages = [];
    let imagesLoadedCount = 0;
    const screenWidth = window.innerWidth;
    const imagesPerRow = screenWidth < SMALL_SCREEN_BREAKPOINT ? 2 : 3;

    // Sort images based on manifest before loading
    if (manifest && Array.isArray(manifest)) {
        const manifestOrder = manifest.reduce((acc, name, index) => {
            acc[name] = index;
            return acc;
        }, {});
        imagesToProcess.sort((a, b) => {
            const aFilename = a.src.split('?')[0].split('/').pop();
            const bFilename = b.src.split('?')[0].split('/').pop();
            const aIndex = manifestOrder[aFilename];
            const bIndex = manifestOrder[bFilename];
            if (aIndex === undefined) return 1;
            if (bIndex === undefined) return -1;
            return aIndex - bIndex;
        });
    } else {
        imagesToProcess.sort((a, b) => {
            const aFilename = a.src.split('?')[0].split('/').pop();
            const bFilename = b.src.split('?')[0].split('/').pop();
            return aFilename.localeCompare(bFilename);
        });
    }

    imagesToProcess.forEach(imgElement => {
        const tempImg = new Image();
        tempImg.onload = () => {
            const imgData = {
                element: imgElement,
                aspectRatio: tempImg.naturalWidth / tempImg.naturalHeight,
                naturalWidth: tempImg.naturalWidth,
                naturalHeight: tempImg.naturalHeight,
                filename: imgElement.src.split('?')[0].split('/').pop()
            };
            
            // Add to the global list for potential full re-renders on resize
            const originalIndex = imagesToProcess.findIndex(el => el.src === imgElement.src);
            allImageObjects[originalIndex] = imgData;


            // Process for incremental rendering
            loadedImages.push(imgData);
            imagesLoadedCount++;

            if (loadedImages.length === imagesPerRow || imagesLoadedCount === imagesToProcess.length) {
                appendRowToGallery(loadedImages);
                loadedImages = []; // Reset for the next row
            }
        };
        tempImg.onerror = () => {
            console.warn(`Could not load image: ${imgElement.src}`);
            imagesLoadedCount++;
            // Potentially handle error, maybe append a placeholder
            if (loadedImages.length > 0 && imagesLoadedCount === imagesToProcess.length) {
                 appendRowToGallery(loadedImages);
                 loadedImages = [];
            }
        };
        tempImg.src = imgElement.src;
    });
}

function sortAndRender(manifest) {
    // This function is now primarily for the full-gallery resize event.
    // The initial sort happens in processAndRenderGallery.
    // We just need to ensure allImageObjects is sorted correctly before re-rendering.
    const sortedObjects = allImageObjects.filter(Boolean); // Filter out any empty slots if images failed to load

    if (manifest && Array.isArray(manifest) && manifest.length > 0) {
        const manifestOrder = manifest.reduce((acc, name, index) => {
            acc[name] = index;
            return acc;
        }, {});
        sortedObjects.sort((a, b) => {
            const aIndex = manifestOrder[a.filename];
            const bIndex = manifestOrder[b.filename];
            if (aIndex === undefined) return 1;
            if (bIndex === undefined) return -1;
            return aIndex - bIndex;
        });
    } else {
        sortedObjects.sort((a, b) => a.filename.localeCompare(b.filename));
    }
    allImageObjects = sortedObjects; // Update the global array with the sorted, filtered list
    renderGallery(); // Re-render the entire gallery
}

// Make the function globally available for albums.js
window.processAndRenderGallery = processAndRenderGallery;
window.renderGallery = renderGallery;

document.addEventListener('DOMContentLoaded', function() {
    // Initial call for public galleries, but not for the private gallery page
    if (!document.getElementById('album-access')) {
        processAndRenderGallery();
    }

    // Setup debounced resize listener - add only once
    if (!window.galleryResizeListenerAttached) {
        window.addEventListener('resize', debounce(renderGallery, 100));
        window.galleryResizeListenerAttached = true;
    }
});

function appendRowToGallery(rowImages) {
    if (!galleryNode || rowImages.length === 0) {
        return;
    }

    const rowElement = document.createElement('div');
    rowElement.className = 'grid__row';

    const rowAspectRatioSum = rowImages.reduce((sum, imgData) => {
        return sum + (typeof imgData.aspectRatio === 'number' && !isNaN(imgData.aspectRatio) ? imgData.aspectRatio : 1);
    }, 0);

    rowImages.forEach(imgData => {
        const itemContainer = document.createElement('div');
        itemContainer.className = 'grid__item-container js-grid-item-container image-container';

        const currentImageAspectRatio = typeof imgData.aspectRatio === 'number' && !isNaN(imgData.aspectRatio) ? imgData.aspectRatio : 1;
        const flexBasis = rowAspectRatioSum > 0 ? (currentImageAspectRatio / rowAspectRatioSum) * 100 : (100 / rowImages.length);
        itemContainer.style.flexBasis = `${flexBasis}%`;

        const newImgElement = document.createElement('img');
        newImgElement.src = imgData.element.src;
        newImgElement.alt = imgData.element.alt || '';
        newImgElement.className = 'grid__item-image js-grid__item-image grid__item-image-lazy js-lazy';
        newImgElement.classList.remove('gallery-image-source');

        newImgElement.style.aspectRatio = `${currentImageAspectRatio}`;
        newImgElement.style.height = '100%';
        newImgElement.style.objectFit = 'cover';

        const onclickAttribute = imgData.element.getAttribute('onclick');
        if (onclickAttribute) {
            newImgElement.setAttribute('onclick', onclickAttribute);
        }

        itemContainer.appendChild(newImgElement);

        if (isPrivateGalleryView) {
            const overlay = document.createElement('div');
            overlay.className = 'filename-overlay';
            overlay.textContent = imgData.filename;
            itemContainer.appendChild(overlay);
        }

        rowElement.appendChild(itemContainer);
    });

    galleryNode.appendChild(rowElement);

    // After adding a new row, re-initialize lightbox for the new images
    if (typeof window.initializeLightboxStateAndListeners === 'function') {
        window.initializeLightboxStateAndListeners();
    }
}


function renderGallery() {
    if (!galleryNode || allImageObjects.length === 0) {
        return;
    }
    
    // Filter out any potential undefined entries if images failed to load
    const validImages = allImageObjects.filter(Boolean);

    galleryNode.innerHTML = ''; // Clear the container for a full redraw

    const screenWidth = window.innerWidth;
    const imagesPerRow = screenWidth < SMALL_SCREEN_BREAKPOINT ? 2 : 3;

    const rows = [];
    for (let i = 0; i < validImages.length; i += imagesPerRow) {
        rows.push(validImages.slice(i, i + imagesPerRow));
    }

    rows.forEach(rowImages => {
        // We can reuse the appendRowToGallery logic for each row
        appendRowToGallery(rowImages);
    });
}
