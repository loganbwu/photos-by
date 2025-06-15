let images = [];
let currentIndex = 0;
const lightbox = document.getElementById('lightbox');
const lightboxImg = lightbox.querySelector('img');
let hasWiggleAnimatedThisLoad = false; // Flag to track animation per page load

// Function to show a specific image in the lightbox
function showImage(index) {
  if (images.length === 0) return;
  currentIndex = (index + images.length) % images.length; // Handle wrapping
  lightboxImg.src = images[currentIndex];
}

// Function to open the lightbox with the selected image
function openLightbox(imgSrc, index) {
  lightboxImg.src = imgSrc; // Set the source of the image in the lightbox
  lightbox.style.display = 'flex'; // Display the lightbox
  currentIndex = index; // Set the current index

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
window.initializeLightboxStateAndListeners = function() {
  images = []; // Clear existing images before repopulating
  const galleryImages = document.querySelectorAll('.grid__item-image');
  galleryImages.forEach((img, index) => {
    images.push(img.src); // Populate the images array
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

  // Swipe functionality for mobile
  let touchStartX = 0;
  let touchEndX = 0;
  const minSwipeDistance = 50; // pixels

  lightbox.addEventListener('touchstart', (e) => {
    touchStartX = e.touches[0].clientX;
  });

  lightbox.addEventListener('touchmove', (e) => {
    touchEndX = e.touches[0].clientX;
  });

  lightbox.addEventListener('touchend', () => {
    if (touchEndX < touchStartX - minSwipeDistance) {
      nextImage(); // Swiped left
    }
    if (touchEndX > touchStartX + minSwipeDistance) {
      prevImage(); // Swiped right
    }
    touchStartX = 0;
    touchEndX = 0;
  });
});
