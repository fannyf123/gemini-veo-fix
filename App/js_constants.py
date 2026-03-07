"""
js_constants.py

Semua JavaScript selector string untuk Shadow DOM automation
di business.gemini.google
"""

# Step 16 - Dismiss popup 'I'll do this later'
_JS_DISMISS_POPUP = """
return document.querySelector("body > ucs-standalone-app").shadowRoot
    .querySelector("ucs-welcome-dialog").shadowRoot
    .querySelector("div > md-dialog > div:nth-child(3) > md-text-button").shadowRoot
    .querySelector("#button > span.touch");
"""

# Step 17 - Click tools button
_JS_CLICK_TOOLS = """
return document.querySelector("body > ucs-standalone-app").shadowRoot
    .querySelector("div > div.ucs-standalone-outer-row-container > div > ucs-chat-landing").shadowRoot
    .querySelector("div > div > div > div.fixed-content > ucs-search-bar").shadowRoot
    .querySelector("#tool-selector-menu-anchor").shadowRoot
    .querySelector("#button > span.touch");
"""

# Step 18 - Click 'Create videos with Veo'
_JS_CLICK_VEO = """
return document.querySelector("body > ucs-standalone-app").shadowRoot
    .querySelector("div > div.ucs-standalone-outer-row-container > div > ucs-chat-landing").shadowRoot
    .querySelector("div > div > div > div.fixed-content > ucs-search-bar").shadowRoot
    .querySelector("div > form > div > div.actions-buttons.omnibar.multiline-input-actions-buttons > div.tools-button-container > md-menu > div:nth-child(7) > md-menu-item > div");
"""

# Step 19 - Get prompt input element
_JS_GET_PROMPT_INPUT = """
return document.querySelector("body > ucs-standalone-app").shadowRoot
    .querySelector("div > div.ucs-standalone-outer-row-container > div > ucs-chat-landing").shadowRoot
    .querySelector("div > div > div > div.fixed-content > ucs-search-bar").shadowRoot
    .querySelector("#agent-search-prosemirror-editor").shadowRoot
    .querySelector("div > div > div > p");
"""

# Step 20 - Get thinking message element
_JS_GET_THINKING = """
return document.querySelector("body > ucs-standalone-app").shadowRoot
    .querySelector("div > div.ucs-standalone-outer-row-container > div > div.search-bar-and-results-container > div > ucs-results").shadowRoot
    .querySelector("div > div > div.tile.chat-mode-conversation.chat-mode-conversation > div.chat-mode-scroller.tile-content > ucs-conversation").shadowRoot
    .querySelector("div > div.turn.last > ucs-summary").shadowRoot
    .querySelector("div > div > div.summary-contents > div.header.agent-thoughts-header > ucs-agent-thoughts").shadowRoot
    .querySelector("div.header > div.thinking-message");
"""

# Step 21a - Click download button
_JS_CLICK_DOWNLOAD = """
return document.querySelector("body > ucs-standalone-app").shadowRoot
    .querySelector("div > div.ucs-standalone-outer-row-container > div > div.search-bar-and-results-container > div > ucs-results").shadowRoot
    .querySelector("div > div > div.tile.chat-mode-conversation.chat-mode-conversation > div.chat-mode-scroller.tile-content > ucs-conversation").shadowRoot
    .querySelector("div > div > ucs-summary").shadowRoot
    .querySelector("div > div > div.summary-contents > ucs-summary-attachments").shadowRoot
    .querySelector("div > ucs-markdown-video").shadowRoot
    .querySelector("div > div.video-actions > md-filled-icon-button").shadowRoot
    .querySelector("#button > span.touch");
"""

