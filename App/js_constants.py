"""
js_constants.py

Semua JavaScript selector string untuk Shadow DOM automation
di business.gemini.google

Update: path diperbaiki untuk Chrome 145+ (main > ucs-chat-landing)
Masing-masing JS mencoba beberapa path (new -> old) sebagai fallback.
"""

# ================================================================
# Helper: resolve shadow chain, return null jika salah satu miss
# ================================================================
_JS_SHADOW_RESOLVE = """
function _sr(el, sel) {
    try { return el.shadowRoot ? el.shadowRoot.querySelector(sel) : null; }
    catch(e) { return null; }
}
"""

# Prefix standar semua query: ucs-standalone-app shadowRoot
_JS_APP_ROOT = "document.querySelector('body > ucs-standalone-app')"

# ================================================================
# Step 16 - Dismiss popup 'I'll do this later'
# ================================================================
_JS_DISMISS_POPUP = """
(function() {
    var app = document.querySelector("body > ucs-standalone-app");
    if (!app || !app.shadowRoot) return null;
    var dialog = app.shadowRoot.querySelector("ucs-welcome-dialog");
    if (!dialog || !dialog.shadowRoot) return null;
    // Try multiple button selectors
    var selectors = [
        "div > md-dialog > div:nth-child(3) > md-text-button",
        "md-dialog md-text-button",
        "md-text-button"
    ];
    for (var i = 0; i < selectors.length; i++) {
        var btn = dialog.shadowRoot.querySelector(selectors[i]);
        if (btn) {
            var touch = btn.shadowRoot ? btn.shadowRoot.querySelector("#button > span.touch") : null;
            return touch || btn;
        }
    }
    return null;
})();
"""

# ================================================================
# Step 17 - Click tools button
# Tries: new path (main > ucs-chat-landing) -> old path (div > ucs-chat-landing)
# ================================================================
_JS_CLICK_TOOLS = """
(function() {
    var app = document.querySelector("body > ucs-standalone-app");
    if (!app || !app.shadowRoot) return null;
    var appRoot = app.shadowRoot;

    // Candidate paths to ucs-chat-landing
    var landingSelectors = [
        "div > div.ucs-standalone-outer-row-container > div > main > ucs-chat-landing",
        "div > div.ucs-standalone-outer-row-container > div > ucs-chat-landing",
        "main > ucs-chat-landing",
        "ucs-chat-landing"
    ];

    for (var li = 0; li < landingSelectors.length; li++) {
        var landing = appRoot.querySelector(landingSelectors[li]);
        if (!landing || !landing.shadowRoot) continue;

        // Candidate paths to ucs-search-bar
        var searchBarSelectors = [
            "div > div > div > div.fixed-content > ucs-search-bar",
            "div > div > div > ucs-search-bar",
            "ucs-search-bar"
        ];

        for (var si = 0; si < searchBarSelectors.length; si++) {
            var searchBar = landing.shadowRoot.querySelector(searchBarSelectors[si]);
            if (!searchBar || !searchBar.shadowRoot) continue;

            // Candidate paths to tool-selector-menu-anchor
            var anchorSelectors = [
                "#tool-selector-menu-anchor",
                "div > form > div > div.actions-buttons > div.tools-button-container > md-icon-button",
                "[id='tool-selector-menu-anchor']"
            ];

            for (var ai = 0; ai < anchorSelectors.length; ai++) {
                var anchor = searchBar.shadowRoot.querySelector(anchorSelectors[ai]);
                if (!anchor) continue;
                // Return inner touch span, or anchor itself
                var touch = anchor.shadowRoot ? anchor.shadowRoot.querySelector("#button > span.touch") : null;
                return touch || anchor;
            }
        }
    }
    return null;
})();
"""

