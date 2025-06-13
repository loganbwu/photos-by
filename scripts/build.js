const fs = require('fs');
const path = require('path');
const sizeOf = require('image-size').imageSize;

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

  // Calculate aspect ratios
  const aspectRatios = {};
  filelist.forEach(file => {
    try {
      const imagePath = path.join(directoryPath, file);
      const buffer = fs.readFileSync(imagePath);
      const dimensions = sizeOf(buffer);
      aspectRatios[file] = dimensions.width / dimensions.height;
    } catch (err) {
      console.log(`Error getting dimensions for ${file}: ${err}`);
      aspectRatios[file] = 1; // Default aspect ratio
    }
  });

  // Generate thumbnail HTML
  let thumbnailHTML = '';
  const rows = [];
  for (let i = 0; i < filelist.length; i += 3) {
    rows.push(filelist.slice(i, i + 3));
  }

  rows.forEach(row => {
    thumbnailHTML += `<div class="grid__row">`;
    const rowAspectRatioSum = row.reduce((sum, imageFile) => sum + aspectRatios[imageFile], 0);

    row.forEach(imageFile => {
      const aspectRatio = aspectRatios[imageFile];
      const flexBasis = (aspectRatio / rowAspectRatioSum) * 100;

      console.log(`${imageFile}: aspectRatio=${aspectRatio}, flexBasis=${flexBasis}`);

      thumbnailHTML += `
        <div class="grid__item-container js-grid-item-container" style="flex-basis: ${flexBasis}%;">
          <img src="photos/${imageFile}" alt="${imageFile}" class="grid__item-image js-grid__item-image grid__item-image-lazy js-lazy" style="aspect-ratio: ${aspectRatio}; height: 100%; object-fit: cover;" onclick="openLightbox('photos/${imageFile}')">
        </div>
      `;
    });
    thumbnailHTML += `</div>`;
  });

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
