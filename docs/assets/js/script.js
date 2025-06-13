// Function to open the lightbox with the selected image
function openLightbox(imgSrc) {
  const lightbox = document.getElementById('lightbox');
  const lightboxImg = lightbox.querySelector('img');

  lightboxImg.src = imgSrc; // Set the source of the image in the lightbox
  lightbox.style.display = 'flex'; // Display the lightbox
}

// Function to close the lightbox
function closeLightbox() {
  const lightbox = document.getElementById('lightbox');
  lightbox.style.display = 'none'; // Hide the lightbox
}

// Event listener to close the lightbox when the Escape key is pressed
document.addEventListener('keydown', function(event) {
  if (event.key === 'Escape') {
    closeLightbox(); // Call the closeLightbox function
  }
});

// Mobile navigation
const burger = document.querySelector('.header__burger'); // Burger icon
const nav = document.getElementById('mobile-nav'); // Navigation menu

// Event listener to toggle the navigation menu on burger icon click
burger.addEventListener('click', () => {
  nav.style.display = nav.style.display === 'block' ? 'none' : 'block'; // Toggle the display of the navigation menu
});