# ================================================================
# Step 18 - Click 'Create videos with Veo'
# ================================================================
_JS_CLICK_VEO = """
(function() {
    var app = document.querySelector("body > ucs-standalone-app");
    if (!app || !app.shadowRoot) return null;
    var appRoot = app.shadowRoot;

    var landingSelectors = [
        "div > div.ucs-standalone-outer-row-container > div > main > ucs-chat-landing",
        "div > div.ucs-standalone-outer-row-container > div > ucs-chat-landing",
        "main > ucs-chat-landing",
        "ucs-chat-landing"
    ];

    for (var li = 0; li < landingSelectors.length; li++) {
        var landing = appRoot.querySelector(landingSelectors[li]);
        if (!landing || !landing.shadowRoot) continue;

        var searchBarSelectors = [
            "div > div > div > div.fixed-content > ucs-search-bar",
            "div > div > div > ucs-search-bar",
            "ucs-search-bar"
        ];

        for (var si = 0; si < searchBarSelectors.length; si++) {
            var searchBar = landing.shadowRoot.querySelector(searchBarSelectors[si]);
            if (!searchBar || !searchBar.shadowRoot) continue;
            var sbRoot = searchBar.shadowRoot;

            // Try specific Veo menu item selectors
            var veoSelectors = [
                "div > form > div > div.actions-buttons.omnibar.multiline-input-actions-buttons > div.tools-button-container > md-menu > div:nth-child(7) > md-menu-item > div",
                "md-menu md-menu-item > div",
                "md-menu-item > div",
                "md-menu-item"
            ];

            for (var vi = 0; vi < veoSelectors.length; vi++) {
                var items = sbRoot.querySelectorAll(veoSelectors[vi]);
                for (var ii = 0; ii < items.length; ii++) {
                    var txt = (items[ii].textContent || items[ii].innerText || "").toLowerCase();
                    if (txt.includes("veo") || txt.includes("video")) {
                        return items[ii];
                    }
                }
                // If no text match, try last nth-child fallback
                if (vi === 0) {
                    var direct = sbRoot.querySelector(veoSelectors[0]);
                    if (direct) return direct;
                }
            }
        }
    }
    return null;
})();
"""

# ================================================================
# Step 19 - Get prompt input element
# ================================================================
_JS_GET_PROMPT_INPUT = """
(function() {
    var app = document.querySelector("body > ucs-standalone-app");
    if (!app || !app.shadowRoot) return null;
    var appRoot = app.shadowRoot;

    // After Veo selected, page may be on chat or landing
    var containerSelectors = [
        "div > div.ucs-standalone-outer-row-container > div > main > ucs-chat-landing",
        "div > div.ucs-standalone-outer-row-container > div > ucs-chat-landing",
        "main > ucs-chat-landing",
        "ucs-chat-landing"
    ];

    for (var li = 0; li < containerSelectors.length; li++) {
        var landing = appRoot.querySelector(containerSelectors[li]);
        if (!landing || !landing.shadowRoot) continue;

        var searchBarSelectors = [
            "div > div > div > div.fixed-content > ucs-search-bar",
            "div > div > div > ucs-search-bar",
            "ucs-search-bar"
        ];

        for (var si = 0; si < searchBarSelectors.length; si++) {
            var searchBar = landing.shadowRoot.querySelector(searchBarSelectors[si]);
            if (!searchBar || !searchBar.shadowRoot) continue;

            var editorSelectors = [
                "#agent-search-prosemirror-editor",
                "div[id='agent-search-prosemirror-editor']",
                "ucs-prosemirror-editor",
            ];

            for (var ei = 0; ei < editorSelectors.length; ei++) {
                var editor = searchBar.shadowRoot.querySelector(editorSelectors[ei]);
                if (!editor) continue;
                if (editor.shadowRoot) {
                    var p = editor.shadowRoot.querySelector("div > div > div > p") ||
                            editor.shadowRoot.querySelector(".ProseMirror p") ||
                            editor.shadowRoot.querySelector("[contenteditable='true']");
                    if (p) return p;
                }
                return editor;
            }
        }
    }
    return null;
})();
"""

# ================================================================
# Step 20 - Get thinking message element
# ================================================================
_JS_GET_THINKING = """
(function() {
    var app = document.querySelector("body > ucs-standalone-app");
    if (!app || !app.shadowRoot) return null;
    var appRoot = app.shadowRoot;

    var resultsSelectors = [
        "div > div.ucs-standalone-outer-row-container > div > div.search-bar-and-results-container > div > ucs-results",
        "div > div.ucs-standalone-outer-row-container > div > ucs-results",
        "ucs-results"
    ];

    for (var ri = 0; ri < resultsSelectors.length; ri++) {
        var results = appRoot.querySelector(resultsSelectors[ri]);
        if (!results || !results.shadowRoot) continue;

        var convSelectors = [
            "div > div > div.tile.chat-mode-conversation.chat-mode-conversation > div.chat-mode-scroller.tile-content > ucs-conversation",
            "ucs-conversation"
        ];

        for (var ci = 0; ci < convSelectors.length; ci++) {
            var conv = results.shadowRoot.querySelector(convSelectors[ci]);
            if (!conv || !conv.shadowRoot) continue;

            var summarySelectors = [
                "div > div.turn.last > ucs-summary",
                "div > div > ucs-summary",
                "ucs-summary"
            ];

            for (var ssi = 0; ssi < summarySelectors.length; ssi++) {
                var summary = conv.shadowRoot.querySelector(summarySelectors[ssi]);
                if (!summary || !summary.shadowRoot) continue;

                var thinkingSelectors = [
                    "div > div > div.summary-contents > div.header.agent-thoughts-header > ucs-agent-thoughts",
                    "ucs-agent-thoughts"
                ];

                for (var ti = 0; ti < thinkingSelectors.length; ti++) {
                    var thoughts = summary.shadowRoot.querySelector(thinkingSelectors[ti]);
                    if (!thoughts || !thoughts.shadowRoot) continue;
                    var msg = thoughts.shadowRoot.querySelector("div.header > div.thinking-message") ||
                              thoughts.shadowRoot.querySelector(".thinking-message");
                    if (msg) return msg;
                }
            }
        }
    }
    return null;
})();
"""

