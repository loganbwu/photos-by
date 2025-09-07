let images = [];
let currentIndex = 0;
const lightbox = document.getElementById('lightbox');
const lightboxImg = lightbox.querySelector('img');
let hasWiggleAnimatedThisLoad = false; // Flag to track animation per page load
let isPrivate = false;

// Function to show a specific image in the lightbox
function showImage(index) {
  if (images.length === 0) return;
  currentIndex = (index + images.length) % images.length; // Handle wrapping
  const image = images[currentIndex];
  lightboxImg.src = image.src;
  const lightboxFilename = document.getElementById('lightbox-filename');
  
  // Handle filename display - only show for private galleries
  if (lightboxFilename) {
    if (isPrivate) {
      lightboxFilename.textContent = image.filename;
      lightboxFilename.style.display = 'block';
      positionFilename();
    } else {
      lightboxFilename.style.display = 'none';
    }
  }
}

// Variables for image container and additional images (global scope)
let imageContainer = null;
let nextImg = null;
let prevImg = null;

// Function to initialize the swipe container (called when lightbox opens)
function initializeSwipeContainer() {
  if (imageContainer) return; // Already initialized
  
  // Create container for image transitions
  imageContainer = document.createElement('div');
  imageContainer.className = 'lightbox-image-container';
  
  // Move the existing image into the container
  lightboxImg.parentNode.insertBefore(imageContainer, lightboxImg);
  imageContainer.appendChild(lightboxImg);
  
  // Create next and previous image elements for smooth transitions
  nextImg = document.createElement('img');
  nextImg.className = 'lightbox-image lightbox-next-image';
  prevImg = document.createElement('img');
  prevImg.className = 'lightbox-image lightbox-prev-image';
  
  imageContainer.appendChild(nextImg);
  imageContainer.appendChild(prevImg);
}

// Function to open the lightbox with the selected image
function openLightbox(imgSrc, index) {
  // Initialize swipe container if not already done
  initializeSwipeContainer();
  
  const image = images[index];
  lightboxImg.src = image.src; // Set the source of the image in the lightbox
  const lightboxFilename = document.getElementById('lightbox-filename');
  
  // Handle filename display - only show for private galleries
  if (lightboxFilename) {
    if (isPrivate) {
      lightboxFilename.textContent = image.filename;
      lightboxFilename.style.display = 'block';
    } else {
      lightboxFilename.style.display = 'none';
    }
  }
  
  lightbox.style.display = 'flex'; // Display the lightbox
  currentIndex = index; // Set the current index
  if (isPrivate) {
    // Use a short delay to allow the image to render and get correct dimensions
    setTimeout(positionFilename, 50);
  }

  // Wiggle animation logic
  const prevButton = document.getElementById('prev-button');
  const nextButton = document.getElementById('next-button');

  // Check if nav buttons are hidden (common on mobile)
  const navButtonsHidden = (prevButton && getComputedStyle(prevButton).display === 'none') || 
                           (nextButton && getComputedStyle(nextButton).display === 'none');

  if (!hasWiggleAnimatedThisLoad && navButtonsHidden) {
    lightboxImg.classList.add('lightbox-image-wiggle');
    hasWiggleAnimatedThisLoad = true; // Set flag for this page load

    function handleAnimationEnd() {
      lightboxImg.classList.remove('lightbox-image-wiggle');
      lightboxImg.removeEventListener('animationend', handleAnimationEnd);
    }
    lightboxImg.addEventListener('animationend', handleAnimationEnd);
  }
}

// Function to close the lightbox
function closeLightbox() {
  lightbox.style.display = 'none'; // Hide the lightbox
}

// Function to navigate to the next image
function nextImage() {
  showImage(currentIndex + 1);
}

// Function to navigate to the previous image
function prevImage() {
  showImage(currentIndex - 1);
}

