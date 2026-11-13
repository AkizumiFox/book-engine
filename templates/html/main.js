/**
 * Book pages: navigation, search palette, reference previews, folds, tabs, progress.
 * Direction B ("modern documentation"). No third-party script: previews and the palette
 * are drawn here, so their motion can start from where the reader acted.
 */

(function () {
    'use strict';

    const root = document.documentElement;
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const DRAWER_QUERY = window.matchMedia('(max-width: 900px)');

    // ==========================================================================
    // Small helpers
    // ==========================================================================

    function getBasePath() {
        const meta = document.querySelector('meta[name="asset-prefix"]');
        return meta ? meta.content : './';
    }

    function assetVersion() {
        const meta = document.querySelector('meta[name="asset-version"]');
        return meta ? meta.content : '';
    }

    /** A site-wide data file, versioned like styles.css so the browser may cache it. */
    function fetchData(name) {
        const version = assetVersion();
        return fetch(getBasePath() + name + (version ? `?v=${encodeURIComponent(version)}` : ''));
    }

    function currentPagePath() {
        return document.querySelector('meta[name="page-path"]')?.content || '';
    }

    function bookKey() {
        return document.querySelector('meta[name="book-title"]')?.content || getBasePath();
    }

    function escapeHtml(text) {
        return String(text).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    function readJson(key, fallback) {
        try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (e) { return fallback; }
    }

    /** Write to localStorage; false when the browser refuses (private mode, quota). */
    function writeJson(key, value) {
        try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch (e) { return false; }
    }

    function saveSetting(key, value) {
        try {
            if (value === null) localStorage.removeItem(key);
            else localStorage.setItem(key, value);
        } catch (e) { /* private mode: the setting lasts for this page only */ }
    }

    function setButtonLabel(button, label) {
        button.setAttribute('aria-label', label);
        if (button.dataset.tooltip !== undefined) button.dataset.tooltip = label;
    }

    let toastTimer;
    function toast(message) {
        const el = document.querySelector('.toast');
        if (!el) return;
        el.textContent = message;
        el.hidden = false;
        requestAnimationFrame(() => el.classList.add('is-open'));
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => el.classList.remove('is-open'), 2600);
    }

    // ==========================================================================
    // Contents pane
    // ==========================================================================

    let navigationData = null;

    async function loadNavigation() {
        try {
            const response = await fetchData('navigation.json');
            if (response.ok) {
                navigationData = await response.json();
                return true;
            }
        } catch (error) {
            console.warn('Could not load navigation manifest:', error);
        }
        return false;
    }

    /** Adopt the sidebar the build rendered; false if this page has none. */
    function hydrateSidebarNav() {
        const sidebarNav = document.querySelector('.sidebar-nav');
        if (!sidebarNav || !sidebarNav.querySelector('.nav-chapter')) return false;
        scrollActiveSectionIntoView(sidebarNav);
        setupChapterToggle();
        return true;
    }

    function scrollActiveSectionIntoView(sidebarNav) {
        const active = sidebarNav.querySelector('.nav-section-item.active');
        const sidebar = document.getElementById('quarto-sidebar');
        if (!active || !sidebar) return;
        const offset = active.getBoundingClientRect().top - sidebar.getBoundingClientRect().top;
        if (offset > sidebar.clientHeight * 0.7) {
            sidebar.scrollTop = offset - sidebar.clientHeight / 3;
        }
    }

    /** Fallback when the page has no server-rendered tree: the same markup as
     *  render_navigation() in build/manifest.py. */
    function buildSidebarNav() {
        if (!navigationData) return;
        const sidebarNav = document.querySelector('.sidebar-nav');
        if (!sidebarNav) return;
        const current = currentPagePath();
        const base = getBasePath();
        const chevron = '<svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3.5 10.5 8 6 12.5"/></svg>';
        let html = '<ul class="nav-list">';
        const home = navigationData.home || { title: 'Preface', path: 'index.html' };
        html += `<li class="nav-item nav-home"><a href="${base}${home.path}">${home.title}</a></li>`;
        for (const extra of navigationData.extras || []) {
            const active = current === extra.path ? ' active' : '';
            html += `<li class="nav-item nav-extra${active}"><a href="${base}${extra.path}"><i class="bi ${extra.icon}" aria-hidden="true"></i> ${extra.title}</a></li>`;
        }
        navigationData.chapters.forEach((chapter, index) => {
            const isActive = chapter.sections.some(s => s.path === current) || chapter.path === current;
            const url = chapter.path || chapter.sections[0]?.path;
            if (chapter.part) html += `<li class="nav-part">${chapter.part}</li>`;
            html += `<li class="nav-chapter${isActive ? ' active' : ''}"${isActive ? ' data-open' : ''}>`
                + `<div class="nav-chapter-header" data-chapter="${index}">`
                + `<a href="${url ? base + url : '#'}" class="nav-chapter-title-link">`
                + (chapter.number ? `<span class="nav-chapter-number">${chapter.number}</span>` : '')
                + `<span class="nav-chapter-title">${chapter.title}</span></a>`
                + `<button type="button" class="nav-toggle" aria-expanded="${isActive}" aria-controls="nav-sections-${index}" aria-label="Sections of chapter ${chapter.number || index + 1}">${chevron}</button>`
                + `</div><div class="nav-sections-wrap" id="nav-sections-${index}"><ul class="nav-sections">`;
            chapter.sections.forEach(section => {
                const active = section.path === current;
                html += `<li class="nav-section-item${active ? ' active' : ''}" data-path="${escapeHtml(section.path)}">`
                    + `<a href="${base}${section.path}"${active ? ' aria-current="page"' : ''}>`
                    + `<span class="nav-section-number">${section.number}</span>`
                    + `<span class="nav-section-title">${section.title}</span><span class="nav-done" aria-hidden="true"></span></a></li>`;
            });
            html += '</ul></div></li>';
        });
        html += '</ul>';
        sidebarNav.innerHTML = html;
        scrollActiveSectionIntoView(sidebarNav);
        setupChapterToggle();
    }

    /** Chapter toggles: real buttons; the open state is an attribute, the motion is CSS. */
    function setupChapterToggle() {
        document.querySelectorAll('.nav-chapter').forEach(chapter => {
            let toggle = chapter.querySelector(':scope > .nav-chapter-header > .nav-toggle');
            if (!toggle) return;
            if (toggle.tagName !== 'BUTTON') {   // an older page: a span becomes a button
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'nav-toggle';
                button.innerHTML = toggle.innerHTML;
                toggle.replaceWith(button);
                toggle = button;
            }
            toggle.setAttribute('aria-expanded', String(chapter.hasAttribute('data-open')));
            toggle.addEventListener('click', event => {
                event.preventDefault();
                const open = !chapter.hasAttribute('data-open');
                chapter.toggleAttribute('data-open', open);
                toggle.setAttribute('aria-expanded', String(open));
            });
        });
    }

    // ==========================================================================
    // On this page
    // ==========================================================================

    function buildTableOfContents() {
        const tocContainer = document.querySelector('.toc');
        const content = document.querySelector('.content');
        if (!tocContainer || !content) return;
        const headings = content.querySelectorAll('h2, h3');
        if (headings.length === 0) {
            tocContainer.hidden = true;
            return;
        }
        let html = '<h2>On this page</h2><ul class="toc-list"><span class="toc-marker" aria-hidden="true"></span>';
        headings.forEach(heading => {
            const level = heading.tagName.toLowerCase();
            const id = heading.id || heading.textContent.toLowerCase().replace(/[^a-z0-9]+/g, '-');
            heading.id = id;
            const numberEl = heading.querySelector('.header-section-number');
            const number = numberEl ? numberEl.textContent.trim().replace(/\.$/, '') : '';
            const titleEl = heading.cloneNode(true);
            titleEl.querySelectorAll('.header-section-number, .anchor-link').forEach(el => el.remove());
            const numberHtml = number ? `<span class="toc-number">${escapeHtml(number)}</span>` : '';
            html += `<li class="toc-item${level === 'h3' ? ' toc-indent' : ''}"><a href="#${id}">${numberHtml}<span class="toc-text">${escapeHtml(titleEl.textContent.trim())}</span></a></li>`;
        });
        html += '</ul>';
        tocContainer.innerHTML = html;
        setupScrollSpy(headings);
    }

    /** The current heading lights up in the pane, and one marker glides to it. */
    function setupScrollSpy(headings) {
        const list = document.querySelector('.toc-list');
        const marker = list?.querySelector('.toc-marker');
        const headingArray = Array.from(headings);
        let ticking = false;
        let current = null;

        function update() {
            ticking = false;
            const offset = (document.querySelector('.site-header')?.offsetHeight || 56) + 40;
            let found = null;
            for (let i = headingArray.length - 1; i >= 0; i--) {
                const heading = headingArray[i];
                if (heading.closest('.tab-panel[hidden]')) continue;
                if (heading.getBoundingClientRect().top <= offset) { found = heading; break; }
            }
            if (!found) found = headingArray.find(h => !h.closest('.tab-panel[hidden]')) || null;
            const link = found && list?.querySelector(`a[href="#${CSS.escape(found.id)}"]`);
            if (!link || link === current) return;
            current?.classList.remove('active');
            link.classList.add('active');
            current = link;
            if (marker) {
                marker.style.setProperty('--marker-y', `${link.offsetTop + 4}px`);
                marker.style.setProperty('--marker-h', `${link.offsetHeight - 8}px`);
            }
        }

        window.addEventListener('scroll', () => {
            if (!ticking) { ticking = true; requestAnimationFrame(update); }
        }, { passive: true });
        window.addEventListener('toc-refresh', () => { current = null; update(); });
        update();
        // the marker glides only after it has found its first place
        requestAnimationFrame(() => requestAnimationFrame(() => list?.classList.add('ready')));
    }

    /** The hairline under the header, where scroll-driven animations are not supported. */
    function setupReadProgress() {
        if (CSS.supports('animation-timeline: scroll()')) return;
        const bar = document.querySelector('.read-progress span');
        if (!bar) return;
        let ticking = false;
        const update = () => {
            ticking = false;
            const max = document.documentElement.scrollHeight - window.innerHeight;
            bar.style.setProperty('--progress', max > 0 ? Math.min(1, window.scrollY / max).toFixed(4) : 0);
        };
        window.addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
        update();
    }

    // ==========================================================================
    // Reference previews ("peeks")
    // ==========================================================================

    // One small file per result (theorems/<chapter>/<label>.json), fetched on first hover;
    // sessionStorage carries entries across page loads.
    const theoremEntries = new Map();

    function cached(labelId) {
        try {
            const stored = sessionStorage.getItem(`thm:${assetVersion()}:${labelId}`);
            return stored ? JSON.parse(stored) : undefined;
        } catch (error) {
            return undefined;
        }
    }

    function remember(labelId, info) {
        try { sessionStorage.setItem(`thm:${assetVersion()}:${labelId}`, JSON.stringify(info)); } catch (error) { /* full */ }
    }

    function loadEntry(shard, labelId, base) {
        const key = base ? `${base}|${labelId}` : labelId;
        if (!theoremEntries.has(key)) {
            const stored = base ? undefined : cached(labelId);
            if (stored !== undefined) {
                theoremEntries.set(key, Promise.resolve(stored));
            } else {
                const request = base
                    ? fetch(`${base}theorems/${shard}/${labelId}.json`)
                    : fetchData(`theorems/${shard}/${labelId}.json`);
                theoremEntries.set(key, request
                    .then(response => response.ok ? response.json() : null)
                    .then(info => { if (info && !base) remember(labelId, info); return info; })
                    .catch(() => null));
            }
        }
        return theoremEntries.get(key);
    }

    function previewHtml(refId, info, goTo, book) {
        if (!info) return `<div class="tooltip-error">Reference not found: ${escapeHtml(refId)}</div>`;
        let title = info.type_name || (info.type.charAt(0).toUpperCase() + info.type.slice(1));
        if (info.number) title += ` ${info.number}`;
        const name = info.title_html || info.title;
        if (book) title = `<span class="xref-book">${escapeHtml(book)}</span>, ${title}`;
        const footer = goTo
            ? `<a class="tooltip-go" href="${escapeHtml(goTo.href)}"><span>Go to ${escapeHtml(goTo.label)}</span><i class="bi bi-arrow-right" aria-hidden="true"></i></a>`
            : '';
        return `<div class="tooltip-theorem ${escapeHtml(info.type)}">`
            + `<div class="tooltip-title"><span>${title}${name ? ` <span class="env-name">· ${name}</span>` : ''}</span></div>`
            + `<div class="tooltip-content">${info.html || 'Content not available'}</div>${footer}</div>`;
    }

    const SKELETON = '<div class="tooltip-skeleton" aria-hidden="true"><i></i><i></i><i></i><i></i></div>';

    function setupPeeks() {
        const links = [...document.querySelectorAll('a.xref[data-ref]')];
        if (!links.length) return;
        const touch = window.matchMedia('(hover: none)').matches;

        const peek = document.createElement('div');
        peek.className = 'peek';
        peek.id = 'reference-preview';
        peek.setAttribute('role', 'tooltip');
        document.body.append(peek);

        let owner = null;          // the link the card belongs to
        let anchorRect = null;     // the line box of the link that was hovered
        let openTimer = 0, closeTimer = 0, request = 0;

        /** Above the link if it fits, else below; never off-screen. The transform origin is
         *  the point of the card's edge nearest the link, so it grows out of the reference. */
        function place() {
            if (!owner || !anchorRect) return;
            const gap = 8, margin = 12;
            const w = peek.offsetWidth, h = peek.offsetHeight;
            const vw = document.documentElement.clientWidth, vh = window.innerHeight;
            const header = document.querySelector('.site-header')?.offsetHeight || 0;
            const above = anchorRect.top - gap - h >= header + margin;
            const below = anchorRect.bottom + gap + h <= vh - margin;
            const side = (above || !below) && !(touch && below) ? 'top' : 'bottom';
            const centre = anchorRect.left + anchorRect.width / 2;
            const x = Math.max(margin, Math.min(centre - w / 2, vw - w - margin));
            const y = side === 'top' ? Math.max(header + margin, anchorRect.top - gap - h) : anchorRect.bottom + gap;
            peek.style.left = `${Math.round(x)}px`;
            peek.style.top = `${Math.round(y)}px`;
            peek.dataset.side = side;
            const ox = Math.max(12, Math.min(w - 12, centre - x));
            peek.style.setProperty('--peek-origin', `${Math.round(ox)}px ${side === 'top' ? '100%' : '0%'}`);
        }

        function rectFor(link, event) {
            const rects = [...link.getClientRects()];
            if (event && 'clientY' in event && rects.length > 1) {
                const hit = rects.find(r => event.clientY >= r.top - 2 && event.clientY <= r.bottom + 2);
                if (hit) return hit;
            }
            return rects[0] || link.getBoundingClientRect();
        }

        function show(link, event) {
            clearTimeout(closeTimer);
            if (owner && owner !== link) owner.removeAttribute('aria-describedby');
            owner = link;
            anchorRect = rectFor(link, event);
            link.setAttribute('aria-describedby', peek.id);
            const id = ++request;
            const { ref, shard } = link.dataset;
            const base = link.dataset.base || '';
            const book = link.dataset.book || '';
            const goTo = touch ? { href: link.getAttribute('href'), label: link.textContent.trim() } : null;
            let settled = false;
            loadEntry(shard, ref, base).then(info => {
                settled = true;
                if (id !== request) return;
                if (!info && base) {   // another site's preview could not be read: a plain link
                    hide(true);
                    link.classList.add('xref-nopeek');
                    return;
                }
                peek.innerHTML = previewHtml(ref, info, goTo, book);
                if (!document.querySelector('meta[name="math-prerendered"]') && window.MathJax?.typesetPromise) {
                    MathJax.typesetPromise([peek]).then(place).catch(() => {});
                }
                place();
            });
            if (!settled) {
                peek.innerHTML = SKELETON;
            }
            place();
            peek.classList.add('is-open');
        }

        function hide(now) {
            clearTimeout(openTimer);
            clearTimeout(closeTimer);
            const go = () => {
                request++;
                peek.classList.remove('is-open');
                owner?.removeAttribute('aria-describedby');
                owner = null;
            };
            if (now) go(); else closeTimer = setTimeout(go, 160);
        }

        links.forEach(link => {
            if (touch) {
                link.addEventListener('click', event => {
                    if (link.classList.contains('xref-nopeek')) return;
                    if (owner === link && peek.classList.contains('is-open')) return;   // second tap follows
                    event.preventDefault();
                    show(link, event);
                });
                return;
            }
            link.addEventListener('pointerenter', event => {
                if (event.pointerType === 'touch' || link.classList.contains('xref-nopeek')) return;
                clearTimeout(closeTimer);
                clearTimeout(openTimer);
                // already open on another link: move at once; else a short delay
                const delay = peek.classList.contains('is-open') ? 0 : 120;
                openTimer = setTimeout(() => show(link, event), delay);
            });
            link.addEventListener('pointerleave', () => { clearTimeout(openTimer); hide(false); });
            link.addEventListener('focus', () => { if (link.matches(':focus-visible')) show(link); });
            link.addEventListener('blur', () => hide(false));
        });

        peek.addEventListener('pointerenter', () => clearTimeout(closeTimer));
        peek.addEventListener('pointerleave', () => hide(false));
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && peek.classList.contains('is-open')) hide(true);
        });
        document.addEventListener('pointerdown', event => {
            if (owner && !peek.contains(event.target) && !owner.contains(event.target)) hide(true);
        });
        let ticking = false;
        const follow = () => {
            ticking = false;
            if (!owner) return;
            anchorRect = rectFor(owner);
            if (anchorRect.bottom < 0 || anchorRect.top > window.innerHeight) hide(true);
            else place();
        };
        window.addEventListener('scroll', () => { if (!ticking && owner) { ticking = true; requestAnimationFrame(follow); } }, { passive: true });
        window.addEventListener('resize', () => owner && follow());
    }

    // ==========================================================================
    // Labels, theorem titles, exercise checks
    // ==========================================================================

    /** The nodes of a run-in label: from the start of the paragraph to the italic "."
     *  (or just the first <em> when there is none). */
    function labelNodes(paragraph) {
        const nodes = [...paragraph.childNodes];
        const end = nodes.findIndex(n => n.nodeType === Node.ELEMENT_NODE && n.tagName === 'EM' && n.textContent.trim() === '.');
        if (end >= 0) {
            nodes[end].classList.add('label-dot');
            return nodes.slice(0, end + 1);
        }
        const first = nodes.find(n => !(n.nodeType === Node.TEXT_NODE && !n.textContent.trim()));
        return first && first.tagName === 'EM' ? nodes.slice(0, nodes.indexOf(first) + 1) : [];
    }

    /** Run-in labels of the small environments (Idea, Warning, ...) in a span of their own. */
    function setupSmallLabels() {
        document.querySelectorAll('.content .small-env').forEach(block => {
            if (block.classList.contains('foldable')) return;
            const first = block.firstElementChild;
            if (!first || first.tagName !== 'P' || first.querySelector('.env-label, .fold-toggle')) return;
            const nodes = labelNodes(first);
            if (!nodes.length) return;
            const label = document.createElement('span');
            label.className = 'env-label';
            nodes.forEach(n => label.append(n));
            first.prepend(label, ' ');
        });
    }

    /** "Theorem 2.2.1 (Functions on Classes)": the name after the kind, without the
     *  brackets, in a span the header strip sets beside the kind. */
    function setupTheoremTitles() {
        document.querySelectorAll('.content .env > .theorem-title').forEach(title => {
            const first = title.querySelector(':scope > strong');
            if (!first) return;
            // The kind and its number ("Theorem" "2.2.1") are separate <strong>s: one chip
            const kind = document.createElement('span');
            kind.className = 'env-kind';
            let node = first;
            while (node && (node.tagName === 'STRONG' || (node.nodeType === Node.TEXT_NODE && !node.textContent.trim()))) {
                const next = node.nextSibling;
                if (node.nodeType === Node.TEXT_NODE) kind.append(' ');
                else {
                    node.textContent = node.textContent.trim();
                    if (kind.lastChild && kind.lastChild.nodeType !== Node.TEXT_NODE) kind.append(' ');
                    kind.append(node);
                }
                node = next;
            }
            title.prepend(kind);
            const rest = [];
            for (let n = kind.nextSibling; n; n = n.nextSibling) rest.push(n);
            const text = rest.map(n => n.textContent).join('').replace(/\s+/g, ' ').trim();
            if (!text) return;
            const name = document.createElement('span');
            name.className = 'env-name';
            rest.forEach(n => name.append(n));
            if (/^\(/.test(text) && /\)$/.test(text)) {
                const texts = [];
                const walk = document.createTreeWalker(name, NodeFilter.SHOW_TEXT);
                while (walk.nextNode()) texts.push(walk.currentNode);
                const firstText = texts.find(t => t.textContent.trim());
                const lastText = [...texts].reverse().find(t => t.textContent.trim());
                if (firstText && lastText && !firstText.parentElement.closest('mjx-container')
                    && !lastText.parentElement.closest('mjx-container')) {
                    firstText.textContent = firstText.textContent.replace(/^\s*\(/, '');
                    lastText.textContent = lastText.textContent.replace(/\)\s*$/, '');
                    // An exercise's label ("A1", "B1: Two rules ...") is its number
                    const label = firstText.textContent.match(/^\s*([A-Z]\d+[a-z]?)(?::\s*|\s*$)/);
                    if (title.closest('.exercise') && label) {
                        const number = document.createElement('strong');
                        number.textContent = label[1];
                        kind.append(' ', number);
                        firstText.textContent = firstText.textContent.slice(label[0].length);
                    }
                }
            }
            const optional = name.querySelector('.env-optional');
            if (name.textContent.trim()) title.append(name);
            if (optional) title.append(optional);
        });
    }

    // Exercises and sections marked done: stored per book in this browser. Optimistic: the
    // mark shows at the click; if the browser cannot store it, the mark is undone and a
    // toast says why.
    const DONE_KEY = () => `atlas:done:${bookKey()}`;
    const EX_KEY = () => `atlas:exercises:${bookKey()}`;

    function toggleStored(key, id, on) {
        const set = new Set(readJson(key, []));
        if (on) set.add(id); else set.delete(id);
        return writeJson(key, [...set]);
    }

    function setupExerciseChecks() {
        const done = new Set(readJson(EX_KEY(), []));
        document.querySelectorAll('.content .env.exercise[id]').forEach(exercise => {
            const title = exercise.querySelector(':scope > .theorem-title');
            if (!title) return;
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'exercise-check';
            button.innerHTML = '<span class="done-box" aria-hidden="true"><i class="bi bi-check"></i></span><span class="exercise-check-text">Done</span>';
            const apply = on => {
                button.setAttribute('aria-pressed', String(on));
                button.setAttribute('aria-label', `${on ? 'Done' : 'Mark as done'}: ${title.textContent.replace(/#/g, '').trim()}`);
                exercise.classList.toggle('is-done', on);
            };
            apply(done.has(exercise.id));
            button.addEventListener('click', () => {
                const on = button.getAttribute('aria-pressed') !== 'true';
                apply(on);                                   // at once
                if (!toggleStored(EX_KEY(), exercise.id, on)) {
                    apply(!on);                              // could not be kept: roll back
                    toast('Could not save this in your browser (private window?)');
                }
                window.dispatchEvent(new Event('exercises-changed'));
            });
            title.append(button);
        });
    }

    // ==========================================================================
    // Proofs and solutions: progressive disclosure
    // ==========================================================================

    let foldCount = 0;

    function setupFolding() {
        document.querySelectorAll('.content .proof.small-env, .content .solution.small-env').forEach(block => {
            if (block.parentElement.closest('.proof, .solution')) return;
            const first = block.firstElementChild;
            if (!first || first.tagName !== 'P') return;
            const nodes = labelNodes(first);
            if (!nodes.length) return;
            const kind = block.classList.contains('solution') ? 'solution' : 'proof';

            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'fold-toggle';
            const chevron = document.createElement('span');
            chevron.className = 'fold-chevron';
            chevron.innerHTML = '<i class="bi bi-chevron" aria-hidden="true"></i>';
            const label = document.createElement('span');
            label.className = 'fold-label';
            nodes.forEach(n => label.append(n));
            button.append(label, chevron);

            // The rest of the first paragraph becomes the body's first paragraph
            const head = document.createElement('p');
            head.className = 'fold-head';
            head.append(button);
            const body = document.createElement('div');
            body.className = 'fold-body';
            body.id = `fold-${++foldCount}`;
            const inner = document.createElement('div');
            inner.className = 'fold-inner';
            body.append(inner);
            if (first.textContent.trim() || first.querySelector('mjx-container, img')) {
                while (first.firstChild && !first.firstChild.textContent.trim() && first.firstChild.nodeType === Node.TEXT_NODE) first.firstChild.remove();
                inner.append(first);
            } else {
                first.remove();
            }
            while (block.firstChild) inner.append(block.firstChild);
            block.append(head, body);
            block.classList.add('foldable');
            button.setAttribute('aria-controls', body.id);

            const set = folded => {
                block.classList.toggle('is-folded', folded);
                button.setAttribute('aria-expanded', String(!folded));
                button.title = `${folded ? 'Show' : 'Hide'} ${kind}`;
                inner.inert = folded;
            };
            button.addEventListener('click', () => set(!block.classList.contains('is-folded')));
            block.addEventListener('unfold', () => set(false));
            set(kind === 'solution');
        });
    }

    function unfoldAround(element) {
        openFoldsAround(element);
        for (let block = element?.closest('.is-folded'); block; block = block.parentElement?.closest('.is-folded')) {
            block.dispatchEvent(new Event('unfold'));
        }
    }

    function openFoldsAround(element) {
        let opened = false;
        for (let d = element?.closest('details'); d; d = d.parentElement?.closest('details')) {
            if (!d.open) { d.open = true; opened = true; }
        }
        return opened;
    }

    function setupFoldLinks() {
        document.addEventListener('click', event => {
            const link = event.target.closest?.('a[href*="#"]');
            if (!link) return;
            const url = new URL(link.href, location.href);
            if (url.origin !== location.origin || url.pathname !== location.pathname || url.hash.length < 2) return;
            const target = document.getElementById(decodeURIComponent(url.hash.slice(1)));
            openFoldsAround(target);
            unfoldAround(target);
        }, true);
        const closed = [];
        const folded = [];
        window.addEventListener('beforeprint', () => {
            document.querySelectorAll('details.second-reading:not([open])').forEach(d => { d.open = true; closed.push(d); });
            document.querySelectorAll('.fold-inner[inert]').forEach(i => { i.inert = false; folded.push(i); });
        });
        window.addEventListener('afterprint', () => {
            closed.splice(0).forEach(d => { d.open = false; });
            folded.splice(0).forEach(i => { i.inert = true; });
        });
    }

    // ==========================================================================
    // Formulas: selection and copy
    // ==========================================================================

    function setupMathSelection() {
        let marked = [];
        let pending = false;
        const update = () => {
            pending = false;
            const selection = window.getSelection();
            let touched = [];
            if (selection && !selection.isCollapsed && selection.rangeCount) {
                let scope = selection.getRangeAt(0).commonAncestorContainer;
                if (scope.nodeType !== Node.ELEMENT_NODE) scope = scope.parentElement;
                const inside = scope.closest('mjx-container');
                touched = inside ? [inside]
                    : [...scope.querySelectorAll('mjx-container')].filter(node => selection.containsNode(node, true));
            }
            marked.forEach(node => { if (!touched.includes(node)) node.classList.remove('math-selected'); });
            touched.forEach(node => node.classList.add('math-selected'));
            marked = touched;
        };
        document.addEventListener('selectionchange', () => {
            if (pending) return;
            pending = true;
            requestAnimationFrame(update);
        });
    }

    function setupMathCopy() {
        const BREAK = ' ';
        document.addEventListener('copy', event => {
            const selection = window.getSelection();
            if (!selection || selection.isCollapsed || !event.clipboardData) return;
            const fragment = selection.getRangeAt(0).cloneContents();
            if (!fragment.querySelector('mjx-container[data-tex]')) return;
            fragment.querySelectorAll('mjx-assistive-mml, .fold-chevron, .anchor-link, .tab-continue, .exercise-check')
                .forEach(node => node.remove());
            fragment.querySelectorAll('mjx-container[data-tex]').forEach(node => {
                const tex = node.getAttribute('data-tex').replace(/\s+/g, ' ').trim();
                const display = node.getAttribute('display') === 'true';
                node.replaceWith(document.createTextNode(display ? `${BREAK}\\[ ${tex} \\]${BREAK}` : `\\( ${tex} \\)`));
            });
            const wrapper = document.createElement('div');
            wrapper.append(fragment);
            wrapper.querySelectorAll('p, li, h1, h2, h3, h4, h5, h6, blockquote, .env, .small-env, .tikz-figure')
                .forEach(block => block.append(document.createTextNode(BREAK)));
            const text = wrapper.textContent.replace(/\s+/g, ' ')
                .split(BREAK).map(part => part.trim()).filter(Boolean).join('\n\n');
            event.clipboardData.setData('text/plain', text);
            event.preventDefault();
        });
    }

    let mathjaxLoading = null;
    function ensureMathJax() {
        if (window.MathJax?.typesetPromise) return Promise.resolve(window.MathJax);
        if (mathjaxLoading) return mathjaxLoading;
        const load = src => new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = src;
            script.onload = resolve;
            script.onerror = reject;
            document.head.append(script);
        });
        mathjaxLoading = load(getBasePath() + 'mathjax-macros.js').then(() => {
            window.MathJax = {
                tex: {
                    inlineMath: [['\\(', '\\)']], displayMath: [['\\[', '\\]']],
                    processEscapes: true, processEnvironments: true, macros: window.BOOK_MACROS || {},
                },
                options: { skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre'] },
                startup: { typeset: false },
            };
            return load('https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-chtml-full.js');
        }).then(() => window.MathJax.startup.promise).then(() => window.MathJax).catch(() => null);
        return mathjaxLoading;
    }

    /** Widows of punctuation: a formula and the comma or full stop after it (and an
     *  opening bracket before it) never part at a line break. */
    function glueMathPunctuation() {
        document.querySelectorAll('.content mjx-container:not([display="true"])').forEach(math => {
            const host = math.parentElement?.matches('span.math') ? math.parentElement : math;
            const next = host.nextSibling;
            const prev = host.previousSibling;
            const after = next?.nodeType === Node.TEXT_NODE ? next.textContent.match(/^[.,;:!?)\]’”]+/) : null;
            const before = prev?.nodeType === Node.TEXT_NODE ? prev.textContent.match(/[(\[‘“]+$/) : null;
            if (!after && !before) return;
            const glue = document.createElement('span');
            glue.className = 'nowrap';
            host.before(glue);
            if (before) {
                prev.textContent = prev.textContent.slice(0, -before[0].length);
                glue.append(before[0]);
            }
            glue.append(host);
            if (after) {
                next.textContent = next.textContent.slice(after[0].length);
                glue.append(after[0]);
            }
        });
    }

    // A table wider than the column scrolls sideways inside its own box; the table itself
    // keeps the column's full width, so its hairlines line up with the text
    function wrapTables() {
        document.querySelectorAll('.content table').forEach(table => {
            if (table.parentElement.classList.contains('table-wrap')) return;
            const wrap = document.createElement('div');
            wrap.className = 'table-wrap';
            table.before(wrap);
            wrap.append(table);
        });
    }

    function setupWideInlineMath() {
        const prerendered = document.querySelector('meta[name="math-prerendered"]');
        if (!prerendered && !window.MathJax) return;
        const update = () => {
            document.querySelectorAll('.content mjx-container:not([display="true"])').forEach(math => {
                math.classList.remove('wide-inline');
                const column = math.closest('li, p, .env, .small-env, .content');
                if (column && math.getBoundingClientRect().width > column.clientWidth) math.classList.add('wide-inline');
            });
        };
        if (prerendered) document.fonts.ready.then(update);
        else {
            const whenReady = () => MathJax.startup?.promise?.then(update);
            if (MathJax.startup?.promise) whenReady();
            else window.addEventListener('load', whenReady);
        }
        let timer;
        window.addEventListener('resize', () => { clearTimeout(timer); timer = setTimeout(update, 200); });
    }

    // ==========================================================================
    // Links: anchors, targets, smooth in-page scrolling, arrow-key paging
    // ==========================================================================

    function markTarget(element) {
        document.querySelectorAll('.is-target').forEach(el => el.classList.remove('is-target'));
        if (!element) return;
        unfoldAround(element);
        void element.offsetWidth;
        element.classList.add('is-target');
    }

    function markTargetFromHash() {
        if (location.hash.length > 1) {
            const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
            const moved = target && revealTabFor(target);
            if (target && (openFoldsAround(target) || moved)) target.scrollIntoView({ block: 'start' });
            markTarget(target);
        }
    }

    function setupSmoothScrolling() {
        document.addEventListener('click', event => {
            const anchor = event.target.closest?.('a[href^="#"]');
            if (!anchor || anchor.closest('.peek')) return;
            const targetId = decodeURIComponent(anchor.getAttribute('href').slice(1));
            const target = document.getElementById(targetId);
            if (!target) return;
            event.preventDefault();
            revealTabFor(target);
            openFoldsAround(target);
            target.scrollIntoView({ behavior: reduceMotion.matches ? 'auto' : 'smooth', block: 'start' });
            history.pushState(null, '', `#${targetId}`);
            markTarget(target);
        });
    }

    function setupAnchorLinks() {
        const content = document.querySelector('.content');
        if (!content) return;
        content.querySelectorAll('h2[id], h3[id], .env[id]').forEach(element => {
            const host = element.classList.contains('env') ? element.querySelector('.theorem-title') : element;
            if (!host) return;
            const link = document.createElement('a');
            link.className = 'anchor-link';
            link.href = `#${element.id}`;
            link.textContent = '#';
            link.setAttribute('aria-label', 'Copy link to this ' + (element.classList.contains('env') ? 'result' : 'section'));
            link.addEventListener('click', () => {
                const url = `${location.origin}${location.pathname}#${element.id}`;
                navigator.clipboard?.writeText(url).then(() => {
                    link.dataset.copied = 'true';
                    setTimeout(() => delete link.dataset.copied, 1500);
                }).catch(() => {});
            });
            const kind = host.querySelector(':scope > .env-kind');
            if (kind) (host.querySelector(':scope > .env-name') || kind).after(link); else host.append(' ', link);
        });
    }

    function setupArrowKeys() {
        document.addEventListener('keydown', event => {
            if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
            if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
            const target = event.target;
            if (target.closest('input, textarea, select, [contenteditable="true"], .code-cell, .plot, .widget, [role="tab"], .palette')) return;
            if (document.body.classList.contains('drawer-open')) return;
            if (target !== document.body && target.scrollWidth > target.clientWidth) return;
            const link = document.querySelector(event.key === 'ArrowLeft'
                ? '.nav-page-previous .pagination-link' : '.nav-page-next .pagination-link');
            if (link) {
                event.preventDefault();
                lastClicked = link;
                link.click();
            }
        });
    }

    // ==========================================================================
    // Reading / Exercises tabs
    // ==========================================================================

    let selectSectionTab = null;

    function revealTabFor(element) {
        const panel = element?.closest('.tab-panel');
        if (!panel || !panel.hidden || !selectSectionTab) return false;
        selectSectionTab(panel.dataset.tab);
        return true;
    }

    function setupSectionTabs() {
        const content = document.querySelector('.content');
        const heading = content?.querySelector(':scope > h2#exercises');
        if (!heading) return;

        const makePanel = name => {
            const panel = document.createElement('div');
            panel.className = 'tab-panel';
            panel.dataset.tab = name;
            panel.id = `tab-panel-${name}`;
            panel.setAttribute('role', 'tabpanel');
            panel.setAttribute('aria-labelledby', `tab-${name}`);
            return panel;
        };
        const reading = makePanel('reading');
        const exercises = makePanel('exercises');

        const header = content.querySelector(':scope > header');
        let node = header ? header.nextSibling : content.firstChild;
        while (node && node !== heading) { const next = node.nextSibling; reading.append(node); node = next; }
        while (node) { const next = node.nextSibling; exercises.append(node); node = next; }

        const all = () => [...exercises.querySelectorAll('.exercise.env')];
        const count = all().length;
        const bar = document.createElement('div');
        bar.className = 'section-tabs';
        bar.setAttribute('role', 'tablist');
        bar.setAttribute('aria-label', 'Section parts');
        const pill = document.createElement('span');
        pill.className = 'section-tabs-pill';
        pill.setAttribute('aria-hidden', 'true');
        const makeTab = (name, text) => {
            const tab = document.createElement('button');
            tab.type = 'button';
            tab.className = 'section-tab';
            tab.id = `tab-${name}`;
            tab.dataset.tab = name;
            tab.setAttribute('role', 'tab');
            tab.setAttribute('aria-controls', `tab-panel-${name}`);
            tab.innerHTML = `<span>${text}</span>`;
            return tab;
        };
        const tabs = [makeTab('reading', 'Reading'), makeTab('exercises', 'Exercises')];
        const badge = document.createElement('span');
        badge.className = 'tab-count';
        if (count) tabs[1].append(badge);
        bar.append(pill, ...tabs);

        const next = document.createElement('button');
        next.type = 'button';
        next.className = 'tab-continue';
        next.innerHTML = `<span><span>Continue to the exercises</span><span class="tab-continue-count"></span></span><i class="bi bi-arrow-right" aria-hidden="true"></i>`;
        reading.append(next);

        const updateCounts = () => {
            const done = all().filter(e => e.classList.contains('is-done')).length;
            badge.textContent = done ? `${done}/${count}` : String(count);
            next.querySelector('.tab-continue-count').textContent =
                `(${count} exercise${count === 1 ? '' : 's'}${done ? ` · ${done} done` : ''})`;
        };
        updateCounts();
        window.addEventListener('exercises-changed', updateCounts);

        if (header) header.after(bar, reading, exercises);
        else content.prepend(bar, reading, exercises);

        const movePill = () => {
            const tab = tabs.find(t => t.getAttribute('aria-selected') === 'true') || tabs[0];
            pill.style.setProperty('--pill-x', `${tab.offsetLeft}px`);
            pill.style.setProperty('--pill-w', `${tab.offsetWidth}px`);
        };

        const select = (name, { scroll = false, updateHash = false } = {}) => {
            for (const tab of tabs) {
                const on = tab.dataset.tab === name;
                tab.setAttribute('aria-selected', String(on));
                tab.tabIndex = on ? 0 : -1;
            }
            reading.hidden = name !== 'reading';
            exercises.hidden = name !== 'exercises';
            movePill();
            document.querySelectorAll('.toc a[href^="#"]').forEach(link => {
                const target = document.getElementById(decodeURIComponent(link.getAttribute('href').slice(1)));
                link.closest('li')?.classList.toggle('toc-other-tab', !!target?.closest('.tab-panel[hidden]'));
            });
            if (updateHash) history.replaceState(null, '', name === 'exercises' ? '#exercises' : location.pathname + location.search);
            if (scroll && bar.getBoundingClientRect().top < (document.querySelector('.site-header')?.offsetHeight || 0)) {
                bar.scrollIntoView({ block: 'start' });
            }
            window.dispatchEvent(new Event('toc-refresh'));
        };
        selectSectionTab = name => select(name);

        tabs.forEach((tab, index) => {
            tab.addEventListener('click', () => select(tab.dataset.tab, { scroll: true, updateHash: true }));
            tab.addEventListener('keydown', event => {
                if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
                event.preventDefault();
                const other = tabs[(index + 1) % tabs.length];
                other.focus();
                select(other.dataset.tab, { updateHash: true });
            });
        });
        next.addEventListener('click', () => {
            select('exercises', { updateHash: true });
            bar.scrollIntoView({ block: 'start', behavior: reduceMotion.matches ? 'auto' : 'smooth' });
        });

        select('reading');
        document.fonts?.ready.then(movePill);
        window.addEventListener('resize', movePill);
        requestAnimationFrame(() => requestAnimationFrame(() => bar.classList.add('ready')));
    }

    // ==========================================================================
    // Progress: sections done, recent pages, chapter opening cards
    // ==========================================================================

    function sectionItems() {
        return [...document.querySelectorAll('.sidebar-nav .nav-section-item[data-path]')];
    }

    function refreshProgress() {
        const done = new Set(readJson(DONE_KEY(), []));
        const items = sectionItems();
        items.forEach(item => item.classList.toggle('is-done', done.has(item.dataset.path)));
        const box = document.querySelector('.sidebar-progress');
        const count = items.filter(item => done.has(item.dataset.path)).length;
        if (box) {
            box.hidden = count === 0;
            box.querySelector('.sidebar-progress-count').textContent = count;
            box.querySelector('.sidebar-progress-total').textContent = items.length;
            box.querySelector('.meter span')?.style.setProperty('--done', items.length ? (count / items.length).toFixed(4) : 0);
        }
        document.querySelectorAll('.chapter-sections li[data-path]').forEach(li => li.classList.toggle('is-done', done.has(li.dataset.path)));
        return done;
    }

    function setupDoneToggle() {
        const path = currentPagePath();
        const isSection = sectionItems().some(item => item.dataset.path === path);
        if (!isSection) { refreshProgress(); return; }

        // A second toggle at the end of the text, for screens without the right pane
        const content = document.querySelector('.content');
        const row = document.createElement('div');
        row.className = 'page-done';
        row.innerHTML = '<span>Finished this section?</span>';
        const paneButton = document.querySelector('.page-actions .done-toggle');
        const rowButton = paneButton ? paneButton.cloneNode(true) : null;
        if (rowButton) row.append(rowButton);
        const target = content?.querySelector('.tab-panel[data-tab="reading"] .tab-continue');
        if (target) target.before(row); else content?.append(row);
        const buttons = [paneButton, rowButton].filter(Boolean);

        const apply = on => buttons.forEach(button => {
            button.hidden = false;
            button.setAttribute('aria-pressed', String(on));
            button.querySelector('.done-text').textContent = on ? 'Done' : 'Mark section as done';
        });
        apply(refreshProgress().has(path));
        buttons.forEach(button => button.addEventListener('click', () => {
            const on = button.getAttribute('aria-pressed') !== 'true';
            apply(on);                                  // optimistic: the UI first
            const item = sectionItems().find(i => i.dataset.path === path);
            item?.classList.toggle('is-done', on);
            if (!toggleStored(DONE_KEY(), path, on)) {
                apply(!on);
                item?.classList.toggle('is-done', !on);
                toast('Could not save this in your browser (private window?)');
                return;
            }
            refreshProgress();
        }));
    }

    function recordRecent() {
        const path = currentPagePath();
        // <title> holds the page's title as plain text, math included (\\nN -> ℕ)
        const title = document.title.split(' – ')[0].trim();
        if (!path || !title) return;
        const entry = { path, title, number: '' };
        const key = `atlas:recent:${bookKey()}`;
        const list = readJson(key, []).filter(e => e && e.path !== path);
        list.unshift(entry);
        writeJson(key, list.slice(0, 8));
    }

    /** On a chapter's opening page, its sections as a list of cards below the text. */
    function setupChapterOpening() {
        if (!document.querySelector('.chapter-eyebrow')) return;
        const chapter = document.querySelector('.sidebar-nav .nav-chapter.active');
        const items = chapter ? [...chapter.querySelectorAll('.nav-section-item')] : [];
        const content = document.querySelector('.content');
        if (!items.length || !content) return;
        const section = document.createElement('section');
        section.className = 'chapter-sections';
        section.setAttribute('aria-labelledby', 'in-this-chapter');
        section.innerHTML = '<h2 id="in-this-chapter">In this chapter</h2><ol></ol>';
        const list = section.querySelector('ol');
        items.forEach(item => {
            const link = item.querySelector('a');
            const li = document.createElement('li');
            li.dataset.path = item.dataset.path || '';
            li.innerHTML = `<a href="${link.getAttribute('href')}"><span class="cs-num">${item.querySelector('.nav-section-number')?.innerHTML || ''}</span>`
                + `<span class="cs-title">${item.querySelector('.nav-section-title')?.innerHTML || ''}</span>`
                + '<i class="bi bi-arrow-right cs-arrow" aria-hidden="true"></i></a>';
            list.append(li);
        });
        content.append(section);
    }

    // ==========================================================================
    // Header, panes and theme
    // ==========================================================================

    function setupLayoutControls() {
        const sidebar = document.getElementById('quarto-sidebar');
        const sidebarButton = document.querySelector('.sidebar-toggle');
        const tocButton = document.querySelector('.toc-toggle');
        const themeButton = document.querySelector('.theme-toggle');

        if (sidebar && sidebarButton) {
            const overlay = document.createElement('div');
            overlay.className = 'sidebar-overlay';
            document.body.appendChild(overlay);

            const setDrawer = open => {
                sidebar.classList.toggle('show', open);
                overlay.classList.toggle('show', open);
                document.body.classList.toggle('drawer-open', open);
                sidebar.inert = DRAWER_QUERY.matches && !open;
                sidebarButton.setAttribute('aria-expanded', String(open));
                setButtonLabel(sidebarButton, open ? 'Close book contents' : 'Open book contents');
                if (open) {
                    const current = sidebar.querySelector('.nav-section-item.active a') || sidebar.querySelector('.sidebar-nav a');
                    current?.focus({ preventScroll: true });
                    current?.scrollIntoView({ block: 'center' });
                }
            };
            const setCollapsed = collapsed => {
                if (collapsed) root.dataset.sidebar = 'collapsed';
                else delete root.dataset.sidebar;
                sidebarButton.setAttribute('aria-expanded', String(!collapsed));
                setButtonLabel(sidebarButton, collapsed ? 'Show book contents' : 'Hide book contents');
                saveSetting('book-sidebar', collapsed ? 'collapsed' : null);
            };
            const syncMode = () => {
                setDrawer(false);
                if (!DRAWER_QUERY.matches) {
                    sidebar.inert = false;
                    setCollapsed(root.dataset.sidebar === 'collapsed');
                }
            };
            sidebarButton.addEventListener('click', () => {
                if (DRAWER_QUERY.matches) setDrawer(!sidebar.classList.contains('show'));
                else setCollapsed(root.dataset.sidebar !== 'collapsed');
            });
            overlay.addEventListener('click', () => setDrawer(false));
            sidebar.querySelector('.drawer-close')?.addEventListener('click', () => { setDrawer(false); sidebarButton.focus(); });
            document.addEventListener('keydown', event => {
                if (event.key === 'Escape' && sidebar.classList.contains('show')) {
                    setDrawer(false);
                    sidebarButton.focus();
                }
            });
            sidebar.addEventListener('click', event => {
                if (DRAWER_QUERY.matches && event.target.closest('a')) setDrawer(false);
            });
            DRAWER_QUERY.addEventListener('change', syncMode);
            syncMode();
        }

        if (tocButton) {
            const setToc = collapsed => {
                if (collapsed) root.dataset.toc = 'collapsed';
                else delete root.dataset.toc;
                tocButton.setAttribute('aria-expanded', String(!collapsed));
                setButtonLabel(tocButton, collapsed ? 'Show “On this page”' : 'Hide “On this page”');
                saveSetting('book-toc', collapsed ? 'collapsed' : null);
            };
            tocButton.addEventListener('click', () => setToc(root.dataset.toc !== 'collapsed'));
            setToc(root.dataset.toc === 'collapsed');
        }

        if (themeButton) {
            const systemDark = window.matchMedia('(prefers-color-scheme: dark)');
            const applyTheme = theme => {
                root.dataset.theme = theme;
                const dark = theme === 'dark';
                themeButton.setAttribute('aria-pressed', String(dark));
                setButtonLabel(themeButton, dark ? 'Switch to light mode' : 'Switch to dark mode');
            };
            themeButton.addEventListener('click', () => {
                const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
                // Optimistic: the theme changes at once; saving follows and may fail quietly
                const swap = () => applyTheme(next);
                if (document.startViewTransition && !reduceMotion.matches) {
                    // the new theme spreads from the button that was pressed
                    const r = themeButton.getBoundingClientRect();
                    const x = r.left + r.width / 2, y = r.top + r.height / 2;
                    const radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
                    root.style.setProperty('--vt-x', `${x}px`);
                    root.style.setProperty('--vt-y', `${y}px`);
                    root.style.setProperty('--vt-r', `${radius}px`);
                    root.classList.add('theme-switching');
                    const transition = document.startViewTransition(swap);
                    transition.finished.finally(() => root.classList.remove('theme-switching'));
                } else {
                    swap();
                }
                saveSetting('book-theme', next === (systemDark.matches ? 'dark' : 'light') ? null : next);
            });
            systemDark.addEventListener('change', event => {
                let stored = null;
                try { stored = localStorage.getItem('book-theme'); } catch (e) {}
                if (!stored) applyTheme(event.matches ? 'dark' : 'light');
            });
            applyTheme(root.dataset.theme === 'dark' ? 'dark' : 'light');
        }
    }

    // ==========================================================================
    // Search: a command palette (ARIA 1.2 combobox + listbox in a modal dialog)
    // ==========================================================================

    let searchIndex = null;
    let searchLoading = null;

    function loadSearchIndex() {
        if (searchIndex) return Promise.resolve(true);
        if (!searchLoading) {
            searchLoading = fetchData('search.json')
                .then(response => response.ok ? response.json() : null)
                .then(data => { searchIndex = data; return !!data; })
                .catch(() => false);
        }
        return searchLoading;
    }

    function splitMath(text) {
        const parts = [];
        const pattern = /\\\(([\s\S]*?)\\\)|\\\[([\s\S]*?)\\\]/g;
        let last = 0, match;
        while ((match = pattern.exec(text))) {
            if (match.index > last) parts.push({ math: false, text: text.slice(last, match.index) });
            parts.push({ math: true, text: match[0] });
            last = pattern.lastIndex;
        }
        if (last < text.length) parts.push({ math: false, text: text.slice(last) });
        return parts;
    }

    function highlight(text, words) {
        return splitMath(text).map(part => {
            if (part.math) return escapeHtml(part.text);
            let html = escapeHtml(part.text);
            for (const word of words) {
                const pattern = new RegExp(escapeHtml(word).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
                html = html.replace(pattern, match => `<mark>${match}</mark>`);
            }
            return html;
        }).join('');
    }

    function snippetAround(text, index, before = 40, after = 120) {
        let start = Math.max(0, index - before);
        let end = Math.min(text.length, index + after);
        for (const pattern of [/\\\(([\s\S]*?)\\\)/g, /\\\[([\s\S]*?)\\\]/g]) {
            let match;
            while ((match = pattern.exec(text))) {
                const mStart = match.index, mEnd = pattern.lastIndex;
                if (mStart < start && mEnd > start) start = mStart;
                if (mStart < end && mEnd > end) end = mEnd;
            }
        }
        return (start > 0 ? '…' : '') + text.slice(start, end) + (end < text.length ? '…' : '');
    }

    function search(query) {
        if (!searchIndex || !query) return [];
        const words = query.toLowerCase().split(/\s+/).filter(Boolean);
        const results = [];
        for (const entry of searchIndex) {
            const title = (entry.title || '').toLowerCase();
            const content = (entry.content || '').toLowerCase();
            if (!words.every(w => title.includes(w) || content.includes(w))) continue;
            let score = 0;
            for (const w of words) score += title.includes(w) ? 10 : 1;
            if (title.includes(query.toLowerCase())) score += 15;
            if (title.startsWith(query.toLowerCase())) score += 5;
            if (entry.kind === 'result') score += 2;
            const hit = words.map(w => content.indexOf(w)).filter(i => i >= 0).sort((a, b) => a - b)[0];
            const snippet = snippetAround(entry.content || '', hit === undefined ? 0 : hit, hit === undefined ? 0 : 40);
            results.push({ ...entry, snippet, score });
        }
        return results.sort((a, b) => b.score - a.score).slice(0, 20);
    }

    const ENV_KINDS = { theorem: 'theorem', lemma: 'theorem', corollary: 'theorem', proposition: 'theorem', axiom: 'axiom',
        definition: 'definition', example: 'example', exercise: 'exercise', conjecture: 'theorem' };

    function setupSearch() {
        const palette = document.getElementById('palette');
        const input = document.getElementById('search-input');
        const list = document.getElementById('palette-list');
        const empty = palette?.querySelector('.palette-empty');
        const status = document.getElementById('palette-status');
        const panel = palette?.querySelector('.palette-panel');
        const trigger = document.querySelector('.search-trigger');
        if (!palette || !input || !list) return;

        let options = [];
        let active = -1;
        let closeTimer = 0;
        let returnFocus = null;
        let typed = 0;

        const setActive = (index, scroll = true) => {
            if (!options.length) { active = -1; input.removeAttribute('aria-activedescendant'); return; }
            active = (index + options.length) % options.length;
            options.forEach((option, i) => option.setAttribute('aria-selected', String(i === active)));
            input.setAttribute('aria-activedescendant', options[active].id);
            if (scroll) options[active].scrollIntoView({ block: 'nearest' });
        };

        const optionHtml = (item, index, words) => {
            const kind = item.kind === 'result' ? 'result' : (item.kind || 'page');
            const env = kind === 'result' ? (ENV_KINDS[(item.title || '').split(/\s+/)[0].toLowerCase()] || 'theorem') : '';
            const icon = kind === 'result' ? 'bi-sigma' : kind === 'recent' ? 'bi-clock' : kind === 'chapter' ? 'bi-book' : 'bi-file-text';
            const where = item.page ? `<span class="palette-where">${escapeHtml(item.page.replace(/^(\d+(\.\d+)*)\s.*$/, '§ $1'))}</span>`
                : '<span class="palette-enter"><i class="bi bi-corner" aria-hidden="true"></i></span>';
            return `<div class="palette-option" role="option" id="palette-option-${index}" aria-selected="false" data-href="${escapeHtml(item.href)}" data-kind="${kind}"${env ? ` data-env="${env}"` : ''}>`
                + `<span class="palette-icon" aria-hidden="true"><i class="bi ${icon}"></i></span>`
                + `<span class="palette-text"><span class="palette-title">${words ? highlight(item.title, words) : item.titleHtml || escapeHtml(item.title)}</span>`
                + (item.snippet ? `<span class="palette-snippet">${words ? highlight(item.snippet, words) : escapeHtml(item.snippet)}</span>` : '')
                + `</span>${where}</div>`;
        };

        const render = (groups, words, stagger) => {
            let index = 0;
            list.innerHTML = groups.filter(g => g.items.length).map((group, g) =>
                `<div role="group" aria-labelledby="palette-group-${g}"><div class="palette-group" id="palette-group-${g}" aria-hidden="true">${escapeHtml(group.label)}</div>`
                + group.items.map(item => optionHtml(item, index++, words)).join('') + '</div>').join('');
            options = [...list.querySelectorAll('[role="option"]')];
            if (stagger && !reduceMotion.matches) {
                options.slice(0, 8).forEach((option, i) => { option.classList.add('enter'); option.style.setProperty('--i', i); });
            }
            input.setAttribute('aria-expanded', String(options.length > 0));
            setActive(0, false);
            list.scrollTop = 0;
            if (/\\\(|\\\[/.test(list.textContent)) {
                ensureMathJax().then(mj => {
                    if (!mj) return;
                    mj.typesetClear?.([list]);
                    mj.typesetPromise([list]).catch(() => {});
                });
            }
        };

        /** No query yet: recent pages, then the chapters (from the contents pane). */
        const renderStart = stagger => {
            const base = getBasePath();
            const here = currentPagePath();
            const recent = readJson(`atlas:recent:${bookKey()}`, [])
                .filter(e => e && e.path && e.path !== here).slice(0, 5)
                .map(e => ({ kind: 'recent', title: (e.number ? `${e.number} ` : '') + e.title, href: base + e.path }));
            const chapters = [...document.querySelectorAll('.sidebar-nav .nav-chapter')].map(ch => {
                const link = ch.querySelector('.nav-chapter-title-link');
                const number = ch.querySelector('.nav-chapter-number')?.textContent.trim();
                return { kind: 'chapter', title: (number ? `${number} ` : '') + link.textContent.replace(/\s+/g, ' ').trim().replace(/^\d+\s*/, ''),
                    titleHtml: (number ? `<span class="nav-page-num">${number}</span> ` : '') + (ch.querySelector('.nav-chapter-title')?.innerHTML || ''),
                    href: link.getAttribute('href') };
            });
            render([{ label: 'Recent', items: recent }, { label: 'Chapters', items: chapters }], null, stagger);
            empty.hidden = true;
            status.textContent = '';
        };

        const run = async () => {
            const query = input.value.trim();
            const ticket = ++typed;
            if (query.length < 2) { renderStart(false); return; }
            await loadSearchIndex();
            if (ticket !== typed) return;
            const words = query.split(/\s+/).filter(Boolean);
            const base = getBasePath();
            const results = search(query).map(r => ({ ...r, href: base + r.url }));
            const pages = results.filter(r => r.kind !== 'result').slice(0, 6);
            const found = results.filter(r => r.kind === 'result').slice(0, 12);
            render([{ label: 'Sections', items: pages }, { label: 'Results', items: found }], words, false);
            const total = pages.length + found.length;
            empty.hidden = total > 0;
            empty.textContent = total ? '' : `No sections or results match “${query}”.`;
            status.textContent = total ? `${total} result${total === 1 ? '' : 's'}` : 'No results';
        };

        let debounce = 0;
        input.addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(run, 90); });

        const open = from => {
            clearTimeout(closeTimer);
            returnFocus = document.activeElement;
            palette.hidden = false;
            // the panel grows out of the button that opened it (or the top centre)
            const p = panel.getBoundingClientRect();
            if (from && from.getBoundingClientRect) {
                const r = from.getBoundingClientRect();
                const ox = r.left + r.width / 2 - p.left, oy = r.top + r.height / 2 - p.top;
                panel.style.setProperty('--palette-origin', `${Math.round(ox)}px ${Math.round(oy)}px`);
            } else {
                panel.style.setProperty('--palette-origin', '50% 0');
            }
            void panel.offsetWidth;
            const wasOpen = palette.classList.contains('is-open');
            palette.classList.add('is-open');
            // lock scrolling; the scrollbar's width becomes padding, so nothing shifts sideways
            if (!wasOpen) {
                const bar = window.innerWidth - document.documentElement.clientWidth;
                document.documentElement.style.overflow = 'hidden';
                if (bar > 0) document.documentElement.style.paddingRight = `${bar}px`;
            }
            trigger?.setAttribute('aria-expanded', 'true');
            loadSearchIndex();
            if (!wasOpen) {
                if (input.value.trim().length >= 2) run(); else renderStart(true);
            }
            input.focus({ preventScroll: true });
            input.select();
        };

        const close = () => {
            if (!palette.classList.contains('is-open')) return;
            palette.classList.remove('is-open');
            document.documentElement.style.overflow = '';
            document.documentElement.style.paddingRight = '';
            trigger?.setAttribute('aria-expanded', 'false');
            input.setAttribute('aria-expanded', 'false');
            clearTimeout(closeTimer);
            closeTimer = setTimeout(() => { palette.hidden = true; }, 220);
            (returnFocus && document.contains(returnFocus) ? returnFocus : trigger)?.focus({ preventScroll: true });
        };

        const go = option => {
            if (!option) return;
            const href = option.dataset.href;
            close();
            const url = new URL(href, location.href);
            if (url.pathname === location.pathname && url.hash) {
                history.pushState(null, '', url.hash);
                markTargetFromHash();
                document.getElementById(decodeURIComponent(url.hash.slice(1)))?.scrollIntoView({ block: 'start' });
            } else {
                lastClicked = null;
                location.href = href;
            }
        };

        trigger?.addEventListener('click', event => open(event.detail === 0 ? null : trigger));
        palette.querySelectorAll('[data-close]').forEach(el => el.addEventListener('click', close));
        list.addEventListener('pointermove', event => {
            const option = event.target.closest('[role="option"]');
            if (option && option.getAttribute('aria-selected') !== 'true') setActive(options.indexOf(option), false);
        });
        list.addEventListener('click', event => go(event.target.closest('[role="option"]')));

        input.addEventListener('keydown', event => {
            const key = event.key;
            if (key === 'ArrowDown' || (event.ctrlKey && key === 'n')) { event.preventDefault(); setActive(active + 1); }
            else if (key === 'ArrowUp' || (event.ctrlKey && key === 'p')) { event.preventDefault(); setActive(active - 1); }
            else if (key === 'PageDown') { event.preventDefault(); setActive(Math.min(options.length - 1, active + 5)); }
            else if (key === 'PageUp') { event.preventDefault(); setActive(Math.max(0, active - 5)); }
            else if (key === 'Enter') { event.preventDefault(); go(options[active] || options[0]); }
            else if (key === 'Escape') {
                event.preventDefault();
                event.stopPropagation();
                if (input.value) { input.value = ''; renderStart(false); } else close();
            } else if (key === 'Tab') {
                event.preventDefault();   // the dialog holds focus: the field is the one stop
            }
        });

        document.addEventListener('keydown', event => {
            const typing = event.target.closest?.('input, textarea, select, [contenteditable="true"]');
            if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
                event.preventDefault();
                if (palette.classList.contains('is-open')) close(); else open(null);
            } else if (event.key === '/' && !typing && !event.metaKey && !event.ctrlKey && !event.altKey) {
                event.preventDefault();
                open(null);
            } else if (event.key === 'Escape' && palette.classList.contains('is-open')) {
                close();
            }
        });
    }

    // ==========================================================================
    // Results page filters (build/extras.py)
    // ==========================================================================

    function setupResultsFilters() {
        const filters = document.querySelector('.results-filters');
        if (!filters) return;
        const checkboxes = [...filters.querySelectorAll('input[type="checkbox"]')];
        const searchBox = filters.querySelector('.results-search');
        const empty = document.querySelector('.results-empty');
        const apply = () => {
            const groups = new Set(checkboxes.filter(c => c.checked).map(c => c.value));
            const words = searchBox.value.toLowerCase().split(/\s+/).filter(Boolean);
            let shown = 0;
            document.querySelectorAll('.result').forEach(item => {
                const visible = groups.has(item.dataset.group) && words.every(w => item.dataset.search.includes(w));
                item.hidden = !visible;
                if (visible) shown++;
            });
            document.querySelectorAll('.results-section, .results-chapter').forEach(block => {
                block.hidden = !block.querySelector('.result:not([hidden])');
            });
            empty.hidden = shown > 0;
        };
        checkboxes.forEach(c => c.addEventListener('change', apply));
        searchBox.addEventListener('input', apply);
    }

    // ==========================================================================
    // Page transitions: the followed link becomes the next page's title
    // ==========================================================================

    let lastClicked = null;

    function setupPageTransitions() {
        document.addEventListener('click', event => {
            const link = event.target.closest?.('a[href]');
            lastClicked = link && !event.defaultPrevented ? link : null;
        });
        // pageswap fires on the old page just before its snapshot (Chrome 124+)
        window.addEventListener('pageswap', event => {
            if (!event.viewTransition || reduceMotion.matches) return;
            const link = lastClicked;
            const source = link && (link.querySelector('.nav-page-title') || link.querySelector('.nav-section-title')
                || link.querySelector('.cs-title') || link.querySelector('.nav-chapter-title'));
            if (!source) return;
            const title = document.querySelector('.quarto-title h1 .chapter-title');
            if (title) title.style.viewTransitionName = 'none';
            source.style.viewTransitionName = 'page-title';
            event.viewTransition.finished.finally(() => {
                source.style.viewTransitionName = '';
                if (title) title.style.viewTransitionName = '';
            });
        });
    }

    // ==========================================================================
    // Start
    // ==========================================================================

    async function init() {
        setupLayoutControls();
        setupPageTransitions();
        if (!hydrateSidebarNav() && await loadNavigation()) buildSidebarNav();

        setupArrowKeys();
        setupTheoremTitles();
        setupFolding();
        setupSmallLabels();
        setupFoldLinks();
        setupExerciseChecks();
        setupChapterOpening();
        setupSectionTabs();
        buildTableOfContents();
        if (selectSectionTab) {
            selectSectionTab(document.querySelector('.section-tab[aria-selected="true"]')?.dataset.tab || 'reading');
        }
        setupDoneToggle();
        recordRecent();
        setupReadProgress();

        wrapTables();
        glueMathPunctuation();
        setupWideInlineMath();
        setupMathCopy();
        setupMathSelection();
        setupResultsFilters();

        setupAnchorLinks();
        markTargetFromHash();
        window.addEventListener('hashchange', markTargetFromHash);

        setupPeeks();
        setupSmoothScrolling();
        setupSearch();
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
