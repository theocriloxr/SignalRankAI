import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const view = readFileSync(new URL("../src/components/WatchlistsView.tsx", import.meta.url), "utf8");

test("watched instruments show their symbol and can be removed one at a time", () => {
  assert.match(view, /label:display\(x\.display_symbol,display\(x\.instrument_id,""\)\)/);
  assert.match(view, /client\.DELETE\("\/api\/v1\/platform\/watchlists\/\{watchlist_id\}\/items\/\{instrument_id\}"/);
  assert.match(view, /aria-label=\{`Remove \$\{x\.label\} from \$\{name\}`\}/);
});

test("deleting a whole list takes a second, explicit click", () => {
  assert.match(view, /client\.DELETE\("\/api\/v1\/platform\/watchlists\/\{watchlist_id\}"/);
  assert.match(view, /confirmDelete\?<>/);
  assert.match(view, /onClick=\{\(\)=>setConfirmDelete\(true\)\}>Delete watchlist<\/button>/);
  assert.match(view, /onClick=\{deleteList\}/);
});

test("watchlists never reach execution paths", () => {
  assert.doesNotMatch(view, /\/execute|\/broker\/|place.order/);
});
