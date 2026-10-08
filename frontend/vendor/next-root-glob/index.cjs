"use strict";

const path = require("node:path");
const tinyglobby = require("tinyglobby");

// This implements the single API consumed by the pinned Next ESLint plugin.
// It is not a general fast-glob replacement. Refuse API drift and excessive
// patterns before glob parsing or filesystem traversal.
function globSync(pattern, options) {
  if (typeof pattern !== "string" || pattern.length > 4096 || pattern.includes("\0")) {
    throw new TypeError("Next root directory pattern must be a string of at most 4096 characters");
  }
  if (!options || options.onlyDirectories !== true || Object.keys(options).some(key => key !== "onlyDirectories")) {
    throw new TypeError("Next root discovery requires onlyDirectories: true");
  }
  let nesting = 0;
  let escaped = false;
  for (const character of pattern) {
    if (escaped) { escaped = false; continue; }
    if (character === "\\") { escaped = true; continue; }
    if (character === "{" || character === "(") {
      if (++nesting > 64) throw new RangeError("Next root directory pattern nesting exceeds 64");
    } else if (character === "}" || character === ")") {
      nesting = Math.max(0, nesting - 1);
    }
  }
  return tinyglobby.globSync(pattern, {
    onlyDirectories: true,
    expandDirectories: false,
    absolute: path.isAbsolute(pattern),
  });
}

module.exports = { globSync };
