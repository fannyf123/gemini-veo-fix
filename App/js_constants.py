"""
js_constants.py

Semua JavaScript selector string untuk Shadow DOM automation
di business.gemini.google

Selector utama berdasarkan outerHTML yang dikonfirmasi langsung dari DevTools:
- Step 16: jslog=283097 (md-text-button "I'll do this later")
- Step 17: jslog=283108, id=tool-selector-menu-anchor (md-text-button tools)
- Step 18: jslog=283118 (md-menu-item Veo)
- Step 19: id=agent-search-prosemirror-editor (ucs-prosemirror-editor)
- Step 20: tag=ucs-agent-thoughts, class=show-summary-text
- Step 21a: class=download-button, data-aria-label=Download video file (md-filled-icon-button)
"""

# ================================================================
# Step 16 - Dismiss popup 'I'll do this later'
# Confirmed outerHTML: <md-text-button jslog="283097;track:impression,click" value="">
# ================================================================
_JS_DISMISS_POPUP = """
(function() {
    function clickBtn(btn) {
        if (!btn) return false;
        if (btn.shadowRoot) {
            var touch = btn.shadowRoot.querySelector('#button > span.touch') ||
                        btn.shadowRoot.querySelector('span.touch') ||
                        btn.shadowRoot.querySelector('#button');
            if (touch) { touch.click(); return true; }
        }
        btn.click();
        return true;
    }
    function deepScan(root, depth) {
        if (depth > 8) return false;
        var btn = root.querySelector ? root.querySelector("[jslog*='283097']") : null;
        if (btn) return clickBtn(btn);
        var btns = root.querySelectorAll ? root.querySelectorAll('md-text-button') : [];
        for (var i = 0; i < btns.length; i++) {
            var txt = (btns[i].textContent || '').toLowerCase();
            if (txt.includes('do this later') || txt.includes("i'll do")) return clickBtn(btns[i]);
        }
        var all = root.querySelectorAll ? root.querySelectorAll('*') : [];
        for (var i = 0; i < all.length; i++) {
            if (all[i].shadowRoot && deepScan(all[i].shadowRoot, depth + 1)) return true;
        }
        return false;
    }
    return deepScan(document, 0);
})();
"""

# ================================================================
# Step 17 - Click tools button
# Confirmed outerHTML:
#   <md-text-button id="tool-selector-menu-anchor"
#     jslog="283108;track:click"
#     data-aria-label="Select tools"
#     class="omnibox-tools-selector selector-button">
# ================================================================
_JS_CLICK_TOOLS = """
(function() {
    function clickBtn(btn) {
        if (!btn) return false;
        if (btn.shadowRoot) {
            var touch = btn.shadowRoot.querySelector('#button > span.touch') ||
                        btn.shadowRoot.querySelector('span.touch') ||
                        btn.shadowRoot.querySelector('#button');
            if (touch) { touch.click(); return true; }
        }
        btn.click();
        return true;
    }
    function deepScan(root, depth) {
        if (depth > 8) return false;
        var btn = root.querySelector ? root.querySelector("[jslog*='283108']") : null;
        if (btn) return clickBtn(btn);
        btn = root.querySelector ? root.querySelector("#tool-selector-menu-anchor") : null;
        if (btn) return clickBtn(btn);
        btn = root.querySelector ? root.querySelector(".omnibox-tools-selector") : null;
        if (btn) return clickBtn(btn);
        btn = root.querySelector ? root.querySelector("[data-aria-label='Select tools']") : null;
        if (btn) return clickBtn(btn);
        var all = root.querySelectorAll ? root.querySelectorAll('*') : [];
        for (var i = 0; i < all.length; i++) {
            if (all[i].shadowRoot && deepScan(all[i].shadowRoot, depth + 1)) return true;
        }
        return false;
    }
    return deepScan(document, 0);
})();
"""

