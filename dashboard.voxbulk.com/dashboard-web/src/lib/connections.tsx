import * as React from "react";

type Ctx = {
  chatOpen: boolean;
  openChat: () => void;
  closeChat: () => void;
  toggleChat: () => void;
};

const ConnectionsCtx = React.createContext<Ctx>({
  chatOpen: false,
  openChat: () => {},
  closeChat: () => {},
  toggleChat: () => {},
});

export function ConnectionsProvider({ children }: { children: React.ReactNode }) {
  const [chatOpen, setChatOpen] = React.useState(false);
  return (
    <ConnectionsCtx.Provider
      value={{
        chatOpen,
        openChat: () => setChatOpen(true),
        closeChat: () => setChatOpen(false),
        toggleChat: () => setChatOpen((o) => !o),
      }}
    >
      {children}
    </ConnectionsCtx.Provider>
  );
}

export const useConnections = () => React.useContext(ConnectionsCtx);
