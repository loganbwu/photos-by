(function () {
    'use strict';

    var baseUrl = '';
    var allProofs = [];
    var currentProof = null;
    var baseImage = null;
    var overlayImages = [];
    var overlaySettings = [];
    var animFrameId = null;
    var lastTimestamp = null;
    var TRANSITION_MS = 250;
    var viewerLoadGen = 0;      // incremented per loadImages call; stale loads check against this
    var viewerLastFocused = null; // element to restore focus to when the viewer closes


    function initMultipleExposureViewer(proofs, galleryBaseUrl) {
        if (!proofs || proofs.length === 0) return;
        baseUrl = galleryBaseUrl;
        allProofs = proofs;
        renderExposuresSection(proofs);
        createModal();
    }

    function renderExposuresSection(proofs) {
        var existing = document.getElementById('exposures-section');
        if (existing) existing.remove();

        var section = document.createElement('div');
        section.id = 'exposures-section';

        var heading = document.createElement('h2');
        heading.textContent = 'Multiple Exposures';
        section.appendChild(heading);

        var p = document.createElement('p');
        p.className = 'gallery-instructions';
        p.textContent = 'Select a sequence to composite exposures in the browser. For the best experience, use a desktop browser.';
        section.appendChild(p);

        var cards = document.createElement('div');
        cards.className = 'exposure-cards';

        proofs.forEach(function (proof) {
            var card = document.createElement('div');
            card.className = 'exposure-card';
            card.setAttribute('role', 'button');
            card.setAttribute('tabindex', '0');
            card.setAttribute('aria-label', 'Open compositor for ' + proof.base);

            var thumb = proof.overlays.length > 0
                ? createCompositeThumbnail(proof)
                : createPlainThumbnail(proof);

            var info = document.createElement('div');
            info.className = 'exposure-card-info';

            var idLabel = document.createElement('span');
            idLabel.className = 'exposure-card-id';
            idLabel.textContent = proof.base;

            var countLabel = document.createElement('span');
            countLabel.className = 'exposure-card-count';
            countLabel.textContent = proof.overlays.length + ' overlay' + (proof.overlays.length !== 1 ? 's' : '');

            info.appendChild(idLabel);
            info.appendChild(countLabel);
            card.appendChild(thumb);
            card.appendChild(info);

            card.addEventListener('click', function () { openExposureViewer(proof); });
            card.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') openExposureViewer(proof);
            });

            cards.appendChild(card);
        });

        section.appendChild(cards);

        var albumViewer = document.getElementById('album-viewer');
        if (albumViewer && albumViewer.parentNode) {
            albumViewer.parentNode.insertBefore(section, albumViewer);
        }

        // Re-sync every rendered card's canvas resolution to its actual
        // displayed size whenever the layout changes (responsive breakpoints,
        // window resize) -- there's no zoom control here, just the viewport.
        window.addEventListener('resize', scheduleResizeAllCardCanvases);
        scheduleResizeAllCardCanvases();
    }

    function createPlainThumbnail(proof) {
        var img = document.createElement('img');
        img.src = baseUrl + proof.base;
        img.alt = proof.base;
        return img;
    }

    // ---------------------------------------------------------------------------
    // Card thumbnail compositing: static for <=1 (well, 0, since >0 always
    // reaches here) overlay is impossible -- every card that gets here has at
    // least 1 overlay, so it either pulses (n=1) or rotates (n>=2). Screen-
    // blends client-side, the same technique the modal viewer uses for live
    // overlay toggling, just applied once per card (or continuously, for the
    // rotate/pulse cases) instead of interactively.
    //
    // How many overlays are shown at once (n = total overlay count):
    //   n=1   -> 1, permanently, but pulsing 100%<->0% opacity (nothing to
    //            rotate in, so a static full-opacity overlay looked inert)
    //   n=2-3 -> n-1 (always one fewer than the total, rotating)
    //   n>=4  -> MAX_ACTIVE_OVERLAYS (3), rotating
    // ---------------------------------------------------------------------------
    var MAX_ACTIVE_OVERLAYS = 3;
    var CARD_ROTATION_MS = 3000;
    var CARD_MAX_FPS = 10;
    var CARD_REDRAW_INTERVAL_MS = 1000 / CARD_MAX_FPS;
    var lastCardDrawTime = 0;
    var cardAnimations = new Map();   // canvas -> rotation/pulse state, driven by tickCardAnimations

    // Only cards actually scrolled into view get redrawn each frame — an
    // off-screen card's animation state still advances (so it isn't stuck
    // showing a stale frame whenever it does scroll into view) but skips the
    // canvas compositing work, which is what actually costs frame rate.
    var visibleCanvases = new Set();
    var cardVisibilityObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (entry.isIntersecting) visibleCanvases.add(entry.target);
            else visibleCanvases.delete(entry.target);
        });
    }, { rootMargin: '200px' });

    function stopCardAnimation(canvas) {
        if (cardAnimations.delete(canvas)) {
            cardVisibilityObserver.unobserve(canvas);
            visibleCanvases.delete(canvas);
        }
    }

    function activeOverlayCount(n) {
        if (n === 0) return 0;
        return Math.max(1, Math.min(n - 1, MAX_ACTIVE_OVERLAYS));
    }

    function createCompositeThumbnail(proof) {
        var canvas = document.createElement('canvas');
        canvas.className = 'exposure-card-thumb-canvas';
        canvas.setAttribute('aria-hidden', 'true');

        var srcs = [proof.base].concat(proof.overlays);
        var imgs = srcs.map(function () { return new Image(); });
        var loaded = 0;

        function allLoaded() {
            var base = imgs[0];
            if (!base.complete || !base.naturalWidth) return;
            canvas._imgs = imgs;

            if (proof.overlays.length === 1) {
                startCardPulse(canvas, imgs);
            } else {
                var activeCount = activeOverlayCount(proof.overlays.length);
                if (activeCount > 0 && activeCount < proof.overlays.length) {
                    startCardRotation(canvas, imgs, activeCount);
                }
            }
            resizeCardCanvas(canvas);   // sets canvas.width/height to the card's actual displayed size and paints it
        }

        imgs.forEach(function (img, idx) {
            img.onload = function () { loaded++; if (loaded === srcs.length) allLoaded(); };
            img.onerror = function () { loaded++; if (loaded === srcs.length) allLoaded(); };
            img.src = baseUrl + srcs[idx];
        });

        return canvas;
    }

    // Renders at the canvas's actual displayed CSS size (scaled by devicePixelRatio
    // for sharpness), not the source image's resolution — thumbnails are shown
    // small, and rotation redraws every layer every frame, so matching display
    // size keeps that redraw cheap. Canvas width/height writes clear the drawing
    // buffer, so this always repaints immediately after resizing.
    var CARD_CANVAS_MAX_PX = 1600;   // no point rendering the canvas larger than this

    function resizeCardCanvas(canvas) {
        var imgs = canvas._imgs;
        if (!imgs) return;
        var base = imgs[0];
        if (!base.complete || !base.naturalWidth) return;
        var displayWidth = canvas.clientWidth || (canvas.parentElement && canvas.parentElement.clientWidth) || 0;
        if (!displayWidth) return;
        var dpr = window.devicePixelRatio || 1;
        var targetWidth = Math.max(1, Math.round(displayWidth * dpr));
        var targetHeight = Math.max(1, Math.round(targetWidth * base.naturalHeight / base.naturalWidth));
        var overCap = Math.max(targetWidth, targetHeight) / CARD_CANVAS_MAX_PX;
        if (overCap > 1) {
            targetWidth = Math.max(1, Math.round(targetWidth / overCap));
            targetHeight = Math.max(1, Math.round(targetHeight / overCap));
        }
        if (canvas.width === targetWidth && canvas.height === targetHeight) return;
        canvas.width = targetWidth;
        canvas.height = targetHeight;

        var state = cardAnimations.get(canvas);
        if (state && state.kind === 'pulse') {
            var elapsed = state.startTime === null ? 0 : performance.now() - state.startTime;
            drawPulsingCard(canvas, state, elapsed);
        } else if (state) {
            var progress = 0;
            if (state.transition && state.transition.startTime !== null) {
                progress = Math.min(1, (performance.now() - state.transition.startTime) / CARD_ROTATION_MS);
            }
            drawRotatingCard(canvas, state, progress);
        } else {
            drawStaticComposite(canvas, imgs);
        }
    }

    var resizeAllRaf = null;
    function scheduleResizeAllCardCanvases() {
        if (resizeAllRaf !== null) return;
        resizeAllRaf = requestAnimationFrame(function () {
            resizeAllRaf = null;
            document.querySelectorAll('.exposure-card-thumb-canvas').forEach(resizeCardCanvas);
        });
    }

    function drawStaticComposite(canvas, imgs) {
        var ctx = canvas.getContext('2d');
        ctx.globalCompositeOperation = 'source-over';
        ctx.drawImage(imgs[0], 0, 0, canvas.width, canvas.height);
        for (var i = 1; i < imgs.length; i++) {
            if (!imgs[i].complete || !imgs[i].naturalWidth) continue;
            ctx.globalCompositeOperation = 'screen';
            ctx.drawImage(imgs[i], 0, 0, canvas.width, canvas.height);
        }
        ctx.globalCompositeOperation = 'source-over';
    }

    // Consumed once, the first time an animation's startTime is set from null
    // (see tickCardAnimations) -- backdates that start so cards don't all
    // begin their cycles in lockstep. Zeroed after use so it only ever offsets
    // a card's very first cycle, not every one after it.
    function takeInitialOffset(state) {
        var offset = state.initialOffsetMs || 0;
        state.initialOffsetMs = 0;
        return offset;
    }

    // imgs[0] is the base; imgs[1..] correspond 1:1 with the proof's overlays.
    function startCardRotation(canvas, imgs, activeCount) {
        var activeIndices = [];
        for (var i = 1; i < Math.min(imgs.length, 1 + activeCount); i++) activeIndices.push(i);
        var state = {
            kind: 'rotate', imgs: imgs, activeIndices: activeIndices, transition: null,
            initialOffsetMs: Math.random() * CARD_ROTATION_MS,
        };
        beginNextCardTransition(state);
        cardAnimations.set(canvas, state);
        cardVisibilityObserver.observe(canvas);
    }

    // A single overlay never has anything to rotate in, so instead of sitting
    // at a static 100% (which reads as inert), it continuously breathes between
    // 100% and 0% opacity to signal there's a composited layer at all.
    var PULSE_PERIOD_MS = 10000;   // one full 100%->0%->100% cycle: 5s down, 5s back up
    var PULSE_MIN_ALPHA = 0;

    function startCardPulse(canvas, imgs) {
        var state = { kind: 'pulse', imgs: imgs, startTime: null, initialOffsetMs: Math.random() * PULSE_PERIOD_MS };
        cardAnimations.set(canvas, state);
        cardVisibilityObserver.observe(canvas);
    }

    function drawPulsingCard(canvas, state, elapsed) {
        var phase = (elapsed % PULSE_PERIOD_MS) / PULSE_PERIOD_MS;   // 0..1 over one full cycle
        var mid = (1 + PULSE_MIN_ALPHA) / 2;
        var amp = (1 - PULSE_MIN_ALPHA) / 2;
        var alpha = mid + amp * Math.cos(phase * 2 * Math.PI);       // 1 -> PULSE_MIN_ALPHA -> 1

        var ctx = canvas.getContext('2d');
        ctx.globalCompositeOperation = 'source-over';
        ctx.drawImage(state.imgs[0], 0, 0, canvas.width, canvas.height);
        var overlay = state.imgs[1];
        if (overlay.complete && overlay.naturalWidth) {
            ctx.globalCompositeOperation = 'screen';
            ctx.globalAlpha = alpha;
            ctx.drawImage(overlay, 0, 0, canvas.width, canvas.height);
        }
        ctx.globalAlpha = 1;
        ctx.globalCompositeOperation = 'source-over';
    }

    function beginNextCardTransition(state) {
        var pool = [];
        for (var i = 1; i < state.imgs.length; i++) {
            if (state.activeIndices.indexOf(i) === -1) pool.push(i);
        }
        if (pool.length === 0) { state.transition = null; return; }
        state.transition = {
            outIdx: state.activeIndices[0],                        // oldest active overlay retires
            inIdx: pool[Math.floor(Math.random() * pool.length)],   // random replacement
            startTime: null,
        };
        state.steadyCanvas = null;   // active set just changed -- invalidate the cached steady layer
    }

    // The active overlays other than the one currently fading out don't change
    // for the whole duration of a transition, so they're composited once into
    // an offscreen canvas and reused every redraw, instead of re-compositing
    // all of them from scratch on every frame.
    function rebuildSteadyLayer(canvas, state) {
        var sc = state.steadyCanvas || document.createElement('canvas');
        sc.width = canvas.width;
        sc.height = canvas.height;
        var sctx = sc.getContext('2d');
        sctx.globalCompositeOperation = 'source-over';
        sctx.drawImage(state.imgs[0], 0, 0, sc.width, sc.height);
        sctx.globalCompositeOperation = 'screen';
        state.activeIndices.forEach(function (idx) {
            if (idx === state.transition.outIdx) return;   // drawn separately each frame with its fading alpha
            var img = state.imgs[idx];
            if (img.complete && img.naturalWidth) sctx.drawImage(img, 0, 0, sc.width, sc.height);
        });
        sctx.globalCompositeOperation = 'source-over';
        state.steadyCanvas = sc;
    }

    function drawRotatingCard(canvas, state, progress) {
        if (!state.steadyCanvas || state.steadyCanvas.width !== canvas.width || state.steadyCanvas.height !== canvas.height) {
            rebuildSteadyLayer(canvas, state);
        }
        var ctx = canvas.getContext('2d');
        var t = state.transition;
        ctx.globalCompositeOperation = 'source-over';
        ctx.drawImage(state.steadyCanvas, 0, 0);
        ctx.globalCompositeOperation = 'screen';
        var outImg = state.imgs[t.outIdx];
        if (outImg.complete && outImg.naturalWidth) {
            ctx.globalAlpha = 1 - progress;
            ctx.drawImage(outImg, 0, 0, canvas.width, canvas.height);
        }
        var inImg = state.imgs[t.inIdx];
        if (inImg.complete && inImg.naturalWidth) {
            ctx.globalAlpha = progress;
            ctx.drawImage(inImg, 0, 0, canvas.width, canvas.height);
        }
        ctx.globalAlpha = 1;
        ctx.globalCompositeOperation = 'source-over';
    }

    function tickCardAnimations(timestamp) {
        // Pause entirely (not just the draw) while the tab/window isn't visible.
        // A transition's startTime is a real timestamp, so skipping ticks here
        // doesn't desync anything -- progress just picks up from wherever real
        // wall-clock time says it should be once the tab is visible again.
        if (document.hidden) {
            requestAnimationFrame(tickCardAnimations);
            return;
        }

        // Transition timing/state always advances every frame (cheap); the actual
        // canvas redraw is throttled to CARD_MAX_FPS, since a 3s crossfade doesn't
        // need 60fps smoothness and this is the expensive part per visible card.
        var shouldDraw = (timestamp - lastCardDrawTime) >= CARD_REDRAW_INTERVAL_MS;
        if (shouldDraw) lastCardDrawTime = timestamp;

        cardAnimations.forEach(function (state, canvas) {
            if (!canvas.isConnected) { stopCardAnimation(canvas); return; }

            if (state.kind === 'pulse') {
                if (state.startTime === null) state.startTime = timestamp - takeInitialOffset(state);
                if (shouldDraw && visibleCanvases.has(canvas)) drawPulsingCard(canvas, state, timestamp - state.startTime);
                return;
            }

            if (!state.transition) return;
            if (state.transition.startTime === null) state.transition.startTime = timestamp - takeInitialOffset(state);
            var progress = Math.min(1, (timestamp - state.transition.startTime) / CARD_ROTATION_MS);
            if (shouldDraw && visibleCanvases.has(canvas)) drawRotatingCard(canvas, state, progress);
            if (progress >= 1) {
                var doneIdx = state.activeIndices.indexOf(state.transition.outIdx);
                if (doneIdx !== -1) state.activeIndices.splice(doneIdx, 1);
                state.activeIndices.push(state.transition.inIdx);
                beginNextCardTransition(state);
            }
        });
        requestAnimationFrame(tickCardAnimations);
    }
    requestAnimationFrame(tickCardAnimations);

    function createModal() {
        if (document.getElementById('multiple-exposure-viewer-modal')) return;

        var modal = document.createElement('div');
        modal.id = 'multiple-exposure-viewer-modal';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-label', 'Multiple exposure viewer');

        modal.innerHTML =
            '<div class="multiple-exposure-viewer-content">' +
                '<div class="multiple-exposure-viewer-canvas-wrap">' +
                    '<canvas id="exposure-canvas"></canvas>' +
                '</div>' +
                '<div class="multiple-exposure-viewer-controls">' +
                    '<div class="multiple-exposure-viewer-header">' +
                        '<h2 id="multiple-exposure-viewer-title">Multiple Exposure</h2>' +
                        '<button class="multiple-exposure-viewer-close" id="multiple-exposure-viewer-close" aria-label="Close viewer"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg><span class="multiple-exposure-viewer-close-label">Exit</span></button>' +
                    '</div>' +
                    '<p class="exposure-instructions">Click an overlay to enable it and combine exposures. Experiment with different combinations to find your favourite composite.</p>' +
                    '<p class="exposure-instructions">Note: this is an indicative preview only. The base image and overlays will be refined in post-processing for the final edit.</p>' +
                    '<div id="exposure-overlays-list" class="exposure-overlays-list"></div>' +
                '</div>' +
            '</div>';

        document.body.appendChild(modal);

        document.getElementById('multiple-exposure-viewer-close').addEventListener('click', closeModal);
        modal.addEventListener('click', function (e) { if (e.target === modal) closeModal(); });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') { closeModal(); return; }
            if (!currentProof) return;
            if (e.key === 'ArrowLeft')  { e.preventDefault(); navigateProof(-1); }
            if (e.key === 'ArrowRight') { e.preventDefault(); navigateProof(1); }
        });
    }

    function openExposureViewer(proof) {
        if (!currentProof) {
            viewerLastFocused = document.activeElement;
        }
        currentProof = proof;
        overlayImages = [];
        overlaySettings = proof.overlays.map(function () { return { enabled: false, currentAlpha: 0, targetAlpha: 0 }; });

        document.getElementById('multiple-exposure-viewer-title').textContent = proof.base;

        var modal = document.getElementById('multiple-exposure-viewer-modal');
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';

        renderOverlayControls(proof);
        loadImages(proof);
        // Deferred: moving focus synchronously here (e.g. while still inside the
        // keydown handler for Enter/Space on the triggering card) can cause the
        // browser's native "Enter activates the focused button" behaviour to
        // immediately fire on the close button, closing the viewer it just opened.
        setTimeout(function () {
            document.getElementById('multiple-exposure-viewer-close').focus();
        }, 0);
    }

    function renderOverlayControls(proof) {
        var list = document.getElementById('exposure-overlays-list');
        list.innerHTML = '';

        var baseLabel = document.createElement('p');
        baseLabel.className = 'exposure-control-label';
        baseLabel.textContent = 'Base';
        list.appendChild(baseLabel);

        var baseName = document.createElement('p');
        baseName.className = 'exposure-base-name';
        baseName.textContent = proof.base;
        list.appendChild(baseName);

        if (proof.overlays.length === 0) {
            return;
        }

        var overlayLabelRow = document.createElement('div');
        overlayLabelRow.className = 'exposure-overlay-label-row';

        var overlayLabel = document.createElement('p');
        overlayLabel.className = 'exposure-control-label';
        overlayLabel.textContent = 'Overlays';

        var selectAllBtn = document.createElement('button');
        selectAllBtn.className = 'exposure-select-all-btn';
        selectAllBtn.textContent = 'Select all';

        overlayLabelRow.appendChild(overlayLabel);
        overlayLabelRow.appendChild(selectAllBtn);
        list.appendChild(overlayLabelRow);

        var overlayBtns = [];

        proof.overlays.forEach(function (name, i) {
            var btn = document.createElement('button');
            btn.className = 'exposure-overlay-btn';
            btn.setAttribute('aria-pressed', 'false');
            btn.textContent = name;
            btn.title = name;
            overlayBtns.push(btn);
            (function (idx) {
                btn.addEventListener('click', function () {
                    overlaySettings[idx].enabled = !overlaySettings[idx].enabled;
                    btn.classList.toggle('active', overlaySettings[idx].enabled);
                    btn.setAttribute('aria-pressed', String(overlaySettings[idx].enabled));
                    updateSelectAllBtn(selectAllBtn);
                    setTargetAlpha(idx);
                });
            }(i));
            list.appendChild(btn);
        });

        selectAllBtn.addEventListener('click', function () {
            var allEnabled = overlaySettings.every(function (s) { return s.enabled; });
            var enable = !allEnabled;
            overlaySettings.forEach(function (s, idx) {
                s.enabled = enable;
                overlayBtns[idx].classList.toggle('active', enable);
                overlayBtns[idx].setAttribute('aria-pressed', String(enable));
                setTargetAlpha(idx);
            });
            updateSelectAllBtn(selectAllBtn);
        });

        updateSelectAllBtn(selectAllBtn);
    }

    function updateSelectAllBtn(btn) {
        var allEnabled = overlaySettings.every(function (s) { return s.enabled; });
        btn.textContent = allEnabled ? 'Deselect all' : 'Select all';
    }

    function loadImages(proof) {
        var myGen = ++viewerLoadGen;
        var canvas = document.getElementById('exposure-canvas');
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
            function onLoad() {
                if (myGen !== viewerLoadGen) return;   // a newer proof has since been opened; discard
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
            }
            img.onload = onLoad;
            img.onerror = onLoad;
            img.src = baseUrl + allSrcs[idx];
        });
    }

    function setTargetAlpha(idx) {
        var s = overlaySettings[idx];
        s.targetAlpha = s.enabled ? 1.0 : 0.0;
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

        var canvas = document.getElementById('exposure-canvas');
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

    function navigateProof(delta) {
        var idx = allProofs.findIndex(function (p) { return p.id === currentProof.id; });
        if (idx === -1) return;
        var newIdx = idx + delta;
        if (newIdx < 0 || newIdx >= allProofs.length) return;
        openExposureViewer(allProofs[newIdx]);
    }

    function closeModal() {
        var modal = document.getElementById('multiple-exposure-viewer-modal');
        if (modal) modal.style.display = 'none';
        document.body.style.overflow = '';
        viewerLoadGen++;   // discard any in-flight image loads from the closed proof
        currentProof = null;
        baseImage = null;
        overlayImages = [];
        if (viewerLastFocused && typeof viewerLastFocused.focus === 'function') {
            viewerLastFocused.focus();
        }
        viewerLastFocused = null;
    }

    window.initMultipleExposureViewer = initMultipleExposureViewer;
}());
