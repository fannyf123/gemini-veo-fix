"""
js_constants.py

Semua JavaScript untuk Shadow DOM automation di business.gemini.google.
Step 16-19 menggunakan level-by-level shadow traversal berdasarkan
CSS selector yang dikonfirmasi langsung dari DevTools.

Step 16: md-dialog > md-text-button → #button > span.touch
Step 17: .tools-button-container > #tool-selector-menu-anchor → #button > span.touch
Step 18: .tools-button-container > md-menu > div:nth-child(7) > md-menu-item > div
Step 19: #agent-search-prosemirror-editor → div > div > div > p
"""

# ================================================================
# Step 16 - Dismiss popup 'I'll do this later'
# Trace: [shadow host] → md-dialog > md-text-button → #button → #button > span.touch
# ================================================================
_JS_DISMISS_POPUP = """
(function() {
    // Traverse semua shadow root untuk menemukan md-dialog
    function getShadow(el) {
        return el && el.shadowRoot ? el.shadowRoot : null;
    }
    function findAndClick(root, depth) {
        if (!root || depth > 10) return false;
        // Cari md-text-button di dalam md-dialog
        var dialog = root.querySelector ? root.querySelector('md-dialog') : null;
        if (dialog) {
            // Cari md-text-button berteks 'do this later' atau 'later'
            var btns = dialog.querySelectorAll('md-text-button');
            for (var i = 0; i < btns.length; i++) {
                var txt = (btns[i].textContent || '').toLowerCase();
                if (txt.includes('later') || txt.includes('skip')) {
                    var s = getShadow(btns[i]);
                    var touch = s && (s.querySelector('#button > span.touch') || s.querySelector('span.touch') || s.querySelector('#button'));
                    if (touch) { touch.click(); return true; }
                    btns[i].click(); return true;
                }
            }
        }
        // Fallback: scan semua md-text-button di root ini
        var allBtns = root.querySelectorAll ? root.querySelectorAll('md-text-button') : [];
        for (var j = 0; j < allBtns.length; j++) {
            var t = (allBtns[j].textContent || '').toLowerCase();
            if (t.includes('later') || t.includes('skip') || t.includes("i'll do")) {
                var sr = getShadow(allBtns[j]);
                var tch = sr && (sr.querySelector('#button > span.touch') || sr.querySelector('span.touch') || sr.querySelector('#button'));
                if (tch) { tch.click(); return true; }
                allBtns[j].click(); return true;
            }
        }
        // Rekursi ke shadow root anak
        var all = root.querySelectorAll ? root.querySelectorAll('*') : [];
        for (var k = 0; k < all.length; k++) {
            if (all[k].shadowRoot && findAndClick(all[k].shadowRoot, depth + 1)) return true;
        }
        return false;
    }
    return findAndClick(document, 0);
})();
"""

