# Node dependency repairs — 7 October 2026

The required frontend and mobile audit gates scan the complete locked graphs.
No advisory exclusions, severity exceptions or fabricated upstream versions
are applied. Local adapters have their own SignalRank package names and their
source is included in the release commit.

## Frontend

The pinned Next ESLint plugin consumes only `globSync(pattern,
{onlyDirectories:true})` from fast-glob. Its fast-glob/micromatch/braces chain is
replaced with `@signalrank/next-root-glob`, backed by official tinyglobby 0.2.17.
The adapter preserves directory-only results, disables automatic expansion of
matched directories and returns absolute results for absolute patterns.
It rejects patterns longer than 4,096 characters or nested beyond 64 levels,
and refuses unsupported options. The Next rules and TypeScript lint rules
remain enabled. CommonJS imports are allowed for this synchronously loaded
adapter; the other lint rules still apply to it.

The installed-consumer tests verify monorepo roots, arrays, brace alternatives,
Windows separators, missing roots, actual internal-link violations and bounded
rejection of deeply nested inputs. An initial direct alias to tinyglobby failed
the directory and hostile-input tests and was replaced with this adapter.

## Mobile

Expo is pinned to 57.0.27 with SDK-matched React Native 0.86.3, native module
versions and TypeScript 6.0.3. The unused deprecated `baseUrl` is removed rather
than suppressing its compiler error. The current Expo file-map patch no longer
depends on micromatch. The remaining standard Metro file-map consumes only
`some(path, patterns, {dot})`; `@signalrank/metro-watch-glob` implements that
bounded watcher interface using official picomatch 4.0.4. Input length,
collection size, nesting and options are checked before parsing.

Tests call the actual installed Metro watcher for inclusion, exclusion,
directory, dotfile, brace, extglob and negation behavior. Session/Telegram
reconciliation tests remain required. Android and iOS JavaScript exports do
not replace native build or physical-device testing.

## Installation and evidence

Both projects set `install-links=true` so npm installs the local packages as
packages rather than mutable external links. Their spec references in
`overrides` point to the declared local dependency. `npm ci` must succeed on a
clean candidate; an npm lock that merely audits cleanly is insufficient.
The local package source is verified by the immutable repository source
fingerprint; upstream dependencies retain their registry integrity hashes.

The frontend full-graph audit currently reports zero vulnerabilities. Mobile
currently reports four high-severity rows, all from node-forge and the inheriting
Expo code-signing/CLI packages. They remain release blockers. The reviewed
[node-forge advisory](https://github.com/advisories/GHSA-86w9-cpqp-85rv) lists no
patched version. A successful functional export cannot waive this finding.

Upstream references:

- [tinyglobby source and documented API](https://github.com/SuperchupuDev/tinyglobby)
- [picomatch source and documented API](https://github.com/micromatch/picomatch)
- [braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
- [TypeScript 6.0 migration notes](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-6-0.html)

## Production boundaries

Railway's four application services watch the required branch and all paths,
and wait for CI. Source approval queues the latest exact certified commit;
failed CI cannot advance those pins. Manual attempts of uncertified newer
commits fail the source pre-deploy guard. Production approval, schema admission,
backup freshness, market/account certification and clean release observation
remain required. This repair does not enable financial execution.
