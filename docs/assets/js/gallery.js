document.addEventListener('DOMContentLoaded', function() {
    const galleryContainer = document.getElementById('image-gallery-container');
    if (!galleryContainer) {
        console.warn('Gallery container #image-gallery-container not found. Aspect ratio script will not run.');
        return;
    }

    // Find images that are direct children or have a specific class indicating they are sources
    const imagesToProcess = Array.from(galleryContainer.querySelectorAll('img.gallery-image-source'));

    if (imagesToProcess.length === 0) {
        console.log('No source images found in #image-gallery-container for gallery processing.');
        return;
    }

    let imagesLoadedCount = 0;
    const imageObjects = []; // To store data about each image (src, alt, dimensions, original element)

    imagesToProcess.forEach(imgElement => {
        // Create a temporary Image object to get natural dimensions without affecting the DOM yet
        const tempImg = new Image();
        tempImg.onload = () => {
            imagesLoadedCount++;
            imageObjects.push({
                element: imgElement, // Keep original element to preserve attributes like onclick, alt, src
                aspectRatio: tempImg.naturalWidth / tempImg.naturalHeight,
                naturalWidth: tempImg.naturalWidth,
                naturalHeight: tempImg.naturalHeight
            });

            if (imagesLoadedCount === imagesToProcess.length) {
                renderGallery(imageObjects, galleryContainer);
            }
        };
        tempImg.onerror = () => {
            imagesLoadedCount++;
            console.warn(`Could not load image for dimension calculation: ${imgElement.src}`);
            // Optionally, add a placeholder or skip this image
            if (imagesLoadedCount === imagesToProcess.length) {
                renderGallery(imageObjects, galleryContainer); // Process with what successfully loaded
            }
        };
        tempImg.src = imgElement.src; // This triggers the loading
    });
});

function renderGallery(imageObjects, galleryContainer) {
    // Clear the container of the original unprocessed images
    galleryContainer.innerHTML = ''; 

    const rows = [];
    const imagesPerRow = 3; // As per "Maximum of 3 images per row"
    for (let i = 0; i < imageObjects.length; i += imagesPerRow) {
        rows.push(imageObjects.slice(i, i + imagesPerRow));
    }

    rows.forEach(rowImages => {
        const rowElement = document.createElement('div');
        rowElement.className = 'grid__row';

        // Calculate sum of aspect ratios for the current row
        const rowAspectRatioSum = rowImages.reduce((sum, imgData) => {
            // Ensure aspectRatio is a valid number, default to 1 if not (e.g., for failed loads)
            return sum + (typeof imgData.aspectRatio === 'number' && !isNaN(imgData.aspectRatio) ? imgData.aspectRatio : 1);
        }, 0);

        rowImages.forEach(imgData => {
            const itemContainer = document.createElement('div');
            // Keep original classes if they were on a container, or define new ones
            itemContainer.className = 'grid__item-container js-grid-item-container'; 
            
            const currentImageAspectRatio = typeof imgData.aspectRatio === 'number' && !isNaN(imgData.aspectRatio) ? imgData.aspectRatio : 1;
            const flexBasis = rowAspectRatioSum > 0 ? (currentImageAspectRatio / rowAspectRatioSum) * 100 : (100 / rowImages.length);
            itemContainer.style.flexBasis = `${flexBasis}%`;

            const newImgElement = document.createElement('img');
            newImgElement.src = imgData.element.src;
            newImgElement.alt = imgData.element.alt || '';
            
            // Transfer classes from the original image element, or use defaults
            // The original build.js used: "grid__item-image js-grid__item-image grid__item-image-lazy js-lazy"
            newImgElement.className = imgData.element.className.replace('gallery-image-source', '').trim() 
                                     || 'grid__item-image js-grid__item-image grid__item-image-lazy js-lazy';
            // Ensure 'gallery-image-source' is removed if it was there, and add common gallery item classes
             if (!newImgElement.classList.contains('grid__item-image')) {
                newImgElement.classList.add('grid__item-image');
            }


            newImgElement.style.aspectRatio = `${currentImageAspectRatio}`;
            newImgElement.style.height = '100%';
            newImgElement.style.objectFit = 'cover'; // Ensures image covers the container maintaining aspect ratio

            // Preserve onclick attribute for lightbox functionality
            const onclickAttribute = imgData.element.getAttribute('onclick');
            if (onclickAttribute) {
                newImgElement.setAttribute('onclick', onclickAttribute);
            }

            itemContainer.appendChild(newImgElement);
            rowElement.appendChild(itemContainer);
        });
        galleryContainer.appendChild(rowElement);
    });

    // If a lazy loading library was used (e.g., for .js-lazy),
    // it might need to be re-initialized here.
    // For example, if there's a global function like `window.reinitLazyLoad()`:
    // if (typeof window.reinitLazyLoad === 'function') {
    //     window.reinitLazyLoad();
    // }
}