# ================================================================
# Step 21a - Click download button
# ================================================================
_JS_CLICK_DOWNLOAD = """
(function() {
    var app = document.querySelector("body > ucs-standalone-app");
    if (!app || !app.shadowRoot) return null;
    var appRoot = app.shadowRoot;

    var resultsSelectors = [
        "div > div.ucs-standalone-outer-row-container > div > div.search-bar-and-results-container > div > ucs-results",
        "ucs-results"
    ];

    for (var ri = 0; ri < resultsSelectors.length; ri++) {
        var results = appRoot.querySelector(resultsSelectors[ri]);
        if (!results || !results.shadowRoot) continue;

        var convSelectors = [
            "div > div > div.tile.chat-mode-conversation.chat-mode-conversation > div.chat-mode-scroller.tile-content > ucs-conversation",
            "ucs-conversation"
        ];

        for (var ci = 0; ci < convSelectors.length; ci++) {
            var conv = results.shadowRoot.querySelector(convSelectors[ci]);
            if (!conv || !conv.shadowRoot) continue;

            var summarySelectors = [
                "div > div > ucs-summary",
                "div > div.turn.last > ucs-summary",
                "ucs-summary"
            ];

            for (var ssi = 0; ssi < summarySelectors.length; ssi++) {
                var summary = conv.shadowRoot.querySelector(summarySelectors[ssi]);
                if (!summary || !summary.shadowRoot) continue;

                var attach = summary.shadowRoot.querySelector("div > div > div.summary-contents > ucs-summary-attachments") ||
                             summary.shadowRoot.querySelector("ucs-summary-attachments");
                if (!attach || !attach.shadowRoot) continue;

                var vid = attach.shadowRoot.querySelector("div > ucs-markdown-video") ||
                          attach.shadowRoot.querySelector("ucs-markdown-video");
                if (!vid || !vid.shadowRoot) continue;

                var dlBtn = vid.shadowRoot.querySelector("div > div.video-actions > md-filled-icon-button") ||
                            vid.shadowRoot.querySelector("md-filled-icon-button");
                if (!dlBtn) continue;

                var touch = dlBtn.shadowRoot ? dlBtn.shadowRoot.querySelector("#button > span.touch") : null;
                return touch || dlBtn;
            }
        }
    }
    return null;
})();
"""

# ================================================================
# Step 21b - Click download confirmation
# ================================================================
_JS_CLICK_CONFIRM = """
(function() {
    var app = document.querySelector("body > ucs-standalone-app");
    if (!app || !app.shadowRoot) return null;
    var appRoot = app.shadowRoot;

    var results = appRoot.querySelector("ucs-results");
    if (!results || !results.shadowRoot) return null;
    var conv = results.shadowRoot.querySelector("ucs-conversation");
    if (!conv || !conv.shadowRoot) return null;
    var summary = conv.shadowRoot.querySelector("ucs-summary");
    if (!summary || !summary.shadowRoot) return null;
    var attach = summary.shadowRoot.querySelector("ucs-summary-attachments");
    if (!attach || !attach.shadowRoot) return null;
    var vid = attach.shadowRoot.querySelector("ucs-markdown-video");
    if (!vid || !vid.shadowRoot) return null;
    var dlWarn = vid.shadowRoot.querySelector("ucs-download-warning-dialog");
    if (!dlWarn || !dlWarn.shadowRoot) return null;
    var confirmBtn = dlWarn.shadowRoot.querySelector("md-dialog > div:nth-child(3) > md-text-button.action-button") ||
                     dlWarn.shadowRoot.querySelector("md-text-button.action-button") ||
                     dlWarn.shadowRoot.querySelector("md-text-button");
    if (!confirmBtn) return null;
    var touch = confirmBtn.shadowRoot ? confirmBtn.shadowRoot.querySelector("#button > span.touch") : null;
    return touch || confirmBtn;
})();
"""