function positionFilename() {
    const lightboxFilename = document.getElementById('lightbox-filename');
    if (!lightboxFilename || !isPrivate) return;

    const imgRect = lightboxImg.getBoundingClientRect();
    
    // Position the filename relative to the lightbox container
    lightboxFilename.style.top = `${imgRect.top + 10}px`;
    lightboxFilename.style.left = `${imgRect.left + 10}px`;
}

// Reposition filename on window resize
window.addEventListener('resize', positionFilename);

// Event listener to close the lightbox when the Escape key is pressed
document.addEventListener('keydown', function(event) {
  if (event.key === 'Escape') {
    closeLightbox(); // Call the closeLightbox function
  } else if (event.key === 'ArrowLeft') {
    prevImage();
  } else if (event.key === 'ArrowRight') {
    nextImage();
  }
});

// Function to initialize lightbox state and listeners for gallery images
// Make it globally accessible for gallery.js
window.initializeLightboxStateAndListeners = function(isPrivateView = false) {
  isPrivate = isPrivateView;
  images = []; // Clear existing images before repopulating
  const galleryImages = document.querySelectorAll('.grid__item-image');
  galleryImages.forEach((img, index) => {
    const filename = img.src.split('?')[0].split('/').pop();
    images.push({ src: img.src, filename: filename }); // Populate the images array
    // Remove any old listener before adding a new one to prevent duplicates if this function is called multiple times
    img.removeEventListener('click', openLightboxOnClick); // Use a named function for removal
    img.addEventListener('click', function() { openLightboxOnClick(img.src, index); });
  });
}

// Named function for the event listener to allow removal
function openLightboxOnClick(src, index) {
  openLightbox(src, index);
}

