# Photos by Logan Wu

**Note:** The `index.html` file is automatically generated from `index.html.template`. Do not modify `index.html` directly; instead, edit `index.html.template` and run `build.js` to regenerate the `index.html` file.

This is the source code for my photography portfolio website, hosted on [photosby.loganwu.co.nz](https://photosby.loganwu.co.nz) via GitHub Pages. It showcases my work with pole dance and aerial arts studios, where I do event photography and run photoshoots. The site is lightweight, static, and easy to maintain.

---

## 🧭 Development Plan

__Phase 1: Basic Structure__

- [x] Set up repo and GitHub Pages configuration (This is assumed to be done)

- [x] Create folder structure: (Completed)

  ```javascript
  /
  ├── photos/
  ├── assets/
  │   ├── css/
  │   │   └── style.css
  │   └── js/
  │       └── script.js
  ├── partials/
  │   ├── contact_partial.html
  │   ├── first_shoot_partial.html
  │   ├── footer_partial.html
  │   └── header_partial.html
  │   └── standard_agreement_partial.html
  ├── package.json
  ├── README.md
  ├── base.html.template
  └── scripts/
      └── build.js
  ```

__Phase 2: Static Album Viewer__
- Adobe Portfolio style layout: Maximum of 3 images per row, new row only if previous row is full. Images retain original aspect ratio. All images in a row have equal heights. Width (and scaling factor) is determined by scaling the entire row to fill the page or content div width. Consistent margins/padding between photos.

- [ ] Albums are exported from Lightroom into `photos/`
- [ ] JavaScript scans folders and renders thumbnails + clicking an image should display it in fullscreen or full window
- [ ] Responsive grid layout for albums using CSS Grid or Flexbox

- [ ] Implement fullscreen or full window viewer

__Phase 3: Styling__

- [ ] Clean, minimal UI using CSS only (no frameworks)
- [ ] Font pairing and consistent color palette for a professional look
- [ ] Mobile-friendly and retina-optimized

__Phase 4: Hosting and Deployment__

- [x] Deploy via GitHub Pages
- [x] Use `photosby.loganwu.co.nz` as custom domain (via CNAME file)
- [ ] Push to `main` branch triggers deployment

Here's a more detailed plan with specific steps:

1. __Phase 2: Static Album Viewer__

   - __Implement JavaScript Logic:__ Write JavaScript code in `assets/js/script.js` to:

     - Scan the `photos` directory for image files (e.g., `.jpg`, `.jpeg`, `.png`).
     - Create thumbnail elements for each image.
     - Append the thumbnails to the `#album-viewer` div in `index.html`.

   (Not yet implemented)

   - __Implement Fullscreen Image Display:__ Add functionality to display the full-size image in fullscreen or full window when a thumbnail is clicked.

   - __Implement Responsive Grid Layout:__ Use CSS Grid or Flexbox in `assets/css/style.css` to create a responsive grid layout for the album thumbnails.

## 📸 Available Albums

- polefolio

2. __Phase 3: Styling__

   - __Choose Font Pairing:__ Select appropriate font pairings for headings and body text.

   - __Define Color Palette:__ Define a consistent color palette for the website.

   - __Implement CSS Styles:__ Add CSS styles to `assets/css/style.css` to:

     - Create a clean, minimal UI.
     - Apply the chosen font pairings and color palette.
     - Make the website mobile-friendly using media queries.
     - Optimize for retina displays.

3. __Phase 4: Hosting and Deployment__

   - __Set Up Custom Domain:__ Add a CNAME file to the repository with the custom domain `photosby.loganwu.co.nz`.
   - __Deploy Website:__ Push the code to the `gh-pages` branch to trigger deployment.

Here's the plan:

__Phase 1: Basic Structure__

- [x] Set up repo and GitHub Pages configuration (This is assumed to be done)
- [x] Create folder structure: (Completed)

__Phase 2: Static Album Viewer__

- [ ] Albums are exported from Lightroom into `photos/`
- [ ] JavaScript scans folders and renders thumbnails + clicking an image should display it in fullscreen or full window
- [ ] Responsive grid layout for albums using CSS Grid or Flexbox

__Phase 3: Styling__

- [ ] Clean, minimal UI using CSS only (no frameworks)
- [ ] Font pairing and consistent color palette for a professional look
- [ ] Mobile-friendly and retina-optimized

__Phase 4: Hosting and Deployment__

- [x] Deploy via GitHub Pages
- [x] Use `photosby.loganwu.co.nz` as custom domain (via CNAME file)
- [ ] Push to `main` branch triggers deployment

Here's a more detailed plan with specific steps:

1. __Phase 2: Static Album Viewer__

   - __Implement JavaScript Logic:__ Write JavaScript code in `assets/js/script.js` to:

     - Scan the `photos` directory for image files (e.g., `.jpg`, `.jpeg`, `.png`).
     - Create thumbnail elements for each image.
     - Append the thumbnails to the `#album-viewer` div in `index.html`.

   - __Implement Fullscreen Image Display:__ Add functionality to display the full-size image in fullscreen or full window when a thumbnail is clicked.

   - __Implement Responsive Grid Layout:__ Use CSS Grid or Flexbox in `assets/css/style.css` to create a responsive grid layout for the album thumbnails.

2. __Phase 3: Styling__

   - __Choose Font Pairing:__ Select appropriate font pairings for headings and body text.

   - __Define Color Palette:__ Define a consistent color palette for the website.

   - __Implement CSS Styles:__ Add CSS styles to `assets/css/style.css` to:

     - Create a clean, minimal UI.
     - Apply the chosen font pairings and color palette.
     - Make the website mobile-friendly using media queries.
     - Optimize for retina displays.

3. __Phase 4: Hosting and Deployment__

   - __Set Up Custom Domain:__ Add a CNAME file to the repository with the custom domain `photosby.loganwu.co.nz`.
   - __Deploy Website:__ Push the code to the `main` branch to trigger deployment.


---

## 🧰 Tech Stack

- HTML5
- CSS3
- Vanilla JavaScript
- image-size
- GitHub Pages (static hosting)

---

## 🧑‍💻 Developer Workflow

1.  Clone the repo:

    ```bash
    git clone https://github.com/loganbu/photography-portfolio.git
    cd photography-portfolio
    ```

2.  Install dependencies:

    ```bash
    npm install image-size
    ```

3.  Run the build script:

    ```bash
    node scripts/build.js
    ```

    This script will generate the `index.html`, `first_shoot.html`, and `standard_agreement.html` files based on the `base.html.template` file and the content in the `standard_agreement_partial.html` and `first_shoot_partial.html` files.

4.  Open the `index.html` file in your browser to view the website.

## 🚀 Deployment

To deploy the site to GitHub Pages manually, follow these steps:

1.  Build the site:

    ```bash
    node scripts/build.js
    ```

    This will generate the website files in the `docs` directory.

2.  Copy the contents of the `docs` directory to the root of your repository's `main` branch. You can do this by:

    *   Checking out the `main` branch:

        ```bash
        git checkout main
        ```

    *   Deleting all files in the `main` branch (except for this README, .git, .gitignore, base.html.template, build.js, package.json, partials/, photos/, and assets/):

        ```bash
        git rm -rf !(README.md|.git|.gitignore|base.html.template|build.js|package.json|partials|photos|assets)
        ```

    *   Copying the contents of the `docs` directory to the root of the `main` branch:

        ```bash
        cp -r docs/. .
        ```

    *   Adding the changes:

        ```bash
        git add .
        ```

    *   Committing the changes:

        ```bash
        git commit -m "Deploy to GitHub Pages"
        ```

    *   Pushing the changes to the `main` branch:

        ```bash
        git push origin main
        ```

3.  Your website will be deployed to GitHub Pages within a few minutes.
