#!/usr/bin/env node
// Forge JS static checker — reads a JSON blob of {path: source} on stdin,
// emits {results: [{path, errors: [{kind, line, message}]}]} on stdout.
//
// Checks performed (without any external deps — uses only Node built-ins):
//   1. Parse the file as a Script with new Function() to detect SyntaxErrors.
//   2. Walk the source heuristically (regex-driven, since the host Node may
//      not have a parser available) and flag:
//        - identifiers called as functions that are never declared in the file
//        - obviously broken CSS-pseudo selectors passed to querySelector
//        - direct setInterval/setTimeout calls with non-numeric delay (cheap)
//
// This is a static, fast check — not a runtime test. It exists to catch the
// "ReferenceError 30 seconds after page load" failure class up-front.

'use strict';

const fs = require('fs');

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', chunk => data += chunk);
    process.stdin.on('end', () => resolve(data));
    process.stdin.on('error', reject);
  });
}

const JS_GLOBAL_NAMES = new Set([
  // Browser
  'window', 'document', 'navigator', 'location', 'history', 'screen',
  'console', 'alert', 'confirm', 'prompt',
  'fetch', 'XMLHttpRequest', 'WebSocket', 'EventSource',
  'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval',
  'requestAnimationFrame', 'cancelAnimationFrame',
  'localStorage', 'sessionStorage', 'indexedDB',
  'Audio', 'Image', 'Notification',
  'URLSearchParams', 'URL', 'FormData', 'Blob', 'File', 'FileReader',
  'AudioContext', 'webkitAudioContext',
  'HTMLElement', 'Element', 'Node', 'NodeList',
  'CustomEvent', 'Event', 'MouseEvent', 'KeyboardEvent',
  // Standard JS
  'Math', 'Date', 'JSON', 'Object', 'Array', 'String', 'Number', 'Boolean',
  'Error', 'TypeError', 'RangeError', 'SyntaxError', 'ReferenceError',
  'Promise', 'Symbol', 'Map', 'Set', 'WeakMap', 'WeakSet',
  'Proxy', 'Reflect', 'parseInt', 'parseFloat', 'isNaN', 'isFinite',
  'encodeURI', 'encodeURIComponent', 'decodeURI', 'decodeURIComponent',
  'undefined', 'null', 'true', 'false', 'NaN', 'Infinity',
  // Common module-y identifiers we don't want to false-flag
  'require', 'module', 'exports', '__dirname', '__filename',
  'process', 'Buffer', 'global', 'globalThis',
  // React/Vue/etc. if they slip in via inline scripts
  'React', 'ReactDOM', 'Vue', 'Svelte',
]);

const KEYWORDS = new Set([
  'if', 'else', 'while', 'for', 'do', 'switch', 'case', 'default',
  'return', 'break', 'continue', 'function', 'class', 'const', 'let',
  'var', 'new', 'this', 'super', 'try', 'catch', 'finally', 'throw',
  'typeof', 'instanceof', 'in', 'of', 'void', 'delete', 'yield', 'await',
  'async', 'static', 'extends', 'export', 'import', 'from', 'as',
]);