// Event listeners for general lightbox functionality (nav buttons, escape key)
document.addEventListener('DOMContentLoaded', () => {
  // Prevent right-click on lightbox image
  if (lightboxImg) {
  }
  
  // Initial setup for gallery images - will be re-run by gallery.js after it renders
  initializeLightboxStateAndListeners();

  const prevButton = document.getElementById('prev-button');
  const nextButton = document.getElementById('next-button');

  if (prevButton) {
    prevButton.addEventListener('click', prevImage);
  }
  if (nextButton) {
    nextButton.addEventListener('click', nextImage);
  }

  // Enhanced swipe and drag functionality for mobile and desktop
  let isPointerDown = false;
  let touchStartX = 0;
  let touchStartY = 0;
  let currentTouchX = 0;
  let isDragging = false;
  let dragOffset = 0;
  const minSwipeDistance = 50; // pixels
  const swipeThreshold = 0.3; // 30% of screen width to trigger swipe

  function pointerDown(e) {
    isPointerDown = true;
    lightbox.style.cursor = 'grabbing';
    touchStartX = e.touches ? e.touches[0].clientX : e.clientX;
    touchStartY = e.touches ? e.touches[0].clientY : e.clientY;
    currentTouchX = touchStartX;
    isDragging = false;
    dragOffset = 0;
    
    // Prepare adjacent images
    if (images.length > 1) {
      const nextIndex = (currentIndex + 1) % images.length;
      const prevIndex = (currentIndex - 1 + images.length) % images.length;
      nextImg.src = images[nextIndex].src;
      prevImg.src = images[prevIndex].src;
    }
  }

  function pointerMove(e) {
    if (!isPointerDown) return;
    e.preventDefault(); // Prevent default browser actions like image saving
    currentTouchX = e.touches ? e.touches[0].clientX : e.clientX;
    const touchY = e.touches ? e.touches[0].clientY : e.clientY;
    
    const deltaX = currentTouchX - touchStartX;
    const deltaY = touchY - touchStartY;
    
    // Only start dragging if horizontal movement is greater than vertical
    if (!isDragging && Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 10) {
      isDragging = true;
    }
    
    if (isDragging && images.length > 1) {
      dragOffset = deltaX;
      updateImagePositions(dragOffset);
    }
  }

  function pointerUp(e) {
    if (!isPointerDown) return;
    isPointerDown = false;
    lightbox.style.cursor = 'default';

    if (isDragging && images.length > 1) {
      const screenWidth = window.innerWidth;
      const swipeDistance = Math.abs(dragOffset);
      const swipePercentage = swipeDistance / screenWidth;
      
      if (swipePercentage > swipeThreshold || swipeDistance > minSwipeDistance) {
        // Complete the swipe
        if (dragOffset < 0) {
          // Swiped left - go to next image
          completeSwipe('next');
        } else {
          // Swiped right - go to previous image
          completeSwipe('prev');
        }
      } else {
        // Snap back to current image
        snapBack();
      }
    }
    
    // Reset values
    isDragging = false;
    dragOffset = 0;
  }

  // Touch events
  lightbox.addEventListener('touchstart', pointerDown);
  lightbox.addEventListener('touchmove', pointerMove);
  lightbox.addEventListener('touchend', pointerUp);

  // Mouse events
  lightbox.addEventListener('mousedown', pointerDown);
  lightbox.addEventListener('mousemove', pointerMove);
  lightbox.addEventListener('mouseup', pointerUp);
  lightbox.addEventListener('mouseleave', pointerUp); // Also end drag on mouse leave
  
  function updateImagePositions(offset) {
    const screenWidth = window.innerWidth;
    
    // Move current image
    lightboxImg.style.transform = `translateX(${offset}px)`;
    
    if (offset < 0) {
      // Dragging left - show next image
      nextImg.style.transform = `translateX(${screenWidth + offset}px)`;
      nextImg.style.opacity = '1';
      prevImg.style.opacity = '0';
    } else {
      // Dragging right - show previous image
      prevImg.style.transform = `translateX(${-screenWidth + offset}px)`;
      prevImg.style.opacity = '1';
      nextImg.style.opacity = '0';
    }
  }
  
  function completeSwipe(direction) {
    const screenWidth = window.innerWidth;
    
    // Add transition for smooth completion
    lightboxImg.style.transition = 'transform 0.3s ease-out';
    nextImg.style.transition = 'transform 0.3s ease-out';
    prevImg.style.transition = 'transform 0.3s ease-out';
    
    if (direction === 'next') {
      lightboxImg.style.transform = `translateX(-${screenWidth}px)`;
      nextImg.style.transform = 'translateX(0)';
      setTimeout(() => {
        nextImage();
        resetImagePositions();
      }, 300);
    } else {
      lightboxImg.style.transform = `translateX(${screenWidth}px)`;
      prevImg.style.transform = 'translateX(0)';
      setTimeout(() => {
        prevImage();
        resetImagePositions();
      }, 300);
    }
  }
  
  function snapBack() {
    // Add transition for smooth snap back
    lightboxImg.style.transition = 'transform 0.3s ease-out';
    nextImg.style.transition = 'transform 0.3s ease-out, opacity 0.3s ease-out';
    prevImg.style.transition = 'transform 0.3s ease-out, opacity 0.3s ease-out';
    
    // Reset positions
    lightboxImg.style.transform = 'translateX(0)';
    nextImg.style.transform = 'translateX(100vw)';
    prevImg.style.transform = 'translateX(-100vw)';
    nextImg.style.opacity = '0';
    prevImg.style.opacity = '0';
    
    setTimeout(resetImagePositions, 300);
  }
  
  function resetImagePositions() {
    // Remove transitions and reset positions
    lightboxImg.style.transition = '';
    nextImg.style.transition = '';
    prevImg.style.transition = '';
    lightboxImg.style.transform = '';
    nextImg.style.transform = '';
    prevImg.style.transform = '';
    nextImg.style.opacity = '0';
    prevImg.style.opacity = '0';
    
    // Ensure filename is repositioned after swipe for private galleries
    if (isPrivate) {
      setTimeout(positionFilename, 50);
    }
  }
});