# ================================================================
# Step 18 - Click 'Create videos with Veo'
# Confirmed outerHTML:
#   <md-menu-item jslog="283118;track:click" md-menu-item="">
#     <div slot="headline">Create videos with Veo</div>
# ================================================================
_JS_CLICK_VEO = """
(function() {
    function clickBtn(btn) {
        if (!btn) return false;
        if (btn.shadowRoot) {
            var touch = btn.shadowRoot.querySelector('#item > span.touch') ||
                        btn.shadowRoot.querySelector('span.touch') ||
                        btn.shadowRoot.querySelector('#item');
            if (touch) { touch.click(); return true; }
        }
        var headline = btn.querySelector("[slot='headline']") || btn.querySelector('div');
        if (headline) { headline.click(); return true; }
        btn.click();
        return true;
    }
    function deepScan(root, depth) {
        if (depth > 8) return false;
        var item = root.querySelector ? root.querySelector("[jslog*='283118']") : null;
        if (item) return clickBtn(item);
        var items = root.querySelectorAll ? root.querySelectorAll('md-menu-item') : [];
        for (var i = 0; i < items.length; i++) {
            var txt = (items[i].textContent || '').toLowerCase();
            if (txt.includes('veo') || txt.includes('create video')) return clickBtn(items[i]);
        }
        var all = root.querySelectorAll ? root.querySelectorAll('*') : [];
        for (var i = 0; i < all.length; i++) {
            if (all[i].shadowRoot && deepScan(all[i].shadowRoot, depth + 1)) return true;
        }
        return false;
    }
    return deepScan(document, 0);
})();
"""

# ================================================================
# Step 19 - Get prompt input element
# Confirmed outerHTML:
#   <ucs-prosemirror-editor id="agent-search-prosemirror-editor"
#     aria-label="Search" class="prosemirror-editor">
# ================================================================
_JS_GET_PROMPT_INPUT = """
(function() {
    function findEditor(root, depth) {
        if (depth > 8) return null;
        var editor = root.querySelector ? root.querySelector('#agent-search-prosemirror-editor') : null;
        if (editor) {
            if (editor.shadowRoot) {
                var p = editor.shadowRoot.querySelector('div > div > div > p') ||
                        editor.shadowRoot.querySelector('.ProseMirror') ||
                        editor.shadowRoot.querySelector("[contenteditable='true']");
                if (p) return p;
            }
            return editor;
        }
        editor = root.querySelector ? root.querySelector('ucs-prosemirror-editor') : null;
        if (editor) {
            if (editor.shadowRoot) {
                var p = editor.shadowRoot.querySelector('.ProseMirror') ||
                        editor.shadowRoot.querySelector("[contenteditable='true']");
                if (p) return p;
            }
            return editor;
        }
        var all = root.querySelectorAll ? root.querySelectorAll('*') : [];
        for (var i = 0; i < all.length; i++) {
            if (all[i].shadowRoot) {
                var found = findEditor(all[i].shadowRoot, depth + 1);
                if (found) return found;
            }
        }
        return null;
    }
    return findEditor(document, 0);
})();
"""

# ================================================================
# Step 20 - Get thinking/loading indicator element
# Confirmed outerHTML:
#   <ucs-agent-thoughts class="show-summary-text animate-header"
#     spk2="" dark-theme="" next-gen="" next-gen-batch-2="">
# Deteksi: elemen ada = masih loading/thinking
# ================================================================
_JS_GET_THINKING = """
(function() {
    function findThoughts(root, depth) {
        if (depth > 8) return null;
        // Primary: tag ucs-agent-thoughts dengan class show-summary-text
        var el = root.querySelector ? root.querySelector('ucs-agent-thoughts.show-summary-text') : null;
        if (el) return el;
        // Secondary: tag ucs-agent-thoughts saja
        el = root.querySelector ? root.querySelector('ucs-agent-thoughts') : null;
        if (el) return el;
        // Fallback: cari .thinking-message di dalam shadow root
        var all = root.querySelectorAll ? root.querySelectorAll('*') : [];
        for (var i = 0; i < all.length; i++) {
            if (all[i].shadowRoot) {
                var found = findThoughts(all[i].shadowRoot, depth + 1);
                if (found) return found;
            }
        }
        return null;
    }
    var el = findThoughts(document, 0);
    if (!el) return null;
    // Coba ambil teks thinking dari shadowRoot
    if (el.shadowRoot) {
        var msg = el.shadowRoot.querySelector('div.header > div.thinking-message') ||
                  el.shadowRoot.querySelector('.thinking-message') ||
                  el.shadowRoot.querySelector('.header');
        if (msg) return msg;
    }
    return el;
})();
"""

