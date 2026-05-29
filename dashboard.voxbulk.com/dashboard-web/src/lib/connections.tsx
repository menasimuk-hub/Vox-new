import * as React from "react";

export type BookingSystemKey = "dentally" | "phorest" | "calendly" | "cronofy" | "zoom" | "standalone";

export const bookingSystems: { key: BookingSystemKey; name: string; description: string; fields: { label: string; placeholder: string; type?: string }[] }[] = [
  { key: "dentally", name: "Dentally", description: "UK dental practice management.", fields: [
    { label: "API key", placeholder: "sk_live_••••", type: "password" },
    { label: "Practice ID", placeholder: "NW-LONDON-001" },
  ]},
  { key: "phorest", name: "Phorest", description: "Salon & clinic booking platform.", fields: [
    { label: "Business ID", placeholder: "phorest_biz_…" },
    { label: "Access token", placeholder: "phr_••••", type: "password" },
    { label: "Branch ID", placeholder: "branch_001" },
  ]},
  { key: "calendly", name: "Calendly", description: "Scheduling links & invitee data.", fields: [
    { label: "Personal access token", placeholder: "eyJraWQiO…", type: "password" },
    { label: "Organization URI", placeholder: "https://api.calendly.com/organizations/…" },
  ]},
  { key: "cronofy", name: "Cronofy", description: "Unified calendar API (Google, Outlook, iCloud).", fields: [
    { label: "Client ID", placeholder: "cronofy_client_id" },
    { label: "Client secret", placeholder: "cronofy_secret", type: "password" },
    { label: "Sub (account ID)", placeholder: "acc_5700a00eb0ccd07000000000" },
    { label: "Data center", placeholder: "eu / us" },
  ]},
  { key: "zoom", name: "Zoom", description: "Video appointments & meeting links.", fields: [
    { label: "Account ID", placeholder: "abc123XYZ" },
    { label: "Client ID", placeholder: "zoom_client_id" },
    { label: "Client secret", placeholder: "zoom_secret", type: "password" },
  ]},
  { key: "standalone", name: "Standalone", description: "Use VoxBulk without a booking system.", fields: [
    { label: "Display name", placeholder: "Northwell Dental" },
    { label: "Default time zone", placeholder: "Europe/London" },
  ]},
];

type Ctx = {
  bookingSystem: BookingSystemKey;
  setBookingSystem: (k: BookingSystemKey) => void;
  chatOpen: boolean;
  openChat: () => void;
  closeChat: () => void;
  toggleChat: () => void;
};

const ConnectionsCtx = React.createContext<Ctx>({
  bookingSystem: "dentally",
  setBookingSystem: () => {},
  chatOpen: false,
  openChat: () => {},
  closeChat: () => {},
  toggleChat: () => {},
});

export function ConnectionsProvider({ children }: { children: React.ReactNode }) {
  const [bookingSystem, setBookingSystem] = React.useState<BookingSystemKey>("dentally");
  const [chatOpen, setChatOpen] = React.useState(false);
  return (
    <ConnectionsCtx.Provider value={{
      bookingSystem, setBookingSystem,
      chatOpen,
      openChat: () => setChatOpen(true),
      closeChat: () => setChatOpen(false),
      toggleChat: () => setChatOpen((o) => !o),
    }}>{children}</ConnectionsCtx.Provider>
  );
}

export const useConnections = () => React.useContext(ConnectionsCtx);

export function bookingSystemName(k: BookingSystemKey) {
  return bookingSystems.find((s) => s.key === k)?.name ?? "Standalone";
}
