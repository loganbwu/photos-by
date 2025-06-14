// Global variables to store image data and container for access by resize handler
let allImageObjects = [];
let galleryNode = null;
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

document.addEventListener('DOMContentLoaded', function() {
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
    // Clear previous image objects if any (e.g. if script was re-run without page reload)
    allImageObjects = []; 

    imagesToProcess.forEach(imgElement => {
        const tempImg = new Image();
        tempImg.onload = () => {
            imagesLoadedCount++;
            allImageObjects.push({
                element: imgElement, // Keep original element to preserve attributes like onclick, alt, src
                aspectRatio: tempImg.naturalWidth / tempImg.naturalHeight,
                naturalWidth: tempImg.naturalWidth,
                naturalHeight: tempImg.naturalHeight
            });

            if (imagesLoadedCount === imagesToProcess.length) {
                renderGallery(); // Initial render
                // Setup debounced resize listener - add only once
                if (!window.galleryResizeListenerAttached) {
                    window.addEventListener('resize', debounce(renderGallery, 250));
                    window.galleryResizeListenerAttached = true; 
                }
            }
        };
        tempImg.onerror = () => {
            imagesLoadedCount++;
            console.warn(`Could not load image for dimension calculation: ${imgElement.src}`);
            // Add with default aspect ratio if load fails, to maintain structure
            allImageObjects.push({
                element: imgElement,
                aspectRatio: 1, 
                naturalWidth: 100, // Default dimensions for placeholder
                naturalHeight: 100
            });
            if (imagesLoadedCount === imagesToProcess.length) {
                renderGallery();
                if (!window.galleryResizeListenerAttached) {
                    window.addEventListener('resize', debounce(renderGallery, 250));
                    window.galleryResizeListenerAttached = true;
                }
            }
        };
        tempImg.src = imgElement.src; // This triggers the loading
    });
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
            itemContainer.className = 'grid__item-container js-grid-item-container'; 
            
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

            itemContainer.appendChild(newImgElement);
            rowElement.appendChild(itemContainer);
        });
        galleryNode.appendChild(rowElement);
    });

    // Re-initialize lazy loading if applicable
    // if (typeof window.reinitLazyLoad === 'function') {
    //     window.reinitLazyLoad();
    // }
}
