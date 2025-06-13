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
