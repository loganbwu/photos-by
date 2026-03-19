(function () {
    'use strict';

    var baseUrl = '';
    var currentProof = null;
    var baseImage = null;
    var overlayImages = [];
    var overlaySettings = [];
    var animFrameId = null;
    var lastTimestamp = null;
    var TRANSITION_MS = 250;


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
        p.textContent = 'Select a sequence to composite exposures in the browser. For the best experience, use a desktop browser.';
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

        var albumViewer = document.getElementById('album-viewer');
        if (albumViewer && albumViewer.parentNode) {
            albumViewer.parentNode.insertBefore(section, albumViewer.nextSibling);
        }
    }

    function createModal() {
        if (document.getElementById('proof-viewer-modal')) return;

        var modal = document.createElement('div');
        modal.id = 'proof-viewer-modal';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-label', 'Composite proof viewer');

        modal.innerHTML =
            '<div class="proof-viewer-content">' +
                '<div class="proof-viewer-canvas-wrap">' +
                    '<canvas id="proof-canvas"></canvas>' +
                '</div>' +
                '<div class="proof-viewer-controls">' +
                    '<div class="proof-viewer-header">' +
                        '<h2 id="proof-viewer-title">Composite Proof</h2>' +
                        '<button class="proof-viewer-close" id="proof-viewer-close" aria-label="Close viewer"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg> Exit</button>' +
                    '</div>' +
                    '<p class="proof-instructions">Hover over an overlay to preview it, or click to keep it enabled. Experiment with different combinations to find your favourite composite.</p>' +
                    '<p class="proof-instructions">Note: this is an indicative preview only. The base image and overlays will be refined in post-processing for the final edit.</p>' +
                    '<div id="proof-overlays-list" class="proof-overlays-list"></div>' +
                '</div>' +
            '</div>';

        document.body.appendChild(modal);

        document.getElementById('proof-viewer-close').addEventListener('click', closeModal);
        modal.addEventListener('click', function (e) { if (e.target === modal) closeModal(); });
        document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeModal(); });
    }

    function openProofViewer(proof) {
        currentProof = proof;
        overlayImages = [];
        overlaySettings = proof.overlays.map(function () { return { enabled: false, hovering: false, currentAlpha: 0, targetAlpha: 0 }; });

        document.getElementById('proof-viewer-title').textContent = proof.id.replace(/_/g, ' ');

        var modal = document.getElementById('proof-viewer-modal');
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';

        renderOverlayControls(proof);
        loadImages(proof);
    }

    function renderOverlayControls(proof) {
        var list = document.getElementById('proof-overlays-list');
        list.innerHTML = '';

        var baseLabel = document.createElement('p');
        baseLabel.className = 'proof-control-label';
        baseLabel.textContent = 'Base';
        list.appendChild(baseLabel);

        var baseName = document.createElement('p');
        baseName.className = 'proof-base-name';
        baseName.textContent = proof.base;
        list.appendChild(baseName);

        if (proof.overlays.length === 0) {
            return;
        }

        var overlayLabel = document.createElement('p');
        overlayLabel.className = 'proof-control-label';
        overlayLabel.textContent = 'Overlays';
        list.appendChild(overlayLabel);

        proof.overlays.forEach(function (name, i) {
            var btn = document.createElement('button');
            btn.className = 'proof-overlay-btn';
            btn.textContent = name;
            btn.title = name;
            (function (idx) {
                btn.addEventListener('pointerenter', function () {
                    if (window.matchMedia('(hover: none)').matches) return;
                    overlaySettings[idx].hovering = true;
                    setTargetAlpha(idx);
                });
                btn.addEventListener('pointerleave', function () {
                    if (window.matchMedia('(hover: none)').matches) return;
                    overlaySettings[idx].hovering = false;
                    setTargetAlpha(idx);
                });
                btn.addEventListener('click', function () {
                    overlaySettings[idx].enabled = !overlaySettings[idx].enabled;
                    btn.classList.toggle('active', overlaySettings[idx].enabled);
                    setTargetAlpha(idx);
                });
            }(i));
            list.appendChild(btn);
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

    function setTargetAlpha(idx) {
        overlaySettings[idx].targetAlpha = (overlaySettings[idx].enabled || overlaySettings[idx].hovering) ? 1.0 : 0.0;
        if (animFrameId !== null) cancelAnimationFrame(animFrameId);
        lastTimestamp = null;
        animFrameId = requestAnimationFrame(animationStep);
    }

    function animationStep(timestamp) {
        var dt = lastTimestamp ? timestamp - lastTimestamp : 16;
        lastTimestamp = timestamp;

        var stillAnimating = false;
        overlaySettings.forEach(function (settings) {
            var diff = settings.targetAlpha - settings.currentAlpha;
            if (Math.abs(diff) > 0.001) {
                settings.currentAlpha += (diff > 0 ? 1 : -1) * dt / TRANSITION_MS;
                settings.currentAlpha = Math.max(0, Math.min(1, settings.currentAlpha));
                stillAnimating = true;
            } else {
                settings.currentAlpha = settings.targetAlpha;
            }
        });

        redraw();

        if (stillAnimating) {
            animFrameId = requestAnimationFrame(animationStep);
        } else {
            animFrameId = null;
            lastTimestamp = null;
        }
    }

    function redraw() {
        if (!baseImage || !baseImage.complete) return;

        var canvas = document.getElementById('proof-canvas');
        var ctx = canvas.getContext('2d');
        var blendMode = 'screen';

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        ctx.globalAlpha = 1.0;
        ctx.globalCompositeOperation = 'source-over';
        ctx.drawImage(baseImage, 0, 0, canvas.width, canvas.height);

        overlaySettings.forEach(function (settings, i) {
            if (settings.currentAlpha <= 0) return;
            if (!overlayImages[i] || !overlayImages[i].complete) return;
            ctx.globalAlpha = settings.currentAlpha;
            ctx.globalCompositeOperation = blendMode;
            ctx.drawImage(overlayImages[i], 0, 0, canvas.width, canvas.height);
        });

        ctx.globalAlpha = 1.0;
        ctx.globalCompositeOperation = 'source-over';
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
