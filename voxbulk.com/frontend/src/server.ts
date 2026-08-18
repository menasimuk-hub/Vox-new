type ServerEntry = {
  fetch: (request: Request, env: unknown, ctx: unknown) => Promise<Response> | Response;
};

export default {
  async fetch(request: Request, env: unknown, ctx: unknown) {
    const mod = await import("@tanstack/react-start/server-entry");
    const handler = (mod.default ?? mod) as ServerEntry;
    return handler.fetch(request, env, ctx);
  },
};
