(function () {
    'use strict';

    var baseUrl = '';
    var currentProof = null;
    var baseImage = null;
    var overlayImages = [];
    var overlaySettings = [];

    var BLEND_MODES = [
        'screen', 'multiply', 'overlay', 'lighten', 'darken',
        'color-dodge', 'color-burn', 'hard-light', 'soft-light',
        'difference', 'exclusion'
    ];

    function initProofViewer(proofs, galleryBaseUrl) {
        if (!proofs || proofs.length === 0) return;
        baseUrl = galleryBaseUrl;
        renderProofsSection(proofs);
        createModal();
    }

    function renderProofsSection(proofs) {
        var existing = document.getElementById('proofs-section');
        if (existing) existing.remove();

        var section = document.createElement('div');
        section.id = 'proofs-section';

        var heading = document.createElement('h2');
        heading.textContent = 'Composite Proofs';
        section.appendChild(heading);

        var p = document.createElement('p');
        p.className = 'gallery-instructions';
        p.textContent = 'Select a sequence to composite exposures in the browser.';
        section.appendChild(p);

        var cards = document.createElement('div');
        cards.className = 'proof-cards';

        proofs.forEach(function (proof) {
            var card = document.createElement('div');
            card.className = 'proof-card';
            card.setAttribute('role', 'button');
            card.setAttribute('tabindex', '0');
            card.setAttribute('aria-label', 'Open compositor for ' + proof.id);

            var img = document.createElement('img');
            img.src = baseUrl + proof.base;
            img.alt = proof.id;
            img.crossOrigin = 'anonymous';

            var info = document.createElement('div');
            info.className = 'proof-card-info';

            var idLabel = document.createElement('span');
            idLabel.className = 'proof-card-id';
            idLabel.textContent = proof.id.replace(/_/g, ' ');

            var countLabel = document.createElement('span');
            countLabel.className = 'proof-card-count';
            countLabel.textContent = proof.overlays.length + ' overlay' + (proof.overlays.length !== 1 ? 's' : '');

            info.appendChild(idLabel);
            info.appendChild(countLabel);
            card.appendChild(img);
            card.appendChild(info);

            card.addEventListener('click', function () { openProofViewer(proof); });
            card.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') openProofViewer(proof);
            });

            cards.appendChild(card);
        });

        section.appendChild(cards);

        var galleryContainer = document.getElementById('image-gallery-container');
        if (galleryContainer && galleryContainer.parentNode) {
            galleryContainer.parentNode.insertBefore(section, galleryContainer.nextSibling);
        }
    }

    function createModal() {
        if (document.getElementById('proof-viewer-modal')) return;

        var modal = document.createElement('div');
        modal.id = 'proof-viewer-modal';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-label', 'Composite proof viewer');

        var blendOptions = BLEND_MODES.map(function (m) {
            return '<option value="' + m + '"' + (m === 'screen' ? ' selected' : '') + '>' + m + '</option>';
        }).join('');

        modal.innerHTML =
            '<div class="proof-viewer-content">' +
                '<div class="proof-viewer-canvas-wrap">' +
                    '<canvas id="proof-canvas"></canvas>' +
                    '<p class="proof-cors-note" id="proof-cors-note" style="display:none;">' +
                        'Download unavailable: the storage bucket needs CORS headers configured.' +
                    '</p>' +
                '</div>' +
                '<div class="proof-viewer-controls">' +
                    '<div class="proof-viewer-header">' +
                        '<h2 id="proof-viewer-title">Composite Proof</h2>' +
                        '<button class="proof-viewer-close" id="proof-viewer-close" aria-label="Close viewer">&times;</button>' +
                    '</div>' +
                    '<label class="proof-control-label" for="proof-blend-mode">Blend mode</label>' +
                    '<select id="proof-blend-mode" class="proof-select">' + blendOptions + '</select>' +
                    '<div id="proof-overlays-list" class="proof-overlays-list"></div>' +
                    '<button id="proof-download-btn" class="proof-download-btn">Download PNG</button>' +
                '</div>' +
            '</div>';

        document.body.appendChild(modal);

        document.getElementById('proof-viewer-close').addEventListener('click', closeModal);
        modal.addEventListener('click', function (e) { if (e.target === modal) closeModal(); });
        document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeModal(); });
        document.getElementById('proof-blend-mode').addEventListener('change', redraw);
        document.getElementById('proof-download-btn').addEventListener('click', downloadCanvas);
    }

    function openProofViewer(proof) {
        currentProof = proof;
        overlayImages = [];
        overlaySettings = proof.overlays.map(function () { return { enabled: true, opacity: 1.0 }; });

        document.getElementById('proof-viewer-title').textContent = proof.id.replace(/_/g, ' ');
        document.getElementById('proof-cors-note').style.display = 'none';
        document.getElementById('proof-blend-mode').value = 'screen';

        var modal = document.getElementById('proof-viewer-modal');
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';

        renderOverlayControls(proof);
        loadImages(proof);
    }

    function renderOverlayControls(proof) {
        var list = document.getElementById('proof-overlays-list');
        list.innerHTML = '';

        if (proof.overlays.length === 0) {
            var empty = document.createElement('p');
            empty.style.color = 'var(--grey)';
            empty.textContent = 'No overlays in this sequence.';
            list.appendChild(empty);
            return;
        }

        var heading = document.createElement('p');
        heading.className = 'proof-control-label';
        heading.textContent = 'Overlays';
        list.appendChild(heading);

        proof.overlays.forEach(function (name, i) {
            var row = document.createElement('div');
            row.className = 'proof-overlay-row';

            var checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = 'overlay-toggle-' + i;
            checkbox.checked = true;
            (function (idx) {
                checkbox.addEventListener('change', function () {
                    overlaySettings[idx].enabled = checkbox.checked;
                    redraw();
                });
            }(i));

            var label = document.createElement('label');
            label.htmlFor = 'overlay-toggle-' + i;
            label.className = 'proof-overlay-label';
            label.textContent = name;
            label.title = name;

            var slider = document.createElement('input');
            slider.type = 'range';
            slider.min = '0';
            slider.max = '1';
            slider.step = '0.05';
            slider.value = '1';
            slider.className = 'proof-opacity-slider';
            slider.setAttribute('aria-label', 'Opacity for ' + name);
            (function (idx) {
                slider.addEventListener('input', function () {
                    overlaySettings[idx].opacity = parseFloat(slider.value);
                    redraw();
                });
            }(i));

            row.appendChild(checkbox);
            row.appendChild(label);
            row.appendChild(slider);
            list.appendChild(row);
        });
    }

    function loadImages(proof) {
        var canvas = document.getElementById('proof-canvas');
        var ctx = canvas.getContext('2d');

        canvas.width = canvas.width || 400;
        canvas.height = canvas.height || 300;
        ctx.fillStyle = '#1a1a1a';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#888';
        ctx.font = '14px Helvetica';
        ctx.textAlign = 'center';
        ctx.fillText('Loading...', canvas.width / 2, canvas.height / 2);

        var allSrcs = [proof.base].concat(proof.overlays);
        var imgs = allSrcs.map(function () { return new Image(); });
        var loaded = 0;

        imgs.forEach(function (img, idx) {
            img.crossOrigin = 'anonymous';
            img.onload = function () {
                loaded++;
                if (idx === 0) {
                    canvas.width = img.naturalWidth;
                    canvas.height = img.naturalHeight;
                }
                if (loaded === allSrcs.length) {
                    baseImage = imgs[0];
                    overlayImages = imgs.slice(1);
                    redraw();
                }
            };
            img.onerror = function () {
                loaded++;
                if (loaded === allSrcs.length) {
                    baseImage = imgs[0];
                    overlayImages = imgs.slice(1);
                    redraw();
                }
            };
            img.src = baseUrl + allSrcs[idx];
        });
    }

    function redraw() {
        if (!baseImage || !baseImage.complete) return;

        var canvas = document.getElementById('proof-canvas');
        var ctx = canvas.getContext('2d');
        var blendMode = document.getElementById('proof-blend-mode').value;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        ctx.globalAlpha = 1.0;
        ctx.globalCompositeOperation = 'source-over';
        ctx.drawImage(baseImage, 0, 0, canvas.width, canvas.height);

        overlaySettings.forEach(function (settings, i) {
            if (!settings.enabled) return;
            if (!overlayImages[i] || !overlayImages[i].complete) return;
            ctx.globalAlpha = settings.opacity;
            ctx.globalCompositeOperation = blendMode;
            ctx.drawImage(overlayImages[i], 0, 0, canvas.width, canvas.height);
        });

        ctx.globalAlpha = 1.0;
        ctx.globalCompositeOperation = 'source-over';
    }

    function downloadCanvas() {
        var canvas = document.getElementById('proof-canvas');
        try {
            var dataUrl = canvas.toDataURL('image/png');
            var a = document.createElement('a');
            a.href = dataUrl;
            a.download = (currentProof ? currentProof.id : 'proof') + '.png';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        } catch (e) {
            console.error('Canvas export failed (likely CORS):', e);
            document.getElementById('proof-cors-note').style.display = 'block';
        }
    }

    function closeModal() {
        var modal = document.getElementById('proof-viewer-modal');
        if (modal) modal.style.display = 'none';
        document.body.style.overflow = '';
        currentProof = null;
        baseImage = null;
        overlayImages = [];
    }

    window.initProofViewer = initProofViewer;
}());
