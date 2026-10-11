/**
 * Book Navigation & Tooltip System
 * =================================
 * Loads navigation manifest and builds sidebar dynamically.
 * Loads theorem manifest and attaches Tippy.js tooltips to cross-references.
 */

(function () {
    'use strict';

    // ==========================================================================
    // Configuration
    // ==========================================================================

    const TOOLTIP_CONFIG = {
        theme: 'quarto',
        placement: 'top',
        animation: 'shift-away',
        interactive: true,
        allowHTML: true,
        maxWidth: 550,
        delay: [100, 0],
        appendTo: document.body,
    };

    // ==========================================================================
    // Navigation Manifest Loading
    // ==========================================================================

    let navigationData = null;

    /**
     * Get the base path to the root of the HTML output directory (set by the build)
     */
    function getBasePath() {
        const meta = document.querySelector('meta[name="asset-prefix"]');
        return meta ? meta.content : './';
    }

    /**
     * Fetch a site-wide data file.
     *
     * The URL carries the build's asset version, exactly as styles.css and main.js do, so
     * the browser may cache it outright. This used to pass 'no-cache' to stay fresh, which
     * cost a revalidation round trip on every fetch on every page; the version query gives
     * the same freshness for nothing.
     */
    function assetVersion() {
        const meta = document.querySelector('meta[name="asset-version"]');
        return meta ? meta.content : '';
    }

    function fetchData(name) {
        const version = assetVersion();
        return fetch(getBasePath() + name + (version ? `?v=${encodeURIComponent(version)}` : ''));
    }

    /**
     * Load the navigation manifest JSON file
     */
    async function loadNavigation() {
        try {
            const response = await fetchData('navigation.json');
            if (response.ok) {
                navigationData = await response.json();
                console.log(`Loaded navigation: ${navigationData.chapters.length} chapters`);
                return true;
            }
        } catch (error) {
            console.warn('Could not load navigation manifest:', error);
        }
        return false;
    }

    /**
     * Determine which page is currently active
     */
    function getCurrentPagePath() {
        const path = window.location.pathname;
        // Extract the relevant part (e.g., "ch01-vector-spaces/07-sums-and-direct-sums.html")
        const match = path.match(/([^/]+\/[^/]+\.html)$/);
        return match ? match[1] : null;
    }

    /**
     * Build the sidebar navigation HTML
     */
    /**
     * Adopt a sidebar that the build already rendered: attach the toggles and scroll the
     * current section into view. Returns false if this page has no server-rendered tree,
     * in which case the caller falls back to fetching navigation.json and building it.
     */
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

    function buildSidebarNav() {
        if (!navigationData) return;

        const sidebarNav = document.querySelector('.sidebar-nav');
        if (!sidebarNav) return;

        const currentPath = getCurrentPagePath();
        const basePath = getBasePath();

        let html = '<ul class="nav-list">';

        // Add Preface link
        const home = navigationData.home || { title: 'Preface', path: 'index.html' };
        html += `<li class="nav-item nav-home">
            <a href="${basePath}${home.path}">${home.title}</a>
        </li>`;
        for (const extra of navigationData.extras || []) {
            const active = currentPagePath() === extra.path ? ' active' : '';
            html += `<li class="nav-item nav-extra${active}">
                <a href="${basePath}${extra.path}"><i class="bi ${extra.icon}" aria-hidden="true"></i> ${extra.title}</a>
            </li>`;
        }

        navigationData.chapters.forEach((chapter, chapterIdx) => {
            const isChapterActive = chapter.sections.some(s => s.path === currentPath);
            const isExpanded = isChapterActive || !chapter.collapsed;

            // Chapter header with title on left (link), toggle arrow on right (button)
            // If chapter has its own index page (chapter.path), title links there. Otherwise, links to first section.
            const firstSection = chapter.sections[0];
            const chapterUrl = chapter.path ? (basePath + chapter.path) : (firstSection ? (basePath + firstSection.path) : '#');

            if (chapter.part) {
                html += `<li class="nav-part">${chapter.part}</li>`;
            }
            html += `
                <li class="nav-chapter${isChapterActive ? ' active' : ''}">
                    <div class="nav-chapter-header" data-chapter="${chapterIdx}">
                        <a href="${chapterUrl}" class="nav-chapter-title-link">
                            <span class="nav-chapter-title">${chapter.title}</span>
                        </a>
                        <span class="nav-toggle ${isExpanded ? 'expanded' : ''}">
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="9 18 15 12 9 6"></polyline>
                            </svg>
                        </span>
                    </div>
                    <ul class="nav-sections ${isExpanded ? '' : 'collapsed'}">
            `;

            chapter.sections.forEach(section => {
                const isActive = section.path === currentPath;
                // Avoid duplicating if the chapter title already links to this index page
                // But user might want it in list too. Let's keep all sections in list.
                const sectionPath = basePath + section.path;

                html += `
                    <li class="nav-section-item${isActive ? ' active' : ''}">
                        <a href="${sectionPath}" title="${section.title}">
                            <span class="nav-section-number">${section.number}</span>
                            <span class="nav-section-title">${section.title}</span>
                        </a>
                    </li>
                `;
            });

            html += '</ul></li>';
        });

        html += '</ul>';
        sidebarNav.innerHTML = html;

        // Keep the current section in view in a long sidebar
        scrollActiveSectionIntoView(sidebarNav);

        // Add click handlers for chapter expansion (ONLY on toggle arrow)
        setupChapterToggle();
    }

    /**
     * Setup chapter toggle (expand/collapse)
     */
    function setupChapterToggle() {
        document.querySelectorAll('.nav-toggle').forEach(toggle => {
            toggle.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();

                const header = toggle.closest('.nav-chapter-header');
                const sections = header.nextElementSibling;

                toggle.classList.toggle('expanded');
                sections.classList.toggle('collapsed');
            });
        });
    }

    /**
     * Update the book title in sidebar header
     */
    function updateSidebarHeader() {
        if (!navigationData) return;

        const sidebarTitle = document.querySelector('.sidebar-title');
        if (sidebarTitle && navigationData.title) {
            sidebarTitle.textContent = navigationData.title;
        }
    }

    // ==========================================================================
    // Table of Contents (Right Sidebar)
    // ==========================================================================

    /**
     * Build table of contents from page headings
     */
    function buildTableOfContents() {
        const tocContainer = document.querySelector('.toc');
        if (!tocContainer) return;

        // Find all h2 and h3 headings in the main content
        const content = document.querySelector('.content');
        if (!content) return;

        const headings = content.querySelectorAll('h2, h3');
        if (headings.length === 0) return;

        let html = '<h2>On this page</h2><ul class="toc-list">';

        headings.forEach(heading => {
            const level = heading.tagName.toLowerCase();
            const id = heading.id || heading.textContent.toLowerCase().replace(/[^a-z0-9]+/g, '-');
            heading.id = id;  // Ensure heading has an ID

            const indent = level === 'h3' ? ' toc-indent' : '';
            html += `
                <li class="toc-item${indent}">
                    <a href="#${id}">${heading.textContent}</a>
                </li>
            `;
        });

        html += '</ul>';
        tocContainer.innerHTML = html;

        // Setup scroll spy
        setupScrollSpy(headings);
    }

    /**
     * Highlight the current section in the TOC as user scrolls
     */
    function setupScrollSpy(headings) {
        if (headings.length === 0) return;

        const headingArray = Array.from(headings);
        let ticking = false;

        function updateActiveHeading() {
            // Find the heading that is currently at or just above the viewport top
            const scrollY = window.scrollY;
            const offset = 100; // Offset from top to trigger

            let currentHeading = null;

            for (let i = headingArray.length - 1; i >= 0; i--) {
                const heading = headingArray[i];
                if (heading.closest('.tab-panel[hidden]')) continue;
                const rect = heading.getBoundingClientRect();
                const headingTop = rect.top + scrollY;

                if (headingTop <= scrollY + offset) {
                    currentHeading = heading;
                    break;
                }
            }

            // If no heading is above viewport, use the first one
            if (!currentHeading) {
                currentHeading = headingArray.find(h => !h.closest('.tab-panel[hidden]')) || null;
            }

            // Update TOC active state
            if (currentHeading) {
                const id = currentHeading.id;
                const tocLink = document.querySelector(`.toc a[href="#${id}"]`);

                // Only update if changed
                const currentActive = document.querySelector('.toc a.active');
                if (tocLink && tocLink !== currentActive) {
                    document.querySelectorAll('.toc a.active').forEach(a => a.classList.remove('active'));
                    tocLink.classList.add('active');
                }
            }

            ticking = false;
        }

        function onScroll() {
            if (!ticking) {
                requestAnimationFrame(updateActiveHeading);
                ticking = true;
            }
        }

        window.addEventListener('scroll', onScroll, { passive: true });

        // Initial update
        updateActiveHeading();
    }

    // ==========================================================================
    // Theorem Manifest & Tooltips
    // ==========================================================================

    // Tooltip data is one small file per result (theorems/<chapter>/<label>.json), fetched the
    // first time that result is hovered. It used to be one file per chapter, so a single hover
    // pulled up to 2.8 MB to read one ~12 KB entry. sessionStorage carries entries across page
    // navigations, which the in-memory map alone could not do.
    const theoremEntries = new Map();  // labelId -> Promise of info (or null)

    function cached(labelId) {
        try {
            const stored = sessionStorage.getItem(`thm:${assetVersion()}:${labelId}`);
            return stored ? JSON.parse(stored) : undefined;
        } catch (error) {
            return undefined;   // private windows, blocked storage, quota
        }
    }

    function remember(labelId, info) {
        try {
            sessionStorage.setItem(`thm:${assetVersion()}:${labelId}`, JSON.stringify(info));
        } catch (error) {
            /* a full or unavailable store is not worth reporting: the fetch still worked */
        }
    }

    // `base` is set for a reference into another book (a.xref-external, data-base): its
    // site's root, from which the same theorems/<chapter>/<label>.json is fetched. That
    // works on a shared origin (a library of books under one domain) and wherever the other
    // site allows cross-origin reads; when the fetch fails the link stays a plain link.
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
                    .then(info => {
                        if (info && !base) remember(labelId, info);
                        return info;
                    })
                    .catch(error => {
                        console.warn(`Could not load theorem data for ${labelId}:`, error);
                        return null;
                    }));
            }
        }
        return theoremEntries.get(key);
    }

    /**
     * Generate tooltip HTML content for a theorem reference
     */
    function generateTooltipContent(refId, info, goTo, book) {

        if (!info) {
            return `<div class="tooltip-error">Reference not found: ${refId}</div>`;
        }

        // Build title (title_html keeps math in titles typesettable)
        let title = info.type_name || (info.type.charAt(0).toUpperCase() + info.type.slice(1));
        if (info.number) {
            title += ` ${info.number}`;
        }
        if (info.title_html || info.title) {
            title += ` (${info.title_html || info.title})`;
        }
        if (book) {
            title = `${book}, ${title}`;   // a result of another book (a.xref-external)
        }

        const footer = goTo
            ? `<a class="tooltip-go" href="${goTo.href}">Go to ${goTo.label} <i class="bi bi-arrow-right-short" aria-hidden="true"></i></a>`
            : '';
        return `
            <div class="tooltip-theorem ${info.type}">
                <div class="tooltip-title">${title}</div>
                <div class="tooltip-content">${info.html || 'Content not available'}</div>
                ${footer}
            </div>
        `;
    }

    /**
     * Create loading placeholder
     */
    function createLoadingContent() {
        return `
            <div class="tooltip-loading">
                <div class="spinner"></div>
                <span>Loading...</span>
            </div>
        `;
    }

    /**
     * Attach tooltips to all cross-reference links
     */
    function attachTooltips() {
        if (typeof tippy === 'undefined') {
            console.warn('Tippy.js not loaded, skipping tooltips');
            return;
        }

        const xrefLinks = document.querySelectorAll('a.xref[data-ref]');
        // Without hover (phones, tablets) the first tap opens the preview, which has a
        // "Go to" link; with a mouse, hovering previews and clicking follows the link.
        const touch = window.matchMedia('(hover: none)').matches;

        xrefLinks.forEach(link => {
            const refId = link.dataset.ref;
            const shard = link.dataset.shard;
            const base = link.dataset.base || '';
            const book = link.dataset.book || '';
            const goTo = touch ? { href: link.getAttribute('href'), label: link.textContent.trim() } : null;
            const preventTap = event => event.preventDefault();
            if (touch) link.addEventListener('click', preventTap);

            tippy(link, {
                ...TOOLTIP_CONFIG,
                ...(touch ? { trigger: 'click', hideOnClick: true, placement: 'bottom', maxWidth: 'calc(100vw - 24px)' } : {}),
                content: createLoadingContent(),
                onShow(instance) {
                    loadEntry(shard, refId, base).then(info => {
                        if (!info && base) {
                            // Another book's preview could not be fetched (offline, or a
                            // cross-origin site that does not allow it): no tooltip, the
                            // link still goes there.
                            instance.hide();
                            instance.disable();
                            if (touch) link.removeEventListener('click', preventTap);
                            return;
                        }
                        instance.setContent(generateTooltipContent(refId, info, goTo, book));
                        // Typeset math in the tooltip
                        const tooltipEl = instance.popper.querySelector('.tippy-content');
                        if (tooltipEl && window.MathJax && window.MathJax.typesetPromise) {
                            MathJax.typesetPromise([tooltipEl]).catch(err => {
                                console.warn('MathJax typeset error:', err);
                            });
                        }
                    });
                }
            });
        });

        console.log(`Attached tooltips to ${xrefLinks.length} cross-references`);
    }

    // ==========================================================================
    // Smooth Scrolling for Internal Links
    // ==========================================================================

    function setupSmoothScrolling() {
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function (e) {
                const targetId = decodeURIComponent(this.getAttribute('href').slice(1));
                const target = document.getElementById(targetId);

                if (target) {
                    e.preventDefault();
                    revealTabFor(target);
                    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
                    target.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });

                    // Update URL without jumping
                    history.pushState(null, null, `#${targetId}`);
                    markTarget(target);
                }
            });
        });
    }

    // ==========================================================================
    // List of Results: filters
    // ==========================================================================

    function setupResultsFilters() {
        const filters = document.querySelector('.results-filters');
        if (!filters) return;
        const checkboxes = [...filters.querySelectorAll('input[type="checkbox"]')];
        const search = filters.querySelector('.results-search');
        const empty = document.querySelector('.results-empty');

        const apply = () => {
            const groups = new Set(checkboxes.filter(c => c.checked).map(c => c.value));
            const words = search.value.toLowerCase().split(/\s+/).filter(Boolean);
            let shown = 0;
            document.querySelectorAll('.result').forEach(item => {
                const visible = groups.has(item.dataset.group)
                    && words.every(w => item.dataset.search.includes(w));
                item.hidden = !visible;
                if (visible) shown++;
            });
            document.querySelectorAll('.results-section, .results-chapter').forEach(block => {
                block.hidden = !block.querySelector('.result:not([hidden])');
            });
            empty.hidden = shown > 0;
        };
        checkboxes.forEach(c => c.addEventListener('change', apply));
        search.addEventListener('input', apply);
    }

    // ==========================================================================
    // Foldable Proofs and Solutions
    // ==========================================================================

    /**
     * Proofs can be hidden and solutions start hidden, so readers can try an example first.
     * Only outermost blocks fold (a claim's proof inside a proof stays with its proof).
     * The block's own label ("Proof." / "Solution.") becomes the toggle, followed by a small
     * chevron: v while folded, ^ while open.
     */
    const CHEVRON = '<svg viewBox="0 0 12 12" aria-hidden="true" focusable="false">'
        + '<path d="M2.75 4.5 6 7.75 9.25 4.5" fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round"/></svg>';

    function setupFolding() {
        const blocks = document.querySelectorAll('.content .proof.small-env, .content .solution.small-env');
        blocks.forEach(block => {
            if (block.parentElement.closest('.proof, .solution')) return;
            const first = block.firstElementChild;
            if (!first || first.tagName !== 'P') return;
            // The label runs from the start of the first paragraph to the italic "." after it
            const nodes = [...first.childNodes];
            const end = nodes.findIndex(n => n.nodeType === Node.ELEMENT_NODE && n.tagName === 'EM'
                && n.textContent.trim() === '.');
            if (end < 0) return;

            const kind = block.classList.contains('solution') ? 'solution' : 'proof';
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'fold-toggle';
            const label = document.createElement('span');
            label.className = 'fold-label';
            nodes.slice(0, end + 1).forEach(node => label.append(node));
            const chevron = document.createElement('span');
            chevron.className = 'fold-chevron';
            chevron.innerHTML = CHEVRON;
            button.append(label, chevron);

            // The rest of the first paragraph, hidden while folded
            const rest = document.createElement('span');
            rest.className = 'fold-rest';
            while (first.firstChild) rest.append(first.firstChild);
            first.append(button, rest);
            first.classList.add('fold-head');
            block.classList.add('foldable');

            const set = folded => {
                block.classList.toggle('is-folded', folded);
                button.setAttribute('aria-expanded', String(!folded));
                button.title = `${folded ? 'Show' : 'Hide'} ${kind}`;
            };
            button.addEventListener('click', () => set(!block.classList.contains('is-folded')));
            block.addEventListener('unfold', () => set(false));
            set(kind === 'solution');
        });
    }

    /** Open any folded block containing the element. */
    function unfoldAround(element) {
        for (let block = element?.closest('.is-folded'); block; block = block.parentElement?.closest('.is-folded')) {
            block.dispatchEvent(new Event('unfold'));
        }
    }

    // ==========================================================================
    // Reading Progress and Keyboard Navigation
    // ==========================================================================

    function readJson(key, fallback) {
        try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (e) { return fallback; }
    }

    function currentPagePath() {
        return document.querySelector('meta[name="page-path"]')?.content || '';
    }

    /**
     * Copying a passage that contains formulas puts their LaTeX source on the clipboard
     * (the rendered glyphs carry no text of their own). The build stores each formula's
     * source in data-tex; see build/render_math.cjs.
     */
    function setupMathCopy() {
        const BREAK = ' ';  // marks a paragraph boundary while whitespace is collapsed
        document.addEventListener('copy', event => {
            const selection = window.getSelection();
            if (!selection || selection.isCollapsed || !event.clipboardData) return;
            const fragment = selection.getRangeAt(0).cloneContents();
            if (!fragment.querySelector('mjx-container[data-tex]')) return;  // no maths: copy as usual

            fragment.querySelectorAll('mjx-assistive-mml, .fold-toggle, .anchor-link, .tab-continue')
                .forEach(node => node.remove());
            fragment.querySelectorAll('mjx-container[data-tex]').forEach(node => {
                const tex = node.getAttribute('data-tex').replace(/\s+/g, ' ').trim();
                const display = node.getAttribute('display') === 'true';
                node.replaceWith(document.createTextNode(
                    display ? `${BREAK}\\[ ${tex} \\]${BREAK}` : `\\( ${tex} \\)`));
            });
            const wrapper = document.createElement('div');
            wrapper.append(fragment);
            // A blank line between blocks; everything else collapses to single spaces
            wrapper.querySelectorAll('p, li, h1, h2, h3, h4, h5, h6, blockquote, .env, .small-env, .tikz-figure')
                .forEach(block => block.append(document.createTextNode(BREAK)));
            const text = wrapper.textContent
                .replace(/\s+/g, ' ')
                .split(BREAK).map(part => part.trim()).filter(Boolean)
                .join('\n\n');
            event.clipboardData.setData('text/plain', text);
            event.preventDefault();
        });
    }

    /** Left and right arrow keys go to the previous and next page. */
    function setupArrowKeys() {
        document.addEventListener('keydown', event => {
            if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
            if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
            const target = event.target;
            if (target.closest('input, textarea, select, [contenteditable="true"], .code-cell, .plot, .widget, [role="tab"]')) return;
            if (document.body.classList.contains('drawer-open')) return;
            // Leave horizontal scrolling of a focused wide equation alone
            if (target !== document.body && target.scrollWidth > target.clientWidth) return;
            const link = document.querySelector(event.key === 'ArrowLeft'
                ? '.nav-page-previous .pagination-link' : '.nav-page-next .pagination-link');
            if (link) {
                event.preventDefault();
                window.location.href = link.href;
            }
        });
    }

    // ==========================================================================
    // MathJax on Demand
    // ==========================================================================

    /**
     * On pages whose math was rendered at build time, MathJax is loaded only when text that
     * was not rendered needs it (search snippets). Resolves to MathJax, or null.
     */
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

    // ==========================================================================
    // Wide Inline Formulas
    // ==========================================================================

    /**
     * MathJax cannot break inline formulas across lines. On narrow screens a long one
     * overflows the column and is clipped; mark those so they scroll sideways instead.
     */
    function setupWideInlineMath() {
        const prerendered = document.querySelector('meta[name="math-prerendered"]');
        if (!prerendered && !window.MathJax) return;
        const update = () => {
            document.querySelectorAll('.content mjx-container:not([display="true"])').forEach(math => {
                math.classList.remove('wide-inline');
                const column = math.closest('li, p, .env, .small-env, .content');
                if (column && math.getBoundingClientRect().width > column.clientWidth) {
                    math.classList.add('wide-inline');
                }
            });
        };
        if (prerendered) {
            // Formulas are already in the page; measure once fonts have loaded
            document.fonts.ready.then(update);
        } else {
            const whenReady = () => MathJax.startup?.promise?.then(update);
            if (MathJax.startup?.promise) whenReady();
            else window.addEventListener('load', whenReady);
        }
        let timer;
        window.addEventListener('resize', () => { clearTimeout(timer); timer = setTimeout(update, 200); });
    }

    // ==========================================================================
    // Link Anchors and Targets
    // ==========================================================================

    /** Briefly highlight the theorem or heading a link led to. */
    function markTarget(element) {
        document.querySelectorAll('.is-target').forEach(el => el.classList.remove('is-target'));
        if (!element) return;
        unfoldAround(element);
        void element.offsetWidth;  // restart the animation when the same target is chosen again
        element.classList.add('is-target');
    }

    function markTargetFromHash() {
        if (location.hash.length > 1) {
            const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
            if (target && revealTabFor(target)) target.scrollIntoView({ block: 'start' });
            markTarget(target);
        }
    }

    // ==========================================================================
    // Reading / Exercises tabs
    // ==========================================================================

    let selectSectionTab = null;

    /** Show the tab that contains the element. Returns true if the tab had to change. */
    function revealTabFor(element) {
        const panel = element?.closest('.tab-panel');
        if (!panel || !panel.hidden || !selectSectionTab) return false;
        selectSectionTab(panel.dataset.tab);
        return true;
    }

    /**
     * A section page whose last part is "Exercises" gets two tabs under its title: the text
     * and the exercises. Without JavaScript, and in print, both stay on one page.
     */
    function setupSectionTabs() {
        const content = document.querySelector('.content');
        const heading = content?.querySelector(':scope > h2#exercises');
        if (!heading) return;

        const makePanel = (name, label) => {
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
        while (node && node !== heading) {
            const next = node.nextSibling;
            reading.append(node);
            node = next;
        }
        while (node) {
            const next = node.nextSibling;
            exercises.append(node);
            node = next;
        }

        const count = exercises.querySelectorAll('.exercise.env').length;
        const bar = document.createElement('div');
        bar.className = 'section-tabs';
        bar.setAttribute('role', 'tablist');
        bar.setAttribute('aria-label', 'Section parts');
        const makeTab = (name, text, badge) => {
            const tab = document.createElement('button');
            tab.type = 'button';
            tab.className = 'section-tab';
            tab.id = `tab-${name}`;
            tab.dataset.tab = name;
            tab.setAttribute('role', 'tab');
            tab.setAttribute('aria-controls', `tab-panel-${name}`);
            tab.innerHTML = `<i class="bi ${name === 'reading' ? 'bi-book' : 'bi-pencil-square'}" aria-hidden="true"></i><span>${text}</span>`
                + (badge ? `<span class="tab-count">${badge}</span>` : '');
            return tab;
        };
        const tabs = [makeTab('reading', 'Reading'), makeTab('exercises', 'Exercises', count || '')];
        bar.append(...tabs);

        // At the end of the text, an invitation to the exercises
        const next = document.createElement('button');
        next.type = 'button';
        next.className = 'tab-continue';
        next.innerHTML = `<span>Continue to the exercises</span><i class="bi bi-arrow-right" aria-hidden="true"></i>`;
        reading.append(next);

        if (header) header.after(bar, reading, exercises);
        else content.prepend(bar, reading, exercises);

        const tocLinks = () => document.querySelectorAll('.toc a[href^="#"]');
        const select = (name, { scroll = false, updateHash = false } = {}) => {
            for (const tab of tabs) {
                const on = tab.dataset.tab === name;
                tab.setAttribute('aria-selected', String(on));
                tab.tabIndex = on ? 0 : -1;
            }
            reading.hidden = name !== 'reading';
            exercises.hidden = name !== 'exercises';
            // Dim the "On this page" entries that belong to the other tab
            tocLinks().forEach(link => {
                const target = document.getElementById(decodeURIComponent(link.getAttribute('href').slice(1)));
                link.closest('li')?.classList.toggle('toc-other-tab', !!target?.closest('.tab-panel[hidden]'));
            });
            if (updateHash) {
                history.replaceState(null, '', name === 'exercises' ? '#exercises' : location.pathname + location.search);
            }
            if (scroll && bar.getBoundingClientRect().top < 0) {
                bar.scrollIntoView({ block: 'start' });
            }
            window.dispatchEvent(new Event('scroll'));  // refresh the table-of-contents highlight
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
            bar.scrollIntoView({ block: 'start', behavior: 'smooth' });
        });

        select('reading');
    }

    /**
     * A "#" link after each heading and theorem title. Clicking it goes to the element and
     * copies its address, so a result can be shared or cited.
     */
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
            host.append(' ', link);
        });
    }

    // ==========================================================================
    // Mobile Menu Toggle
    // ==========================================================================

    /**
     * Toolbar buttons.
     * - Contents: on phones and small tablets the book sidebar is a drawer; on wider screens
     *   the button folds the sidebar away so the text column can widen.
     * - Theme: light / dark. Follows the system until the reader chooses; the choice is saved.
     * - On this page: folds the right-hand pane away.
     * Choices are saved in localStorage and applied before first paint (see template.html).
     */
    const DRAWER_QUERY = window.matchMedia('(max-width: 900px)');

    function saveSetting(key, value) {
        try {
            if (value === null) localStorage.removeItem(key);
            else localStorage.setItem(key, value);
        } catch (e) { /* private mode: the setting lasts for this page only */ }
    }

    function setButtonLabel(button, label) {
        button.setAttribute('aria-label', label);
        button.dataset.tooltip = label;
    }

    function setupLayoutControls() {
        const root = document.documentElement;
        const sidebar = document.getElementById('quarto-sidebar');
        const sidebarButton = document.querySelector('.sidebar-toggle');
        const tocButton = document.querySelector('.toc-toggle');
        const themeButton = document.querySelector('.theme-toggle');

        // --- Book contents: drawer (narrow) or collapsible pane (wide) ---
        if (sidebar && sidebarButton) {
            const overlay = document.createElement('div');
            overlay.className = 'sidebar-overlay';
            document.body.appendChild(overlay);

            const setDrawer = open => {
                sidebar.classList.toggle('show', open);
                overlay.classList.toggle('show', open);
                document.body.classList.toggle('drawer-open', open);
                sidebarButton.setAttribute('aria-expanded', String(open));
                setButtonLabel(sidebarButton, open ? 'Close book contents' : 'Open book contents');
                if (open) {
                    const current = sidebar.querySelector('.nav-section-item.active a') || sidebar.querySelector('a');
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
                if (DRAWER_QUERY.matches) setDrawer(false);
                else {
                    setDrawer(false);
                    setCollapsed(root.dataset.sidebar === 'collapsed');
                }
            };

            sidebarButton.addEventListener('click', () => {
                if (DRAWER_QUERY.matches) setDrawer(!sidebar.classList.contains('show'));
                else setCollapsed(root.dataset.sidebar !== 'collapsed');
            });
            overlay.addEventListener('click', () => setDrawer(false));
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

        // --- On this page ---
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

        // --- Theme ---
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
                // Back to "follow the system" when the choice matches the system anyway
                saveSetting('book-theme', next === (systemDark.matches ? 'dark' : 'light') ? null : next);
                applyTheme(next);
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
    // Search Implementation
    // ==========================================================================

    let searchIndex = null;

    /**
     * Load search index
     */
    async function loadSearchIndex() {
        if (searchIndex) return true;
        
        try {
            const response = await fetchData('search.json');
            if (response.ok) {
                searchIndex = await response.json();
                console.log(`Loaded search index: ${searchIndex.length} entries`);
                return true;
            }
        } catch (error) {
            console.warn('Could not load search index:', error);
        }
        return false;
    }

    function escapeHtml(text) {
        return String(text).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    /** Split text into [{math: bool, text}] at \\( ... \\) and \\[ ... \\] delimiters. */
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

    /** Escape text and wrap query words in <mark>, outside formulas (MathJax typesets those). */
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

    /** A slice of `text` around `index` that never cuts through a formula. */
    function snippetAround(text, index, before = 50, after = 110) {
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

    /**
     * Search pages and results (theorems, definitions, ...). Every word of the query must
     * appear; matches in titles rank above matches in text, and results above pages.
     */
    function search(query) {
        if (!searchIndex || !query) return [];
        const words = query.toLowerCase().split(/\s+/).filter(Boolean);
        const results = [];

        for (const entry of searchIndex) {
            const title = (entry.title || '').toLowerCase();
            const content = (entry.content || '').toLowerCase();
            if (!words.every(w => title.includes(w) || content.includes(w))) continue;

            let score = 0;
            for (const w of words) {
                if (title.includes(w)) score += 10;
                else score += 1;
            }
            if (title.includes(query.toLowerCase())) score += 15;
            if (entry.kind === 'result') score += 2;

            // Snippet around the first word found in the text
            const hit = words.map(w => content.indexOf(w)).filter(i => i >= 0).sort((a, b) => a - b)[0];
            const snippet = snippetAround(entry.content || '', hit === undefined ? 0 : hit, hit === undefined ? 0 : 50);
            results.push({ ...entry, snippet, score });
        }
        return results.sort((a, b) => b.score - a.score).slice(0, 12);
    }

    function setupSearch() {
        const searchInput = document.getElementById('search-input');
        if (!searchInput) return;

        const resultsContainer = document.createElement('div');
        resultsContainer.className = 'search-results';
        resultsContainer.id = 'search-results';
        resultsContainer.setAttribute('role', 'listbox');
        searchInput.parentElement.appendChild(resultsContainer);
        searchInput.setAttribute('aria-controls', 'search-results');

        let debounceTimer;
        let activeIndex = -1;

        const items = () => [...resultsContainer.querySelectorAll('.search-result-item')];
        const close = () => {
            resultsContainer.classList.remove('active');
            activeIndex = -1;
        };
        const setActive = index => {
            const list = items();
            if (!list.length) return;
            activeIndex = (index + list.length) % list.length;
            list.forEach((item, i) => item.classList.toggle('selected', i === activeIndex));
            list[activeIndex].scrollIntoView({ block: 'nearest' });
        };

        searchInput.addEventListener('focus', () => {
            loadSearchIndex();
            if (resultsContainer.childElementCount && searchInput.value.trim().length >= 2) {
                resultsContainer.classList.add('active');
            }
        });

        // "/" focuses search (unless the reader is typing somewhere else)
        document.addEventListener('keydown', event => {
            if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return;
            const target = event.target;
            if (target.closest('input, textarea, select, [contenteditable="true"]')) return;
            event.preventDefault();
            const sidebar = document.getElementById('quarto-sidebar');
            if (DRAWER_QUERY.matches && !sidebar?.classList.contains('show')) {
                document.querySelector('.sidebar-toggle')?.click();
            } else if (!DRAWER_QUERY.matches && document.documentElement.dataset.sidebar === 'collapsed') {
                document.querySelector('.sidebar-toggle')?.click();
            }
            searchInput.focus();
        });

        searchInput.addEventListener('keydown', event => {
            if (event.key === 'ArrowDown') { event.preventDefault(); setActive(activeIndex + 1); }
            else if (event.key === 'ArrowUp') { event.preventDefault(); setActive(activeIndex - 1); }
            else if (event.key === 'Enter') {
                const list = items();
                const chosen = list[activeIndex >= 0 ? activeIndex : 0];
                if (chosen) { event.preventDefault(); chosen.click(); }
            } else if (event.key === 'Escape') {
                if (resultsContainer.classList.contains('active')) {
                    event.stopPropagation();
                    close();
                } else {
                    searchInput.blur();
                }
            }
        });

        searchInput.addEventListener('input', event => {
            const query = event.target.value.trim();
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(async () => {
                if (query.length < 2) {
                    close();
                    return;
                }
                await loadSearchIndex();
                const words = query.split(/\s+/).filter(Boolean);
                const results = search(query);
                activeIndex = -1;

                if (results.length) {
                    resultsContainer.innerHTML = results.map(result => `
                        <a class="search-result-item" role="option" href="${escapeHtml(getBasePath() + result.url)}">
                            <span class="search-result-title">${highlight(result.title, words)}</span>
                            ${result.kind === 'result' ? `<span class="search-result-page">${escapeHtml(result.page)}</span>` : ''}
                            <span class="search-result-preview">${highlight(result.snippet, words)}</span>
                        </a>
                    `).join('');
                } else {
                    resultsContainer.innerHTML = `<div class="search-no-results">No results for “${escapeHtml(query)}”</div>`;
                }
                resultsContainer.classList.add('active');
                if (results.length && /\\\(|\\\[/.test(resultsContainer.textContent)) {
                    ensureMathJax().then(mj => {
                        if (!mj) return;
                        mj.typesetClear?.([resultsContainer]);
                        mj.typesetPromise([resultsContainer]).catch(() => {});
                    });
                }
            }, 150);
        });

        document.addEventListener('click', event => {
            if (!searchInput.contains(event.target) && !resultsContainer.contains(event.target)) close();
        });
    }

    // ==========================================================================
    // Initialization
    // ==========================================================================

    async function init() {
        console.log('Initializing book navigation...');

        // Toolbar first, so its buttons work while the navigation data loads
        setupLayoutControls();

        // The build renders the sidebar into the page, so there is normally nothing to fetch
        // and nothing to rebuild: just wire it up. The fetch remains for any page built
        // without it, so the sidebar still works rather than staying a single Preface link.
        if (!hydrateSidebarNav() && await loadNavigation()) {
            buildSidebarNav();
            updateSidebarHeader();
        }

        // Arrow-key paging
        setupArrowKeys();

        // Reading / Exercises tabs (before the table of contents, which reflects them)
        setupSectionTabs();

        // Build table of contents
        buildTableOfContents();
        if (selectSectionTab) {
            selectSectionTab(document.querySelector('.section-tab[aria-selected="true"]')?.dataset.tab || 'reading');
        }

        setupWideInlineMath();
        setupMathCopy();

        // Fold solutions (and let readers fold proofs), before anchors are resolved
        setupFolding();
        setupResultsFilters();

        // Link anchors on headings and theorems; highlight the linked element
        setupAnchorLinks();
        markTargetFromHash();
        window.addEventListener('hashchange', markTargetFromHash);

        // Attach tooltips
        attachTooltips();

        // Setup smooth scrolling
        setupSmoothScrolling();


        // Setup search
        setupSearch();

        console.log('Book navigation initialized');
    }

    // Run when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
