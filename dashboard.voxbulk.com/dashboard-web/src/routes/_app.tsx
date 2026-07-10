import { createFileRoute, Outlet } from "@tanstack/react-router";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/app-sidebar";
import { LiveChatFab, TopBar } from "@/components/top-bar";
import { ThemeProvider } from "@/lib/theme";
import { ServicesProvider } from "@/lib/services";
import { ConnectionsProvider } from "@/lib/connections";
import { AssistantHighlightProvider } from "@/lib/assistant-highlight";
import { SessionProvider } from "@/lib/session";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { PwaInstallBanner, PwaInstallHelpDialog, PwaInstallProvider } from "@/components/pwa-install";

export const Route = createFileRoute("/_app")({ component: AppLayout });

function AppLayout() {
  return (
    <SessionProvider>
      <ThemeProvider>
        <ServicesProvider>
          <ConnectionsProvider>
            <AssistantHighlightProvider>
              <TooltipProvider delayDuration={150}>
              <PwaInstallProvider>
              <SidebarProvider>
                <AppSidebar />
                <SidebarInset className="relative min-w-0 max-w-full flex-1 overflow-x-hidden bg-background">
                  <AppBackdrop />
                  <TopBar />
                  <main className="relative min-w-0 w-full max-w-full flex-1 px-3 py-4 sm:px-4 sm:py-6 md:px-8 md:py-8">
                    <Outlet />
                  </main>
                </SidebarInset>
                <LiveChatFab />
              </SidebarProvider>
              <PwaInstallBanner />
              <PwaInstallHelpDialog />
              <Toaster />
              </PwaInstallProvider>
            </TooltipProvider>
            </AssistantHighlightProvider>
          </ConnectionsProvider>
        </ServicesProvider>
      </ThemeProvider>
    </SessionProvider>
  );
}

function AppBackdrop() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
      {/* soft radial wash */}
      <div className="absolute -top-40 -right-40 h-[480px] w-[480px] rounded-full bg-primary/[0.06] blur-3xl" />
      <div className="absolute -bottom-52 -left-32 h-[520px] w-[520px] rounded-full bg-accent/40 blur-3xl" />
      {/* dotted grid */}
      <svg className="absolute inset-0 h-full w-full text-foreground/[0.05]" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="app-dots" x="0" y="0" width="28" height="28" patternUnits="userSpaceOnUse">
            <circle cx="1.5" cy="1.5" r="1.2" fill="currentColor" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#app-dots)" />
      </svg>
    </div>
  );
}
