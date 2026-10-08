"use strict";

const picomatch = require("picomatch");

function boundedStrings(value, kind) {
  const values = Array.isArray(value) ? value : [value];
  if (values.length > 256 || values.some(item => typeof item !== "string" || item.length > 4096 || item.includes("\0"))) {
    throw new TypeError(`Metro ${kind} must contain at most 256 strings of at most 4096 characters`);
  }
  return values;
}

// The pinned metro-file-map consumes only some(path, globs, {dot}). This is
// deliberately a watcher adapter, not an implementation of micromatch's API.
function some(paths, patterns, options = {}) {
  if (!options || Object.keys(options).some(key => key !== "dot") ||
      (options.dot !== undefined && typeof options.dot !== "boolean")) {
    throw new TypeError("Metro watcher matching supports only a boolean dot option");
  }
  const items = boundedStrings(paths, "paths");
  const globs = boundedStrings(patterns, "patterns");
  for (const pattern of globs) {
    let depth = 0;
    let escaped = false;
    for (const character of pattern) {
      if (escaped) { escaped = false; continue; }
      if (character === "\\") { escaped = true; continue; }
      if (character === "{" || character === "(") {
        if (++depth > 64) throw new RangeError("Metro pattern nesting exceeds 64");
      } else if (character === "}" || character === ")") {
        depth = Math.max(0, depth - 1);
      }
    }
  }
  return globs.some(pattern => items.some(picomatch(pattern, options)));
}

module.exports = { some };
