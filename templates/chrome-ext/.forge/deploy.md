# Deployment Guide

## Option 1: Direct Install (Demo/Testing)

Share your extension without the Chrome Web Store.

### Package the extension
```bash
# Create a zip file
cd your-extension
zip -r ../extension.zip . -x "*.git*"
```

### Share with others
1. Send them the `extension.zip` file
2. They extract it
3. Go to `chrome://extensions`
4. Enable "Developer mode"
5. Click "Load unpacked" and select the folder

---

## Option 2: Chrome Web Store

Official distribution (requires $5 one-time fee).

### Prepare for submission
1. Create icons in all sizes: 16x16, 48x48, 128x128
2. Take screenshots (1280x800 or 640x400)
3. Write a description (132 chars for short, 16K for full)
4. Create a privacy policy (required)

### Submit
1. Go to [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole)
2. Pay $5 registration fee (one-time)
3. Click "New Item"
4. Upload your zip file
5. Fill in listing details
6. Submit for review (takes 1-3 days)

### Update your extension
1. Increment version in `manifest.json`
2. Upload new zip to dashboard
3. Submit for review

---

## Option 3: Self-Hosted

Host on your website for direct install.

### Create update manifest
```xml
<?xml version='1.0' encoding='UTF-8'?>
<gupdate xmlns='http://www.google.com/update2/response' protocol='2.0'>
  <app appid='YOUR_EXTENSION_ID'>
    <updatecheck codebase='https://yoursite.com/extension.crx' version='1.0.0' />
  </app>
</gupdate>
```

Note: Self-hosted extensions only work for enterprise policy-managed browsers.

---

## Pre-Publish Checklist

- [ ] All features work as expected
- [ ] No console errors
- [ ] manifest.json has correct permissions (minimal)
- [ ] Icons in all required sizes
- [ ] Privacy policy ready (if storing data)
- [ ] Screenshots captured
- [ ] Description written

---

## For Hackathons

Don't need Chrome Web Store! Just:
1. Zip your extension
2. Demo from `chrome://extensions` > Load unpacked
3. Share zip with judges if they want to try