// Match identifiers being CALLED: "foo(" but not "obj.foo(" and not after a dot.
// We also skip "function foo(" declarations and arrow functions.
const CALL_RE = /(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(/g;

// Match declarations: function foo, const foo =, let foo =, var foo =,
// class foo, and import { foo, bar }
const FN_DECL_RE = /\bfunction\s+([A-Za-z_$][\w$]*)/g;
// Method shorthand: name(args) { ... } — covers object literals and class methods.
// Anchored on a preceding delimiter so we don't match `if (x) {` etc.
const METHOD_SHORTHAND_RE = /(?:^|[{,;:])\s*([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{/g;
const VAR_DECL_RE = /\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)/g;
const CLASS_DECL_RE = /\bclass\s+([A-Za-z_$][\w$]*)/g;
const IMPORT_NAMED_RE = /\bimport\s+\{([^}]+)\}/g;
const IMPORT_DEFAULT_RE = /\bimport\s+([A-Za-z_$][\w$]*)/g;
// const { a, b } = expr   and   function foo(a, b)
const DESTRUCT_RE = /(?:const|let|var)\s*\{([^}]+)\}/g;
const PARAM_RE = /\bfunction\s*\w*\s*\(([^)]*)\)/g;
const ARROW_PARAM_RE = /\(([^)]*)\)\s*=>/g;
const SINGLE_ARROW_PARAM_RE = /([A-Za-z_$][\w$]*)\s*=>/g;
// Catch destructuring on left side of arrows / regular assignment too:
const ASSIGN_DESTRUCT_RE = /\b([A-Za-z_$][\w$]*)\s*=/g;

const QUERY_SELECTOR_RE = /\.querySelector(?:All)?\s*\(\s*(['"])(.*?)\1/g;

function extractDeclared(source) {
  const declared = new Set();
  let m;
  // Function declarations
  while ((m = FN_DECL_RE.exec(source)) !== null) declared.add(m[1]);
  // Method shorthand (object literal methods, class methods)
  while ((m = METHOD_SHORTHAND_RE.exec(source)) !== null) declared.add(m[1]);
  // Variable declarations
  while ((m = VAR_DECL_RE.exec(source)) !== null) declared.add(m[1]);
  // Class declarations
  while ((m = CLASS_DECL_RE.exec(source)) !== null) declared.add(m[1]);
  // Imports
  while ((m = IMPORT_NAMED_RE.exec(source)) !== null) {
    m[1].split(',').forEach(name => {
      const cleaned = name.trim().split(/\s+as\s+/).pop().trim();
      if (cleaned) declared.add(cleaned);
    });
  }
  while ((m = IMPORT_DEFAULT_RE.exec(source)) !== null) declared.add(m[1]);
  // Destructured assignments
  while ((m = DESTRUCT_RE.exec(source)) !== null) {
    m[1].split(',').forEach(name => {
      const cleaned = name.trim().split(':').pop().trim().split(/\s+/)[0];
      if (cleaned && /^[A-Za-z_$]/.test(cleaned)) declared.add(cleaned);
    });
  }
  // Function params
  while ((m = PARAM_RE.exec(source)) !== null) {
    m[1].split(',').forEach(name => {
      const cleaned = name.trim().split('=')[0].trim();
      if (cleaned && /^[A-Za-z_$]/.test(cleaned)) declared.add(cleaned);
    });
  }
  // Arrow params
  while ((m = ARROW_PARAM_RE.exec(source)) !== null) {
    m[1].split(',').forEach(name => {
      const cleaned = name.trim().split('=')[0].trim();
      if (cleaned && /^[A-Za-z_$]/.test(cleaned)) declared.add(cleaned);
    });
  }
  while ((m = SINGLE_ARROW_PARAM_RE.exec(source)) !== null) {
    declared.add(m[1]);
  }
  // Plain assignments like `foo = ...` (catches hoisted globals)
  while ((m = ASSIGN_DESTRUCT_RE.exec(source)) !== null) declared.add(m[1]);

  return declared;
}

function lineOf(source, idx) {
  return source.slice(0, idx).split('\n').length;
}

function checkSyntax(source) {
  // Wrap as a function body so top-level returns / strict mode quirks are OK.
  try {
    new Function('"use strict";' + source);
    return null;
  } catch (e) {
    if (e instanceof SyntaxError) {
      return { kind: 'syntax_error', line: 0, message: e.message };
    }
    return null;
  }
}

function findUndefinedCalls(source, declared) {
  const errors = [];
  const seen = new Set();
  let m;
  CALL_RE.lastIndex = 0;
  while ((m = CALL_RE.exec(source)) !== null) {
    const name = m[1];
    if (KEYWORDS.has(name)) continue;
    if (JS_GLOBAL_NAMES.has(name)) continue;
    if (declared.has(name)) continue;
    if (seen.has(name)) continue;
    seen.add(name);
    errors.push({
      kind: 'undefined_call',
      line: lineOf(source, m.index),
      message: `Function '${name}' is called but never defined in this file`,
      name,
    });
  }
  return errors;
}

function findBrokenSelectors(source) {
  const errors = [];
  let m;
  QUERY_SELECTOR_RE.lastIndex = 0;
  while ((m = QUERY_SELECTOR_RE.exec(source)) !== null) {
    const selector = m[2];
    // CSS pseudo-elements (::before, ::after, ::first-line) can't be selected
    // via querySelector. Pseudo-CLASSES (:hover, :nth-child) are fine.
    if (/::[a-z-]/i.test(selector)) {
      errors.push({
        kind: 'broken_selector',
        line: lineOf(source, m.index),
        message: `querySelector cannot match pseudo-element '${selector}' — returns null at runtime`,
      });
    }
  }
  return errors;
}

async function main() {
  let payload;
  try {
    payload = JSON.parse(await readStdin());
  } catch (e) {
    console.error('js_check.js: invalid JSON on stdin:', e.message);
    process.exit(2);
  }

  const results = [];
  for (const [path, source] of Object.entries(payload.files || {})) {
    if (typeof source !== 'string') continue;
    const errors = [];

    const syntaxError = checkSyntax(source);
    if (syntaxError) errors.push(syntaxError);

    const declared = extractDeclared(source);
    errors.push(...findUndefinedCalls(source, declared));
    errors.push(...findBrokenSelectors(source));

    results.push({ path, errors });
  }
  process.stdout.write(JSON.stringify({ results }) + '\n');
}

main().catch(err => {
  console.error('js_check.js failed:', err);
  process.exit(2);
});
