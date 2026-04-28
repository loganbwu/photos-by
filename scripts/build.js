const fs = require('fs').promises;
const path = require('path');
const { marked } = require('marked');

// --- Configuration ---
const SRC_DIR = {
    photos: 'frontend/photos',
    partials: 'frontend/partials',
    assets: 'frontend/assets',
    templates: 'frontend',
};

const BUILD_DIR = 'docs';
const ASSETS_BUILD_DIR = path.join(BUILD_DIR, 'assets');
const PHOTOS_BUILD_DIR = path.join(BUILD_DIR, 'photos');

const TEMPLATE_FILE = 'base.html.template';

// Partials are auto-discovered from frontend/partials/*_partial.{html,md}.
// PAGES entries without a matching partial will warn; discovered partials without
// a matching PAGES entry will get a default page at {slug}/index.html.
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
        title: 'Contact Photos by Logan | Pole & Aerial Photographer',
        metaDescription: 'Get in touch with Logan for pole dance and aerial arts photography services in Melbourne and Shanghai. Event coverage and studio shoots available.',
    },
    {
        name: 'first_shoot/index.html',
        pathPrefix: '../',
        homePathPrefix: '../',
        contentKey: 'firstShoot',
        title: 'Your First Pole/Aerial Photo Shoot Guide | Photos by Logan',
        metaDescription: 'Preparing for your first pole dance or aerial photo shoot? Get tips and advice from Photos by Logan to make the most of your session.',
    },
    {
        name: 'standard_agreement/index.html',
        pathPrefix: '../',
        homePathPrefix: '../',
        contentKey: 'standardAgreement',
        title: 'Photography Agreement | Photos by Logan',
        metaDescription: 'Review the standard photography session agreement for photoshoots with Photos by Logan.',
    },
    {
        name: 'albums/index.html',
        pathPrefix: '../',
        homePathPrefix: '../',
        contentKey: 'albums',
        title: 'Albums | Photos by Logan',
        metaDescription: 'Access a private photo album.',
        scripts: ['assets/js/private-gallery.js'],
    },
    {
        name: 'booking/index.html',
        pathPrefix: '../',
        homePathPrefix: '../',
        contentKey: 'booking',
        title: 'Booking | Photos by Logan',
        metaDescription: 'Book a photoshoot session.',
    },
    {
        name: 'babyg/index.html',
        pathPrefix: '../',
        homePathPrefix: '../',
        contentKey: 'babyg',
        title: "Gabby's birthday | Photos by Logan",
        metaDescription: "Guests and performances from Gabby's birthday and cancer remission celebration.",
    },
    {
        name: 'sirens/index.html',
        pathPrefix: '../',
        homePathPrefix: '../',
        contentKey: 'sirens',
        title: 'Sirens Pole Competition | Photos by Logan',
        metaDescription: 'Sirens pole competition media.',
    },
];

// --- Helper Functions ---

// "first_shoot_partial.html" -> "firstShoot"
function filenameToKey(filename) {
    const slug = filename.replace(/_partial\.(html|md)$/, '');
    return slug.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
}

// "firstShoot" -> "first_shoot"
function keyToSlug(key) {
    return key.replace(/([A-Z])/g, '_$1').toLowerCase();
}

