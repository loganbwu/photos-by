# Photos by Logan Wu

A lightweight, static photography portfolio website showcasing pole dance and aerial arts event photography and photoshoots. Hosted on GitHub Pages, this site is designed for easy maintenance and efficient display of visual content.

## ✨ Features

*   **Dynamic Image Gallery:** Automatically generates image thumbnails and displays full-size images in a responsive grid.
*   **Lightbox Viewer:** Full-screen image viewing with navigation.
    *   Left/Right arrow key navigation (desktop).
    *   On-screen previous/next buttons (desktop & mobile).
    *   Swipe gestures for navigation (mobile).
*   **Responsive Design:** Optimized for various screen sizes, from mobile devices to large desktops.
*   **Minimal UI:** Clean and professional user interface built with pure CSS.
*   **Automated Build Process:** Uses a Node.js script to generate HTML files from templates and image directories.

## 🚀 Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

Ensure you have [Node.js](https://nodejs.org/) installed on your system.

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/loganbu/photography-portfolio.git
    cd photography-portfolio
    ```

2.  **Install dependencies:**
    ```bash
    npm install
    ```

### Usage

1.  **Build the website:**
    Run the build script to generate the static HTML files in the `docs/` directory.
    ```bash
    node scripts/build.js
    ```
    **Note:** The `index.html` and other content pages in `docs/` are automatically generated. Do not modify them directly. Instead, edit `base.html.template` or the partials in `partials/` and then run `node scripts/build.js` to regenerate.

2.  **View the website locally:**
    Open the generated `index.html` file in your web browser.
    ```bash
    open docs/index.html
    ```

## 🌐 Deployment

This site is deployed via GitHub Pages from the `docs/` directory of the `main` branch.

To deploy changes:
1.  Ensure all local changes are committed to your `main` branch.
2.  Run the build script: `node scripts/build.js`
3.  Push your `main` branch to GitHub. GitHub Pages will automatically deploy the content from the `docs/` directory.

## 🧰 Tech Stack

*   **Frontend:** HTML5, CSS3, Vanilla JavaScript
*   **Build Tooling:** Node.js (for `scripts/build.js`)
*   **Image Processing:** `image-size` npm package
*   **Hosting:** GitHub Pages

## 🤝 Contributing

Contributions are welcome! Please feel free to open an issue or submit a pull request.

## 📄 License

This project is licensed under the MIT License - see the `LICENSE` file for details (if applicable).

## 📞 Contact

For any inquiries, please refer to the contact information on the website.