# ================================================================
# Step 17 - Click tools button
# Trace dari DevTools:
# (1) div > form > div > div.actions-buttons... > div.tools-button-container
# (2) #tool-selector-menu-anchor  ← md-text-button
# (3) #button
# (4) #button > span.touch         ← klik di sini
# ================================================================
_JS_CLICK_TOOLS = """
(function() {
    function getShadow(el) { return el && el.shadowRoot ? el.shadowRoot : null; }

    function tryClick(root) {
        if (!root) return false;
        // Cari container tools
        var container = root.querySelector('.tools-button-container');
        if (container) {
            var btn = container.querySelector('#tool-selector-menu-anchor');
            if (!btn) btn = container.querySelector('md-text-button');
            if (btn) {
                var s = getShadow(btn);
                var touch = s && (s.querySelector('#button > span.touch') || s.querySelector('span.touch') || s.querySelector('#button'));
                if (touch) { touch.click(); return true; }
                btn.click(); return true;
            }
        }
        // Fallback langsung cari #tool-selector-menu-anchor
        var btn2 = root.querySelector('#tool-selector-menu-anchor');
        if (btn2) {
            var s2 = getShadow(btn2);
            var t2 = s2 && (s2.querySelector('#button > span.touch') || s2.querySelector('span.touch') || s2.querySelector('#button'));
            if (t2) { t2.click(); return true; }
            btn2.click(); return true;
        }
        return false;
    }

    function deepScan(root, depth) {
        if (!root || depth > 10) return false;
        if (tryClick(root)) return true;
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
# Trace dari DevTools:
# (1) div.tools-button-container > md-menu
# (2) md-menu > div:nth-child(7) > md-menu-item
# (3) md-menu-item > div   ← klik div headline ini
# ================================================================
_JS_CLICK_VEO = """
(function() {
    function getShadow(el) { return el && el.shadowRoot ? el.shadowRoot : null; }

    function tryClickVeo(root) {
        if (!root) return false;
        // Cari md-menu di dalam tools-button-container
        var container = root.querySelector('.tools-button-container');
        var menu = container ? container.querySelector('md-menu') : root.querySelector('md-menu');
        if (menu) {
            // Cari md-menu-item yang teksnya mengandung 'veo' atau 'create video'
            var items = menu.querySelectorAll('md-menu-item');
            for (var i = 0; i < items.length; i++) {
                var txt = (items[i].textContent || '').toLowerCase();
                if (txt.includes('veo') || txt.includes('create video')) {
                    // Klik div headline di dalam md-menu-item
                    var div = items[i].querySelector('div');
                    if (div) { div.click(); return true; }
                    // Fallback: klik span.touch di shadow root item
                    var s = getShadow(items[i]);
                    var touch = s && (s.querySelector('#item > span.touch') || s.querySelector('span.touch') || s.querySelector('#item'));
                    if (touch) { touch.click(); return true; }
                    items[i].click(); return true;
                }
            }
            // Fallback: nth-child(7) jika tidak ada teks match
            var menuItems = menu.querySelectorAll('md-menu-item');
            if (menuItems.length >= 1) {
                // Coba semua item sampai ketemu yang visible dan punya 'veo'
                for (var j = 0; j < menuItems.length; j++) {
                    var t2 = (menuItems[j].textContent || '').toLowerCase();
                    if (t2.includes('video') || t2.includes('veo')) {
                        var d2 = menuItems[j].querySelector('div');
                        if (d2) { d2.click(); return true; }
                        menuItems[j].click(); return true;
                    }
                }
            }
        }
        return false;
    }

    function deepScan(root, depth) {
        if (!root || depth > 10) return false;
        if (tryClickVeo(root)) return true;
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
# Trace dari DevTools:
# (1) #agent-search-prosemirror-editor  ← shadow host
# (2) shadowRoot → div > div > div > p  ← contenteditable target
# ================================================================
_JS_GET_PROMPT_INPUT = """
(function() {
    function getShadow(el) { return el && el.shadowRoot ? el.shadowRoot : null; }

    function findEditor(root, depth) {
        if (!root || depth > 10) return null;
        // Primary: cari by id
        var host = root.querySelector ? root.querySelector('#agent-search-prosemirror-editor') : null;
        if (host) {
            var s = getShadow(host);
            if (s) {
                var p = s.querySelector('div > div > div > p') ||
                        s.querySelector('.ProseMirror') ||
                        s.querySelector("[contenteditable='true']");
                if (p) return p;
            }
            return host;
        }
        // Secondary: cari by tag
        var host2 = root.querySelector ? root.querySelector('ucs-prosemirror-editor') : null;
        if (host2) {
            var s2 = getShadow(host2);
            if (s2) {
                var p2 = s2.querySelector('div > div > div > p') ||
                         s2.querySelector('.ProseMirror') ||
                         s2.querySelector("[contenteditable='true']");
                if (p2) return p2;
            }
            return host2;
        }
        // Rekursi
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
# Step 20 - Get thinking/loading indicator
# ================================================================
_JS_GET_THINKING = """
(function() {
    function findThoughts(root, depth) {
        if (!root || depth > 10) return null;
        var el = root.querySelector ? root.querySelector('ucs-agent-thoughts.show-summary-text') : null;
        if (el) return el;
        el = root.querySelector ? root.querySelector('ucs-agent-thoughts') : null;
        if (el) return el;
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
# ================================================================
_JS_CLICK_DOWNLOAD = """
(function() {
    function getShadow(el) { return el && el.shadowRoot ? el.shadowRoot : null; }
    function clickBtn(btn) {
        if (!btn) return false;
        var s = getShadow(btn);
        var touch = s && (s.querySelector('#button > span.touch') || s.querySelector('span.touch') || s.querySelector('#button'));
        if (touch) { touch.click(); return true; }
        btn.click(); return true;
    }
    function findDownload(root, depth) {
        if (!root || depth > 10) return false;
        var btn = root.querySelector ? root.querySelector('.download-button') : null;
        if (btn) return clickBtn(btn);
        btn = root.querySelector ? root.querySelector("[data-aria-label='Download video file']") : null;
        if (btn) return clickBtn(btn);
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
# Step 21b - Click download confirmation dialog
# ================================================================
_JS_CLICK_CONFIRM = """
(function() {
    function getShadow(el) { return el && el.shadowRoot ? el.shadowRoot : null; }
    function clickBtn(btn) {
        if (!btn) return false;
        var s = getShadow(btn);
        var touch = s && (s.querySelector('#button > span.touch') || s.querySelector('span.touch') || s.querySelector('#button'));
        if (touch) { touch.click(); return true; }
        btn.click(); return true;
    }
    function findConfirm(root, depth) {
        if (!root || depth > 10) return false;
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
} catch(e) { return null; }
"""

# ================================================================
# List all buttons in shadow DOM (debug)
# ================================================================
_JS_LIST_BUTTONS = """
(function() {
    var result = [];
    function scan(root, depth) {
        if (depth > 10) return;
        var btns = root.querySelectorAll('button, md-icon-button, md-filled-icon-button, md-text-button');
        btns.forEach(function(b) {
            result.push({
                tag: b.tagName, id: b.id || '',
                cls: b.getAttribute('class') || '',
                aria: b.getAttribute('aria-label') || b.getAttribute('data-aria-label') || '',
                jslog: (b.getAttribute('jslog') || '').substring(0, 30),
                text: (b.innerText || b.textContent || '').trim().substring(0, 80),
                visible: b.offsetParent !== null
            });
        });
        root.querySelectorAll('*').forEach(function(el) {
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
# Find and click Regenerate button
# ================================================================
_JS_CLICK_REGENERATE = """
(function() {
    let clicked = false;
    function scanAndClick(root) {
        if (clicked) return false;
        let btns = root.querySelectorAll('button, md-text-button, span');
        for (let b of btns) {
            let text = (b.innerText || b.textContent || '').trim().toLowerCase();
            if (text.includes('regenerate')) {
                let target = (b.tagName === 'SPAN' && b.parentElement) ? b.parentElement : b;
                target.click();
                if (target.shadowRoot) {
                    let inner = target.shadowRoot.querySelector('#button > span.touch') || target.shadowRoot.querySelector('button');
                    if (inner) inner.click();
                }
                clicked = true; return true;
            }
        }
        for (let el of root.querySelectorAll('*')) {
            if (el.shadowRoot && scanAndClick(el.shadowRoot)) return true;
        }
        return false;
    }
    return scanAndClick(document);
})();
"""

# ================================================================
# Find blob video src
# ================================================================
_JS_GET_VIDEO_SRC = """
(function() {
    let result = null;
    function scanForVideo(root) {
        if (result) return true;
        for (let v of root.querySelectorAll('video, source')) {
            let src = (v.getAttribute('src') || '').trim();
            if (src.startsWith('blob:')) { result = src; return true; }
        }
        for (let el of root.querySelectorAll('*')) {
            if (el.shadowRoot && scanForVideo(el.shadowRoot)) return true;
        }
        return false;
    }
    scanForVideo(document);
    return result;
})();
"""

# ================================================================
# Fetch blob as Base64
# ================================================================
_JS_FETCH_BLOB_BASE64 = """
var blobUrl = arguments[0];
var callback = arguments[1];
fetch(blobUrl)
    .then(r => r.blob())
    .then(blob => {
        var reader = new FileReader();
        reader.onloadend = function() { callback(reader.result.split(',')[1]); };
        reader.readAsDataURL(blob);
    })
    .catch(e => { callback("ERROR: " + e.toString()); });
"""