# ================================================================
# Get attachment status/error text inside shadow DOM
# ================================================================
_JS_GET_ATTACHMENT_STATUS = """
try {
    var app = document.querySelector("body > ucs-standalone-app");
    if (!app || !app.shadowRoot) return null;
    var results = app.shadowRoot.querySelector("ucs-results");
    if (!results || !results.shadowRoot) return null;
    var conv = results.shadowRoot.querySelector("ucs-conversation");
    if (!conv || !conv.shadowRoot) return null;
    var summary = conv.shadowRoot.querySelector("ucs-summary");
    if (!summary || !summary.shadowRoot) return null;
    var attach = summary.shadowRoot.querySelector("ucs-summary-attachments");
    if (!attach || !attach.shadowRoot) return null;
    var span = attach.shadowRoot.querySelector("div > div > span");
    return span ? span.textContent : null;
} catch(e) {
    return null;
}
"""

# ================================================================
# List all buttons in shadow DOM (for debug)
# ================================================================
_JS_LIST_BUTTONS = """
(function() {
    var result = [];
    function scan(root, depth) {
        if (depth > 10) return;
        var btns = root.querySelectorAll('button, gds-button, gmp-button, md-icon-button, md-filled-icon-button');
        btns.forEach(function(b) {
            result.push({
                tag: b.tagName,
                id: b.id || '',
                cls: b.getAttribute('class') || '',
                aria: b.getAttribute('aria-label') || '',
                text: (b.innerText || b.textContent || '').trim().substring(0, 80),
                visible: b.offsetParent !== null
            });
        });
        var all = root.querySelectorAll('*');
        all.forEach(function(el) {
            if (el.shadowRoot) scan(el.shadowRoot, depth + 1);
        });
    }
    scan(document, 0);
    return JSON.stringify(result);
})();
"""

# ================================================================
# Extract all text across shadow DOMs
# ================================================================
_JS_GET_ALL_TEXT_DEEP = """
(function() {
    let result = "";
    function traverse(node) {
        if (!node) return;
        if (node.nodeType === Node.TEXT_NODE) {
            let text = node.textContent.trim();
            if (text) result += " " + text;
        } else if (node.nodeType === Node.ELEMENT_NODE || node.nodeType === Node.DOCUMENT_FRAGMENT_NODE) {
            if (node.shadowRoot) traverse(node.shadowRoot);
            if (node.tagName !== 'SCRIPT' && node.tagName !== 'STYLE') {
                for (let child of node.childNodes) traverse(child);
            }
        }
    }
    traverse(document.body);
    return result;
})();
"""

# ================================================================
# Find and click "Regenerate" button inside shadow roots
# ================================================================
_JS_CLICK_REGENERATE = """
(function() {
    let clicked = false;
    function scanAndClick(root) {
        if (clicked) return false;
        let btns = root.querySelectorAll('button, gds-button, md-text-button, gmp-button, span');
        for (let i = 0; i < btns.length; i++) {
            let b = btns[i];
            let text = (b.innerText || b.textContent || '').trim().toLowerCase();
            if (text.includes('regenerate')) {
                let target = (b.tagName === 'SPAN' && b.parentElement) ? b.parentElement : b;
                target.click();
                if (target.shadowRoot) {
                    let internalTarget = target.shadowRoot.querySelector('#button > span.touch') || target.shadowRoot.querySelector('button');
                    if (internalTarget) internalTarget.click();
                }
                clicked = true;
                return true;
            }
        }
        let all = root.querySelectorAll('*');
        for (let i = 0; i < all.length; i++) {
            if (all[i].shadowRoot && scanAndClick(all[i].shadowRoot)) return true;
        }
        return false;
    }
    return scanAndClick(document);
})();
"""

# ================================================================
# Find <video> or <source> tags deep inside Shadow DOMs with blob: src
# ================================================================
_JS_GET_VIDEO_SRC = """
(function() {
    let result = null;
    function scanForVideo(root) {
        if (result) return true;
        let videos = root.querySelectorAll('video, source');
        for (let i = 0; i < videos.length; i++) {
            let src = (videos[i].getAttribute('src') || '').trim();
            if (src.startsWith('blob:')) { result = src; return true; }
        }
        let all = root.querySelectorAll('*');
        for (let i = 0; i < all.length; i++) {
            if (all[i].shadowRoot && scanForVideo(all[i].shadowRoot)) return true;
        }
        return false;
    }
    scanForVideo(document);
    return result;
})();
"""

# ================================================================
# Fetch a blob URL, read as ArrayBuffer, convert to Base64
# ================================================================
_JS_FETCH_BLOB_BASE64 = """
var blobUrl = arguments[0];
var callback = arguments[1];
fetch(blobUrl)
    .then(response => response.blob())
    .then(blob => {
        var reader = new FileReader();
        reader.onloadend = function() {
            var b64 = reader.result.split(',')[1];
            callback(b64);
        };
        reader.readAsDataURL(blob);
    })
    .catch(error => { callback("ERROR: " + error.toString()); });
"""
