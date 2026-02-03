# Build Rules

## Stack
- Manifest: V3 (required for Chrome Web Store)
- UI: Vanilla JS or React (for popup)
- Styling: Tailwind CSS or vanilla CSS
- Build: Vite with CRXJS plugin (optional)

## Structure
```
/
├── manifest.json          # Extension config
├── popup/                 # Popup UI
│   ├── popup.html
│   ├── popup.js
│   └── popup.css
├── content/               # Content scripts
│   └── content.js
├── background/            # Service worker
│   └── service-worker.js
├── options/               # Options page
│   ├── options.html
│   └── options.js
├── icons/                 # Extension icons
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
└── README.md
```

## Manifest V3 Template
```json
{
  "manifest_version": 3,
  "name": "Your Extension",
  "version": "1.0.0",
  "description": "What it does",
  "permissions": ["activeTab", "storage"],
  "action": {
    "default_popup": "popup/popup.html",
    "default_icon": {
      "16": "icons/icon16.png",
      "48": "icons/icon48.png",
      "128": "icons/icon128.png"
    }
  },
  "content_scripts": [{
    "matches": ["<all_urls>"],
    "js": ["content/content.js"]
  }],
  "background": {
    "service_worker": "background/service-worker.js"
  }
}
```

## Constraints
- Use Manifest V3 (V2 is deprecated)
- Request minimum permissions
- No remote code execution
- Handle offline gracefully

## Chrome APIs
```javascript
// Storage
chrome.storage.local.set({ key: value });
chrome.storage.local.get(['key'], (result) => {});

// Messaging (popup <-> content script)
chrome.tabs.sendMessage(tabId, message);
chrome.runtime.onMessage.addListener((msg, sender, reply) => {});

// Current tab
chrome.tabs.query({ active: true, currentWindow: true });
```

## Content Script Rules
- Run at document_idle by default
- Don't conflict with page styles (scope CSS)
- Clean up when page unloads
- Handle dynamic content (MutationObserver)

## Popup Rules
- Keep it simple and fast
- Save state to chrome.storage
- Close popup doesn't kill functionality
- 400px max width recommended

## Security Rules
- Never eval() external content
- Validate all message data
- Use CSP (Content Security Policy)
- No inline scripts in HTML

## Testing
```bash
# Load unpacked extension
1. Go to chrome://extensions
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select your extension folder
```

## Deploy Target
- Chrome Web Store ($5 one-time fee)
- Or share as .zip for direct install
