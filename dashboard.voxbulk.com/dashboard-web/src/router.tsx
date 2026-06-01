import { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";

export const getRouter = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 1000 * 60 * 5, // 5 minutes - don't refetch fresh data
        gcTime: 1000 * 60 * 10, // 10 minutes - keep cached data
        retry: 1, // Retry failed requests once
        refetchOnWindowFocus: false, // Don't refetch when window regains focus
        refetchOnReconnect: true, // Do refetch when connection is restored
      },
      mutations: {
        retry: 1,
      },
    },
  });

  const router = createRouter({
    routeTree,
    context: { queryClient },
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
  });

  return router;
};