# Step 21b - Click download confirmation
_JS_CLICK_CONFIRM = """
return document.querySelector("body > ucs-standalone-app").shadowRoot
    .querySelector("div > div.ucs-standalone-outer-row-container > div > div.search-bar-and-results-container > div > ucs-results").shadowRoot
    .querySelector("div > div > div.tile.chat-mode-conversation.chat-mode-conversation > div.chat-mode-scroller.tile-content > ucs-conversation").shadowRoot
    .querySelector("div > div > ucs-summary").shadowRoot
    .querySelector("div > div > div.summary-contents > ucs-summary-attachments").shadowRoot
    .querySelector("div > ucs-markdown-video").shadowRoot
    .querySelector("ucs-download-warning-dialog").shadowRoot
    .querySelector("md-dialog > div:nth-child(3) > md-text-button.action-button").shadowRoot
    .querySelector("#button > span.touch");
"""

# Get attachment status/error text inside shadow DOM
_JS_GET_ATTACHMENT_STATUS = """
try {
    var span = document.querySelector("body > ucs-standalone-app").shadowRoot
        .querySelector("div > div.ucs-standalone-outer-row-container > div > div.search-bar-and-results-container > div > ucs-results").shadowRoot
        .querySelector("div > div > div.tile.chat-mode-conversation.chat-mode-conversation > div.chat-mode-scroller.tile-content > ucs-conversation").shadowRoot
        .querySelector("div > div > ucs-summary").shadowRoot
        .querySelector("div > div > div.summary-contents > ucs-summary-attachments").shadowRoot
        .querySelector("div > div > span");
    return span ? span.textContent : null;
} catch(e) {
    return null;
}
"""

# List all buttons in shadow DOM (for debug)
_JS_LIST_BUTTONS = """
(function() {
    var result = [];
    function scan(root, depth) {
        if (depth > 10) return;
        var btns = root.querySelectorAll('button, gds-button, gmp-button');
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

# Extract all text across shadow DOMs
_JS_GET_ALL_TEXT_DEEP = """
(function() {
    let result = "";
    function traverse(node) {
        if (!node) return;
        if (node.nodeType === Node.TEXT_NODE) {
            let text = node.textContent.trim();
            if (text) result += " " + text;
        } else if (node.nodeType === Node.ELEMENT_NODE || node.nodeType === Node.DOCUMENT_FRAGMENT_NODE) {
            if (node.shadowRoot) {
                traverse(node.shadowRoot);
            }
            if (node.tagName !== 'SCRIPT' && node.tagName !== 'STYLE') {
                for (let child of node.childNodes) {
                    traverse(child);
                }
            }
        }
    }
    traverse(document.body);
    return result;
})();
"""

# Find and click "Regenerate" button inside shadow roots
_JS_CLICK_REGENERATE = """
(function() {
    let clicked = false;
    function scanAndClick(root) {
        if (clicked) return;
        let btns = root.querySelectorAll('button, gds-button, md-text-button, gmp-button, span');
        for (let i = 0; i < btns.length; i++) {
            let b = btns[i];
            let text = (b.innerText || b.textContent || '').trim().toLowerCase();
            if (text === 'regenerate the response' || text === 'regenerate' || text.includes('regenerate')) {
                let target = b;
                if (b.tagName === 'SPAN' && b.parentElement) {
                    target = b.parentElement;
                }
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
            if (all[i].shadowRoot) {
                if(scanAndClick(all[i].shadowRoot)) return true;
            }
        }
        return false;
    }
    return scanAndClick(document);
})();
"""

# Find <video> or <source> tags deep inside Shadow DOMs with a 'blob:' src
_JS_GET_VIDEO_SRC = """
(function() {
    let result = null;
    function scanForVideo(root) {
        if (result) return true;
        let videos = root.querySelectorAll('video, source');
        for (let i = 0; i < videos.length; i++) {
            let src = (videos[i].getAttribute('src') || '').trim();
            if (src.startsWith('blob:')) {
                result = src;
                return true;
            }
        }
        let all = root.querySelectorAll('*');
        for (let i = 0; i < all.length; i++) {
            if (all[i].shadowRoot) {
                if (scanForVideo(all[i].shadowRoot)) return true;
            }
        }
        return false;
    }
    scanForVideo(document);
    return result;
})();
"""

# Fetch a blob URL, read as ArrayBuffer, convert to Base64, return to Selenium
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
    .catch(error => {
        callback("ERROR: " + error.toString());
    });
"""
