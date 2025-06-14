const fs = require('fs');
const path = require('path');

// Define paths
const directoryPath = path.join('photos');
const buildDir = path.join('docs');
const indexPath = path.join(buildDir, 'index.html');
const standardAgreementPath = path.join(buildDir, 'standard_agreement.html');
const firstShootPath = path.join(buildDir, 'first_shoot.html');
const contactPath = path.join(buildDir, 'contact.html');
const templatePath = path.join('base.html.template');
const partialsPath = path.join('partials');
const assetsPath = path.join('assets');
const photosPath = 'photos';
const standardAgreementPartialPath = path.join('partials', 'standard_agreement_partial.html');
const firstShootPartialPath = path.join('partials', 'first_shoot_partial.html');
const headerPartialPath = path.join('partials', 'header_partial.html');
const footerPartialPath = path.join('partials', 'footer_partial.html');
const contactPartialPath = path.join('partials', 'contact_partial.html');

// Helper function to read file content
function readFileContent(filePath) {
  try {
    return fs.readFileSync(filePath, 'utf8');
  } catch (err) {
    console.error(`Unable to read ${filePath}: ${err}`);
    return '';
  }
}

// Read partial content
const standardAgreementContent = readFileContent(standardAgreementPartialPath);
const firstShootContent = readFileContent(firstShootPartialPath);
const headerContent = readFileContent(headerPartialPath);
const footerContent = readFileContent(footerPartialPath);
const contactContent = readFileContent(contactPartialPath);

// Read filelist.json
  fs.readdir(directoryPath, function (err, files) {
  if (err) {
    return console.log('Unable to scan directory: ' + err);
  }

  const filelist = files.filter(file => file.endsWith('.jpg') || file.endsWith('.jpeg') || file.endsWith('.png'));
  console.log('Files found in directory: ' + filelist);

  // Generate thumbnail HTML
  let thumbnailHTML = '<div id="image-gallery-container" class="image-gallery-container">'; // Container for the client-side script
  filelist.forEach(imageFile => {
    // Add original classes that might be used by lightbox or lazy loading, plus the new source class
    thumbnailHTML += `
      <img src="photos/${imageFile}" alt="${imageFile}" class="gallery-image-source grid__item-image-lazy js-lazy" onclick="openLightbox('photos/${imageFile}')">
    `;
  });
  thumbnailHTML += `</div>`;

  // Read template file
  fs.readFile(templatePath, 'utf8', function (err, data) {
    if (err) {
      return console.log('Unable to read base.html.template: ' + err);
    }

    console.log('Original base.html.template content: ' + data);

    // Replace placeholders
    const newIndexHTML = data.replace('<!-- HEADER_PLACEHOLDER -->', headerContent)
      .replace('<!-- FOOTER_PLACEHOLDER -->', footerContent)
      .replace('<!-- CONTENT_PLACEHOLDER -->', thumbnailHTML);

    const newFirstShootHTML = data.replace('<!-- HEADER_PLACEHOLDER -->', headerContent)
      .replace('<!-- FOOTER_PLACEHOLDER -->', footerContent)
      .replace('<!-- CONTENT_PLACEHOLDER -->', firstShootContent);

    const newStandardAgreementHTML = data.replace('<!-- HEADER_PLACEHOLDER -->', headerContent)
      .replace('<!-- FOOTER_PLACEHOLDER -->', footerContent)
      .replace('<!-- CONTENT_PLACEHOLDER -->', standardAgreementContent);

    const newContactHTML = data.replace('<!-- HEADER_PLACEHOLDER -->', headerContent)
      .replace('<!-- FOOTER_PLACEHOLDER -->', footerContent)
      .replace('<!-- CONTENT_PLACEHOLDER -->', contactContent);

    // Write updated files
    // Create the build directory if it doesn't exist
    if (!fs.existsSync(buildDir)) {
      fs.mkdirSync(buildDir, { recursive: true });
    }

    // Copy assets directory
    fs.cpSync(assetsPath, path.join(buildDir, 'assets'), { recursive: true });

    // Copy photos directory
    fs.cpSync(photosPath, path.join(buildDir, 'photos'), { recursive: true });

    fs.writeFile(indexPath, newIndexHTML, function (err) {
      if (err) {
        return console.log('Unable to write index.html: ' + err);
      }
      console.log('index.html updated successfully!');
      console.log('index.html rebuilt!');
    });

    fs.writeFile(firstShootPath, newFirstShootHTML, function (err) {
      if (err) {
        return console.log('Unable to write first_shoot.html: ' + err);
      }
      console.log('first_shoot.html updated successfully!');
      console.log('first_shoot.html rebuilt!');
    });

    fs.writeFile(standardAgreementPath, newStandardAgreementHTML, function (err) {
      if (err) {
        return console.log('Unable to write standard_agreement.html: ' + err);
      }
      console.log('standard_agreement.html updated successfully!');
      console.log('standard_agreement.html rebuilt!');
    });

    fs.writeFile(contactPath, newContactHTML, function (err) {
      if (err) {
        return console.log('Unable to write contact.html: ' + err);
      }
      console.log('contact.html updated successfully!');
      console.log('contact.html rebuilt!');
    });
  });
});