# ================================================================
# Step 21a - Click download button
# Confirmed outerHTML:
#   <md-filled-icon-button class="download-button"
#     data-aria-label="Download video file"
#     aria-describedby="ucs-tooltip-40">
#     <md-icon aria-hidden="true">download</md-icon>
# ================================================================
_JS_CLICK_DOWNLOAD = """
(function() {
    function clickBtn(btn) {
        if (!btn) return false;
        if (btn.shadowRoot) {
            var touch = btn.shadowRoot.querySelector('#button > span.touch') ||
                        btn.shadowRoot.querySelector('span.touch') ||
                        btn.shadowRoot.querySelector('#button');
            if (touch) { touch.click(); return true; }
        }
        btn.click();
        return true;
    }
    function findDownload(root, depth) {
        if (depth > 8) return false;
        // Primary: class=download-button
        var btn = root.querySelector ? root.querySelector('.download-button') : null;
        if (btn) return clickBtn(btn);
        // Secondary: data-aria-label="Download video file"
        btn = root.querySelector ? root.querySelector("[data-aria-label='Download video file']") : null;
        if (btn) return clickBtn(btn);
        // Tertiary: md-filled-icon-button yang mengandung md-icon download
        var btns = root.querySelectorAll ? root.querySelectorAll('md-filled-icon-button') : [];
        for (var i = 0; i < btns.length; i++) {
            var icon = btns[i].querySelector('md-icon');
            if (icon && (icon.textContent || '').trim() === 'download') return clickBtn(btns[i]);
        }
        var all = root.querySelectorAll ? root.querySelectorAll('*') : [];
        for (var i = 0; i < all.length; i++) {
            if (all[i].shadowRoot && findDownload(all[i].shadowRoot, depth + 1)) return true;
        }
        return false;
    }
    return findDownload(document, 0);
})();
"""

# ================================================================
# Step 21b - Click download confirmation
# outerHTML 21b yang dikopi adalah md-ripple (bagian dalam shadow root)
# Tetap pakai selector stabil: md-text-button di dalam ucs-download-warning-dialog
# ================================================================
_JS_CLICK_CONFIRM = """
(function() {
    function clickBtn(btn) {
        if (!btn) return false;
        if (btn.shadowRoot) {
            var touch = btn.shadowRoot.querySelector('#button > span.touch') ||
                        btn.shadowRoot.querySelector('span.touch') ||
                        btn.shadowRoot.querySelector('#button');
            if (touch) { touch.click(); return true; }
        }
        btn.click();
        return true;
    }
    function findConfirm(root, depth) {
        if (depth > 8) return false;
        // Cari dialog konfirmasi download
        var dlWarn = root.querySelector ? root.querySelector('ucs-download-warning-dialog') : null;
        if (dlWarn && dlWarn.shadowRoot) {
            var confirmBtn = dlWarn.shadowRoot.querySelector('md-text-button.action-button') ||
                             dlWarn.shadowRoot.querySelector('md-text-button');
            if (confirmBtn) return clickBtn(confirmBtn);
        }
        var all = root.querySelectorAll ? root.querySelectorAll('*') : [];
        for (var i = 0; i < all.length; i++) {
            if (all[i].shadowRoot && findConfirm(all[i].shadowRoot, depth + 1)) return true;
        }
        return false;
    }
    return findConfirm(document, 0);
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
        var btns = root.querySelectorAll('button, gds-button, gmp-button, md-icon-button, md-filled-icon-button, md-text-button');
        btns.forEach(function(b) {
            result.push({
                tag: b.tagName,
                id: b.id || '',
                cls: b.getAttribute('class') || '',
                aria: b.getAttribute('aria-label') || b.getAttribute('data-aria-label') || '',
                jslog: (b.getAttribute('jslog') || '').substring(0, 20),
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
