let images = [];
let currentIndex = 0;
const lightbox = document.getElementById('lightbox');
const lightboxImg = lightbox.querySelector('img');

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

// Event listeners for navigation buttons
document.addEventListener('DOMContentLoaded', () => {
  const galleryImages = document.querySelectorAll('.grid__item-image');
  galleryImages.forEach((img, index) => {
    images.push(img.src); // Populate the images array
    img.addEventListener('click', () => {
      openLightbox(img.src, index);
    });
  });

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