// "first_shoot" -> "First Shoot"
function slugToTitle(slug) {
    return slug.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

async function readFileContent(filePath, isCritical = true) {
    try {
        return await fs.readFile(filePath, 'utf8');
    } catch (err) {
        console.error(`Error reading file ${filePath}:`, err.message);
        if (isCritical) {
            throw err;
        }
        return '';
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
        throw err;
    }
}

function generateGalleryHTML(imageFiles) {
    let html = '<div id="image-gallery-container" class="image-gallery-container">';
    imageFiles.forEach(imageFile => {
        const descriptiveAlt = `Pole and aerial arts photo by Logan - ${imageFile.replace(/\.[^/.]+$/, "")}`;
        const webPath = path.join('photos', imageFile).replace(/\\/g, '/');
        html += `
      <img src="${webPath}" alt="${descriptiveAlt}" class="gallery-image-source grid__item-image-lazy js-lazy" onclick="openLightbox('${webPath}')">`;
    });
    html += `
    </div>`;
    return html;
}

async function loadPartials() {
    const files = await fs.readdir(SRC_DIR.partials);
    const partialFiles = files.filter(f => /_partial\.(html|md)$/.test(f));
    const loadedPartials = {};
    for (const filename of partialFiles) {
        const key = filenameToKey(filename);
        const partialPath = path.join(SRC_DIR.partials, filename);
        const isCritical = key === 'header' || key === 'footer';
        const content = await readFileContent(partialPath, isCritical);
        loadedPartials[key] = filename.endsWith('.md') ? `<article id="${key}">${marked(content)}</article>` : content;
    }
    return loadedPartials;
}

// --- Main Build Logic ---

async function buildSite() {
    console.log('Starting build process...');

    try {
        await fs.rm(BUILD_DIR, { recursive: true, force: true });
        await fs.mkdir(BUILD_DIR, { recursive: true });
        console.log(`Build directory '${BUILD_DIR}' cleaned and recreated.`);
    } catch (err) {
        console.error('Failed to prepare build directory:', err.message);
        return;
    }

    const baseTemplatePath = path.join(SRC_DIR.templates, TEMPLATE_FILE);
    const baseTemplateContent = await readFileContent(baseTemplatePath);
    if (!baseTemplateContent) return;

    const partials = await loadPartials();
    if (!partials.header || !partials.footer) {
        console.error('Critical header or footer partial missing. Aborting build.');
        return;
    }

    // Extend PAGES with defaults for any discovered partials not explicitly declared
    const SKIP_KEYS = new Set(['header', 'footer']);
    const coveredKeys = new Set(PAGES.map(p => p.contentKey));
    const allPages = [...PAGES];
    for (const key of Object.keys(partials)) {
        if (SKIP_KEYS.has(key) || coveredKeys.has(key)) continue;
        const slug = keyToSlug(key);
        console.log(`Auto-generating page for undeclared partial: ${key} -> ${slug}/index.html`);
        allPages.push({
            name: `${slug}/index.html`,
            pathPrefix: '../',
            homePathPrefix: '../',
            contentKey: key,
            title: `${slugToTitle(slug)} | Photos by Logan`,
            metaDescription: '',
        });
    }

    let galleryHTML = '';
    if (allPages.some(page => page.contentKey === 'gallery')) {
        const imageFiles = await getImageFiles(SRC_DIR.photos);
        console.log(`Found ${imageFiles.length} images.`);
        galleryHTML = generateGalleryHTML(imageFiles);
    }

    for (const page of allPages) {
        let pageSpecificContent = '';
        if (page.contentKey === 'gallery') {
            pageSpecificContent = galleryHTML;
        } else if (partials[page.contentKey]) {
            pageSpecificContent = partials[page.contentKey];
        } else {
            console.warn(`Partial for page ${page.name} (key: ${page.contentKey}) not found. Page might be incomplete.`);
        }

        let pageHtml = baseTemplateContent
            .replace(/<!-- PATH_PREFIX -->/g, page.pathPrefix)
            .replace('<!-- TITLE_PLACEHOLDER -->', page.title || 'Photos by Logan')
            .replace('<!-- META_DESCRIPTION_PLACEHOLDER -->', page.metaDescription ? `<meta name="description" content="${page.metaDescription}">` : '')
            .replace('<!-- HEADER_PLACEHOLDER -->', partials.header)
            .replace('<!-- FOOTER_PLACEHOLDER -->', partials.footer)
            .replace('<!-- CONTENT_PLACEHOLDER -->', pageSpecificContent)
            .replace('<!-- PAGE_SPECIFIC_SCRIPTS_PLACEHOLDER -->', page.scripts ? page.scripts.map(scriptPath => `<script src="${page.pathPrefix}${scriptPath}" defer></script>`).join('\n') : '');

        const urlMappings = {
            'HOME_URL': 'index.html',
            'FIRST_SHOOT_URL': 'first_shoot/index.html',
            'STANDARD_AGREEMENT_URL': 'standard_agreement/index.html',
            'ALBUMS_URL': 'albums/index.html',
            'BOOKING_URL': 'booking/index.html',
            'CONTACT_URL': 'contact/index.html',
        };

        for (const [placeholder, targetPath] of Object.entries(urlMappings)) {
            const relativePath = path.relative(path.dirname(page.name), path.dirname(targetPath));
            const finalPath = path.join(relativePath, path.basename(targetPath)).replace('index.html', '');
            pageHtml = pageHtml.replace(new RegExp(`<!-- ${placeholder} -->`, 'g'), finalPath);
        }

        const outputPath = path.join(BUILD_DIR, page.name);
        await writeFileContent(outputPath, pageHtml);
    }

    console.log('Copying assets...');
    await copyDirectoryRecursive(SRC_DIR.assets, ASSETS_BUILD_DIR);
    console.log('Assets copied.');

    console.log('Copying photos...');
    await copyDirectoryRecursive(SRC_DIR.photos, PHOTOS_BUILD_DIR);
    console.log('Photos copied.');

    const cnamePath = path.join(BUILD_DIR, 'CNAME');
    await writeFileContent(cnamePath, 'photosby.loganwu.co.nz');
    console.log('CNAME file created.');

    console.log('Build process completed successfully!');
}

// --- Run Build ---
buildSite().catch(err => {
    console.error('Unhandled error during build process:', err.message);
    process.exit(1);
});
