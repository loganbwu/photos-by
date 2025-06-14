const fs = require('fs').promises;
const path = require('path');

// --- Configuration ---
const SRC_DIR = {
    photos: 'photos',
    partials: 'partials',
    assets: 'assets',
    templates: '.', // base.html.template is in the root
};

const BUILD_DIR = 'docs';
const ASSETS_BUILD_DIR = path.join(BUILD_DIR, 'assets');
const PHOTOS_BUILD_DIR = path.join(BUILD_DIR, 'photos');

const TEMPLATE_FILE = 'base.html.template';

const PARTIAL_FILES = {
    header: 'header_partial.html',
    footer: 'footer_partial.html',
    contact: 'contact_partial.html',
    firstShoot: 'first_shoot_partial.html',
    standardAgreement: 'standard_agreement_partial.html',
};

const PAGES = [
    {
        name: 'index.html',
        contentKey: 'gallery', // Special key for gallery content
    },
    {
        name: 'contact.html',
        contentKey: 'contact',
        partial: PARTIAL_FILES.contact,
    },
    {
        name: 'first_shoot.html',
        contentKey: 'firstShoot',
        partial: PARTIAL_FILES.firstShoot,
    },
    {
        name: 'standard_agreement.html',
        contentKey: 'standardAgreement',
        partial: PARTIAL_FILES.standardAgreement,
    },
];

// --- Helper Functions ---

async function readFileContent(filePath, isCritical = true) {
    try {
        return await fs.readFile(filePath, 'utf8');
    } catch (err) {
        console.error(`Error reading file ${filePath}:`, err.message);
        if (isCritical) {
            throw err; // Re-throw if critical, allowing build to fail
        }
        return ''; // Return empty for non-critical files (e.g., optional partials)
    }
}

async function writeFileContent(filePath, content) {
    try {
        await fs.writeFile(filePath, content, 'utf8');
        console.log(`${path.basename(filePath)} updated successfully!`);
    } catch (err) {
        console.error(`Error writing file ${filePath}:`, err.message);
        throw err;
    }
}

async function copyDirectoryRecursive(sourceDir, targetDir) {
    try {
        await fs.mkdir(targetDir, { recursive: true });
        const entries = await fs.readdir(sourceDir, { withFileTypes: true });
        for (const entry of entries) {
            const srcPath = path.join(sourceDir, entry.name);
            const destPath = path.join(targetDir, entry.name);
            if (entry.isDirectory()) {
                await copyDirectoryRecursive(srcPath, destPath);
            } else {
                await fs.copyFile(srcPath, destPath);
            }
        }
    } catch (err) {
        console.error(`Error copying directory ${sourceDir} to ${targetDir}:`, err.message);
        throw err;
    }
}

async function getImageFiles(directory) {
    try {
        const files = await fs.readdir(directory);
        return files.filter(file => /\.(jpg|jpeg|png)$/i.test(file));
    } catch (err) {
        console.error(`Error scanning image directory ${directory}:`, err.message);
        throw err; // Image directory is critical
    }
}

function generateGalleryHTML(imageFiles) {
    let html = '<div id="image-gallery-container" class="image-gallery-container">';
    imageFiles.forEach(imageFile => {
        html += `
      <img src="${path.join(SRC_DIR.photos, imageFile)}" alt="${imageFile}" class="gallery-image-source grid__item-image-lazy js-lazy" onclick="openLightbox('${path.join(SRC_DIR.photos, imageFile)}')">`;
    });
    html += `
    </div>`;
    return html;
}

async function loadPartials() {
    const loadedPartials = {};
    for (const key in PARTIAL_FILES) {
        const partialPath = path.join(SRC_DIR.partials, PARTIAL_FILES[key]);
        // Header and Footer are critical, others might be optional depending on design
        const isCriticalPartial = key === 'header' || key === 'footer';
        loadedPartials[key] = await readFileContent(partialPath, isCriticalPartial);
    }
    return loadedPartials;
}

// --- Main Build Logic ---

async function buildSite() {
    console.log('Starting build process...');

    // 1. Ensure build directory exists
    try {
        await fs.mkdir(BUILD_DIR, { recursive: true });
        console.log(`Build directory '${BUILD_DIR}' ensured.`);
    } catch (err) {
        console.error('Failed to create build directory:', err.message);
        return; // Exit if we can't create the main build directory
    }

    // 2. Load base template and common partials
    const baseTemplatePath = path.join(SRC_DIR.templates, TEMPLATE_FILE);
    const baseTemplateContent = await readFileContent(baseTemplatePath);
    if (!baseTemplateContent) return; // Exit if base template fails to load

    const partials = await loadPartials();
    if (!partials.header || !partials.footer) {
        console.error('Critical header or footer partial missing. Aborting build.');
        return;
    }
    
    // 3. Prepare gallery content (if needed for index page)
    let galleryHTML = '';
    if (PAGES.some(page => page.contentKey === 'gallery')) {
        const imageFiles = await getImageFiles(SRC_DIR.photos);
        console.log(`Found ${imageFiles.length} images.`);
        galleryHTML = generateGalleryHTML(imageFiles);
    }

    // 4. Build each page
    for (const page of PAGES) {
        let pageSpecificContent = '';
        if (page.contentKey === 'gallery') {
            pageSpecificContent = galleryHTML;
        } else if (page.partial && partials[page.contentKey]) {
            pageSpecificContent = partials[page.contentKey];
        } else if (page.partial) {
            console.warn(`Partial for page ${page.name} (key: ${page.contentKey}) not found or failed to load. Page might be incomplete.`);
        }

        const pageHtml = baseTemplateContent
            .replace('<!-- HEADER_PLACEHOLDER -->', partials.header)
            .replace('<!-- FOOTER_PLACEHOLDER -->', partials.footer)
            .replace('<!-- CONTENT_PLACEHOLDER -->', pageSpecificContent);

        const outputPath = path.join(BUILD_DIR, page.name);
        await writeFileContent(outputPath, pageHtml);
    }

    // 5. Copy assets and photos
    console.log('Copying assets...');
    await copyDirectoryRecursive(SRC_DIR.assets, ASSETS_BUILD_DIR);
    console.log('Assets copied.');

    console.log('Copying photos...');
    await copyDirectoryRecursive(SRC_DIR.photos, PHOTOS_BUILD_DIR);
    console.log('Photos copied.');

    // 6. Create CNAME file
    const cnamePath = path.join(BUILD_DIR, 'CNAME');
    await writeFileContent(cnamePath, 'photosby.loganwu.co.nz');
    console.log('CNAME file created.');

    console.log('Build process completed successfully!');
}

// --- Run Build ---
buildSite().catch(err => {
    console.error('Unhandled error during build process:', err.message);
    process.exit(1); // Exit with error code
});
