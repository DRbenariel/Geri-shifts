// Cloudflare Worker in front of the static UI. /api/* is proxied to the Cloud Run API so the browser
// sees one origin (the session cookie stays first-party; Safari blocks third-party cookies).
// API_ORIGIN (e.g. https://geri-api-xxxx.me-west1.run.app) is a Worker variable; while it is unset
// /api answers 404, and the UI falls back to its demo data.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/api/')) {
      if (!env.API_ORIGIN) return new Response('{"detail":"no backend"}', { status: 404, headers: { 'content-type': 'application/json' } });
      const target = new URL(url.pathname + url.search, env.API_ORIGIN);
      const init = { method: request.method, headers: request.headers, redirect: 'manual' };
      if (!['GET', 'HEAD'].includes(request.method)) init.body = request.body;
      return fetch(new Request(target, init));
    }
    return env.ASSETS.fetch(request);
  },
};
