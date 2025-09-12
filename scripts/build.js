const fs = require('fs').promises;
const path = require('path');

// --- Configuration ---
const SRC_DIR = {
    photos: 'frontend/photos',
    partials: 'frontend/partials',
    assets: 'frontend/assets',
    templates: 'frontend', // base.html.template is in the frontend directory
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
    privateGallery: 'albums_partial.html',
    booking: 'booking_partial.html',
};

const PAGES = [
    {
        name: 'index.html',
        pathPrefix: '',
        homePathPrefix: '',
        contentKey: 'gallery', // Special key for gallery content
        title: 'Photos by Logan | Melbourne & Shanghai Pole & Aerial Photography',
        metaDescription: 'Stunning pole dance and aerial arts photography by Logan, based in Melbourne and Shanghai. Specializing in studio photoshots and event photography/videography.',
    },
    {
        name: 'contact/index.html',
        pathPrefix: '../',
        homePathPrefix: '../',
        contentKey: 'contact',
        partial: PARTIAL_FILES.contact,
        title: 'Contact Photos by Logan | Pole & Aerial Photographer',
        metaDescription: 'Get in touch with Logan for pole dance and aerial arts photography services in Melbourne and Shanghai. Event coverage and studio shoots available.',
    },
    {
        name: 'first_shoot/index.html',
        pathPrefix: '../',
        homePathPrefix: '../',
        contentKey: 'firstShoot',
        partial: PARTIAL_FILES.firstShoot,
        title: 'Your First Pole/Aerial Photo Shoot Guide | Photos by Logan',
        metaDescription: 'Preparing for your first pole dance or aerial photo shoot? Get tips and advice from Photos by Logan to make the most of your session.',
    },
    {
        name: 'standard_agreement/index.html',
        pathPrefix: '../',
        homePathPrefix: '../',
        contentKey: 'standardAgreement',
        partial: PARTIAL_FILES.standardAgreement,
        title: 'Photography Agreement | Photos by Logan',
        metaDescription: 'Review the standard photography session agreement for photoshoots with Photos by Logan.',
    },
    {
        name: 'albums/index.html',
        pathPrefix: '../',
        homePathPrefix: '../',
        contentKey: 'privateGallery',
        partial: PARTIAL_FILES.privateGallery,
        title: 'Albums | Photos by Logan',
        metaDescription: 'Access a private photo album.',
        scripts: ['assets/js/private-gallery.js'] // Page-specific script
    },
    {
        name: 'booking/index.html',
        pathPrefix: '../',
        homePathPrefix: '../',
        contentKey: 'booking',
        partial: PARTIAL_FILES.booking,
        title: 'Booking | Photos by Logan',
        metaDescription: 'Book a photoshoot session.',
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
        await fs.mkdir(path.dirname(filePath), { recursive: true });
        await fs.writeFile(filePath, content, 'utf8');
        console.log(`${filePath} updated successfully!`);
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
        // Improved alt text
        const descriptiveAlt = `Pole and aerial arts photo by Logan - ${imageFile.replace(/\.[^/.]+$/, "")}`;
        const webPath = path.join('photos', imageFile).replace(/\\/g, '/'); // Ensure forward slashes for web
        html += `
      <img src="${webPath}" alt="${descriptiveAlt}" class="gallery-image-source grid__item-image-lazy js-lazy" onclick="openLightbox('${webPath}')">`;
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
            .replace(/<!-- PATH_PREFIX -->/g, page.pathPrefix)
            .replace(/<!-- HOME_PATH_PREFIX -->/g, page.homePathPrefix)
            .replace('<!-- TITLE_PLACEHOLDER -->', page.title || 'Photos by Logan')
            .replace('<!-- META_DESCRIPTION_PLACEHOLDER -->', page.metaDescription ? `<meta name="description" content="${page.metaDescription}">` : '')
            .replace('<!-- HEADER_PLACEHOLDER -->', partials.header)
            .replace('<!-- FOOTER_PLACEHOLDER -->', partials.footer)
            .replace('<!-- CONTENT_PLACEHOLDER -->', pageSpecificContent)
            .replace('<!-- PAGE_SPECIFIC_SCRIPTS_PLACEHOLDER -->', page.scripts ? page.scripts.map(scriptPath => `<script src="${page.pathPrefix}${scriptPath}" defer></script>`).join('\n') : '');

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
    await writeFileContent(cnamePath, 'photosby.loganwu.co.nz'); // Updated CNAME
    console.log('CNAME file created.');

    console.log('Build process completed successfully!');
}

// --- Run Build ---
buildSite().catch(err => {
    console.error('Unhandled error during build process:', err.message);
    process.exit(1); // Exit with error code
});
