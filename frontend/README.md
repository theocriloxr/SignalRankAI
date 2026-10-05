# SignalRankAI replacement web application

This Next.js application is being integrated with the canonical FastAPI
platform API. Public pages and theme controls exist; the authenticated
overview and catch-all routes still contain descriptive content. They have
not demonstrated full customer-flow parity with the serving web/platform_app
application. Production continues to serve that application while integration
and acceptance remain incomplete.

Run npm ci, npm run dev, npm run lint, npm run test:transport, and npm run build
from this directory. Read AGENTS.md and the installed Next.js guides before
changing the application.

The typed client sends cookie credentials and copies sr_csrf into
X-CSRF-Token for mutations. Access/refresh cookies remain HttpOnly and are
never copied into JavaScript storage. Server-rendered calls do not inherit
browser credentials. NEXT_PUBLIC_SIGNALRANK_API_BASE_URL may select a backend;
browser cookies and CORS must be configured for that origin. A shared origin
through the frontdoor is the intended deployment arrangement. Authentication,
session-refresh UI, role navigation and route workflows remain pending;
transport tests do not certify those features.
