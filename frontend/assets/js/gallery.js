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
    isPrivateGalleryView = isPrivate; // Set the flag for this gallery view
    galleryNode = document.getElementById('image-gallery-container');
    if (!galleryNode) {
        console.warn('Gallery container #image-gallery-container not found. Aspect ratio script will not run.');
        return;
    }

    const imagesToProcess = Array.from(galleryNode.querySelectorAll('img.gallery-image-source'));

    if (imagesToProcess.length === 0) {
        console.log('No source images found in #image-gallery-container for gallery processing.');
        return;
    }

    let imagesLoadedCount = 0;
    allImageObjects = []; // Clear previous image objects

    imagesToProcess.forEach(imgElement => {
        const tempImg = new Image();
        tempImg.onload = () => {
            imagesLoadedCount++;
            allImageObjects.push({
                element: imgElement,
                aspectRatio: tempImg.naturalWidth / tempImg.naturalHeight,
                naturalWidth: tempImg.naturalWidth,
                naturalHeight: tempImg.naturalHeight,
                filename: imgElement.src.split('?')[0].split('/').pop()
            });

            if (imagesLoadedCount === imagesToProcess.length) {
                sortAndRender(manifest);
            }
        };
        tempImg.onerror = () => {
            imagesLoadedCount++;
            console.warn(`Could not load image for dimension calculation: ${imgElement.src}`);
            allImageObjects.push({
                element: imgElement,
                aspectRatio: 1,
                naturalWidth: 100,
                naturalHeight: 100,
                filename: imgElement.src.split('?')[0].split('/').pop()
            });
            if (imagesLoadedCount === imagesToProcess.length) {
                sortAndRender(manifest);
            }
        };
        tempImg.src = imgElement.src;
    });
}

function sortAndRender(manifest) {
    // If a manifest is provided, use it to sort. Otherwise, sort alphabetically.
    if (manifest && Array.isArray(manifest) && manifest.length > 0) {
        console.log("Sorting images based on manifest.");
        const manifestOrder = manifest.reduce((acc, name, index) => {
            acc[name] = index;
            return acc;
        }, {});
        allImageObjects.sort((a, b) => {
            const aIndex = manifestOrder[a.filename];
            const bIndex = manifestOrder[b.filename];
            // If a file isn't in the manifest, push it to the end.
            if (aIndex === undefined) return 1;
            if (bIndex === undefined) return -1;
            return aIndex - bIndex;
        });
    } else {
        console.log("No manifest provided, sorting images alphabetically.");
        allImageObjects.sort((a, b) => a.filename.localeCompare(b.filename));
    }
    renderGallery();
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

function renderGallery() {
    if (!galleryNode || allImageObjects.length === 0) {
        // console.log('RenderGallery: galleryNode or allImageObjects not ready.');
        return;
    }

    galleryNode.innerHTML = ''; // Clear the container of the original unprocessed images or previous render

    const screenWidth = window.innerWidth;
    const imagesPerRow = screenWidth < SMALL_SCREEN_BREAKPOINT ? 2 : 3;

    const rows = [];
    for (let i = 0; i < allImageObjects.length; i += imagesPerRow) {
        rows.push(allImageObjects.slice(i, i + imagesPerRow));
    }

    rows.forEach(rowImages => {
        const rowElement = document.createElement('div');
        rowElement.className = 'grid__row';

        const rowAspectRatioSum = rowImages.reduce((sum, imgData) => {
            return sum + (typeof imgData.aspectRatio === 'number' && !isNaN(imgData.aspectRatio) ? imgData.aspectRatio : 1);
        }, 0);

        rowImages.forEach(imgData => {
            const itemContainer = document.createElement('div');
            itemContainer.className = 'grid__item-container js-grid-item-container image-container'; 
            
            const currentImageAspectRatio = typeof imgData.aspectRatio === 'number' && !isNaN(imgData.aspectRatio) ? imgData.aspectRatio : 1;
            // Ensure rowAspectRatioSum is not zero to prevent division by zero
            const flexBasis = rowAspectRatioSum > 0 ? (currentImageAspectRatio / rowAspectRatioSum) * 100 : (100 / rowImages.length);
            itemContainer.style.flexBasis = `${flexBasis}%`;

            const newImgElement = document.createElement('img');
            newImgElement.src = imgData.element.src;
            newImgElement.alt = imgData.element.alt || '';
            
            newImgElement.className = imgData.element.className.replace('gallery-image-source', '').trim() 
                                     || 'grid__item-image js-grid__item-image grid__item-image-lazy js-lazy';
            if (!newImgElement.classList.contains('grid__item-image')) {
                newImgElement.classList.add('grid__item-image');
            }
            // Ensure gallery-image-source is removed if it was there from original markup
            newImgElement.classList.remove('gallery-image-source');


            newImgElement.style.aspectRatio = `${currentImageAspectRatio}`;
            newImgElement.style.height = '100%';
            newImgElement.style.objectFit = 'cover';

            const onclickAttribute = imgData.element.getAttribute('onclick');
            if (onclickAttribute) {
                newImgElement.setAttribute('onclick', onclickAttribute);
            }

            // Prevent right-click context menu
            newImgElement.addEventListener('contextmenu', e => e.preventDefault());

            itemContainer.appendChild(newImgElement);

            // Conditionally add the overlay for private galleries
            if (isPrivateGalleryView) {
                const overlay = document.createElement('div');
                overlay.className = 'filename-label filename-overlay';
                overlay.textContent = imgData.filename;
                itemContainer.appendChild(overlay);
            }
            
            rowElement.appendChild(itemContainer);
        });
        galleryNode.appendChild(rowElement);
    });

    // Re-initialize lightbox state and listeners after gallery is rendered
    if (typeof window.initializeLightboxStateAndListeners === 'function') {
        window.initializeLightboxStateAndListeners(isPrivateGalleryView);
    }

    // Re-initialize lazy loading if applicable
    // if (typeof window.reinitLazyLoad === 'function') {
    //     window.reinitLazyLoad();
    // }
}
