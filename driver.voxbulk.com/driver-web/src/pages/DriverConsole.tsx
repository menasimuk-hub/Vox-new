import { useState } from "react";
import { useDriverPortal } from "@/hooks/useDriverPortal";
import {
  Sun, Moon, Bike, Zap, Car, ClipboardList, History as HistoryIcon, Settings as SettingsIcon,
  MapPin, Phone, CheckCircle2, Truck, Package, BellRing, X, DollarSign, Activity, ShoppingBag,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { useLang, useTheme, useLocalState } from "@/lib/app-prefs";
import { OnlineSlider } from "@/components/OnlineSlider";
import { toast, Toaster } from "sonner";

type Vehicle = "bike" | "ebike" | "cycle" | "car";
type DStatus = "incoming" | "collected" | "onway" | "arrived" | "delivered" | "cancelled";
type DOrder = {
  id: string; number: string; status: DStatus;
  restaurantName: string; restaurantAddr: string;
  customerName: string; customerAddr: string;
  total: number; createdAt: number; deliveredAt?: number;
};
type DriverSettings = { name: string; mobile: string; vehicle: Vehicle };

const t = {
  en: {
    title: "Yallasay Driver", orders: "Orders", history: "History", settings: "Settings",
    cur: "Earnings", active: "Active", today: "Today",
    newOrder: "New Delivery Order!", order: "Order", restaurant: "Restaurant", restaurantAddr: "Restaurant Address",
    customer: "Customer", customerAddr: "Customer Address", total: "Total",
    readyToCollect: "Ready to Collect", cantCollect: "Can't Collect",
    collected: "Collected", onway: "On my way", arrived: "Arrived", delivered: "Delivered", notify: "Notify Customer",
    notified: "Customer notified", noActive: "No active deliveries",
    name: "Driver Name", mobile: "Mobile Number", vehicle: "Vehicle Type",
    bike: "Motor Bike", ebike: "Electrical Cycle", cycle: "Cycle", car: "Car",
    save: "Save", saved: "Saved", noHistory: "No deliveries yet",
    language: "Language",
  },
  ar: {
    title: "يلا ساي — السائق", orders: "الطلبات", history: "السجل", settings: "الإعدادات",
    cur: "الأرباح", active: "نشطة", today: "اليوم",
    newOrder: "طلب توصيل جديد!", order: "طلب", restaurant: "المطعم", restaurantAddr: "عنوان المطعم",
    customer: "العميل", customerAddr: "عنوان العميل", total: "الإجمالي",
    readyToCollect: "جاهز للاستلام", cantCollect: "لا يمكن الاستلام",
    collected: "تم الاستلام", onway: "في الطريق", arrived: "وصلت", delivered: "تم التسليم", notify: "إعلام العميل",
    notified: "تم إعلام العميل", noActive: "لا توجد توصيلات نشطة",
    name: "اسم السائق", mobile: "رقم الجوال", vehicle: "نوع المركبة",
    bike: "دراجة نارية", ebike: "دراجة كهربائية", cycle: "دراجة", car: "سيارة",
    save: "حفظ", saved: "تم الحفظ", noHistory: "لا توجد توصيلات بعد",
    language: "اللغة",
  },
};

const VEHICLES: { v: Vehicle; icon: string }[] = [
  { v: "bike", icon: "🏍️" }, { v: "ebike", icon: "⚡" }, { v: "cycle", icon: "🚲" }, { v: "car", icon: "🚗" },
];

function DriverPage() {
  const { lang, setLang } = useLang("driver");
  const { theme, toggle: toggleTheme } = useTheme("driver");
  const [online, setOnline] = useLocalState<boolean>("driver:online", true);
  const [tab, setTab] = useState<"orders" | "history" | "settings">("orders");
  const tx = t[lang]; const isAr = lang === "ar";

  const { orders, settings, setSettings, loading, incoming, acceptIncoming, rejectIncoming, advance } =
    useDriverPortal(lang);

  const active = orders.filter(o => o.status !== "delivered" && o.status !== "cancelled" && o.status !== "incoming");
  const today = orders.filter(o => Date.now() - o.createdAt < 86400000);
  const earnings = orders.filter(o => o.status === "delivered" && Date.now() - (o.deliveredAt ?? 0) < 86400000)
    .reduce((s, o) => s + o.total * 0.15, 0);

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center bg-background text-muted-foreground">
        {lang === "ar" ? "جاري التحميل…" : "Loading…"}
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background pb-24 text-foreground">
      <Toaster richColors position="top-center" />
      <header className="sticky top-0 z-30 border-b bg-background/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-md items-center justify-between gap-2 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Truck className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-sm font-bold">{tx.title}</h1>
              <p className="truncate text-xs text-muted-foreground">{settings.name}</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <OnlineSlider online={online} setOnline={setOnline} lang={lang} />
            <Button variant="ghost" size="icon" onClick={toggleTheme}>{theme === "light" ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}</Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-md px-4 py-4">
        {tab === "orders" && (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-2">
              <MiniKpi icon={<DollarSign className="h-5 w-5" />} label={tx.cur} value={`$${earnings.toFixed(0)}`} />
              <MiniKpi icon={<Activity className="h-5 w-5" />} label={tx.active} value={active.length.toString()} />
              <MiniKpi icon={<ShoppingBag className="h-5 w-5" />} label={tx.today} value={today.length.toString()} />
            </div>
            {active.length === 0 ? (
              <Card className="border-border/50"><CardContent className="py-10 text-center text-sm text-muted-foreground">{tx.noActive}</CardContent></Card>
            ) : (
              active.map(o => <DeliveryCard key={o.id} order={o} tx={tx} isAr={isAr} onAdvance={() => advance(o.id)} />)
            )}
          </div>
        )}

        {tab === "history" && (
          <HistoryView orders={orders.filter(o => o.status === "delivered")} tx={tx} isAr={isAr} />
        )}

        {tab === "settings" && (
          <SettingsView settings={settings} setSettings={setSettings} tx={tx} lang={lang} setLang={setLang} />
        )}
      </main>

      <nav className="fixed inset-x-0 bottom-0 z-30 border-t bg-background/95 backdrop-blur-xl">
        <div className="mx-auto grid max-w-md grid-cols-3">
          {[
            { k: "orders", icon: ClipboardList, label: tx.orders },
            { k: "history", icon: HistoryIcon, label: tx.history },
            { k: "settings", icon: SettingsIcon, label: tx.settings },
          ].map(({ k, icon: Icon, label }) => (
            <button key={k} onClick={() => setTab(k as typeof tab)}
              className={`flex flex-col items-center gap-1 py-3 text-xs transition ${tab === k ? "text-primary" : "text-muted-foreground"}`}>
              <Icon className={`h-6 w-6 ${tab === k ? "scale-110" : ""}`} />
              <span className="font-medium">{label}</span>
            </button>
          ))}
        </div>
      </nav>

      <Dialog open={!!incoming} onOpenChange={(o) => !o && rejectIncoming()}>
        <DialogContent className="max-w-sm overflow-hidden border-0 p-0">
          <div className="gradient-energy px-5 py-4 text-white">
            <div className="flex items-center gap-2 text-lg font-bold">
              <BellRing className="h-5 w-5 animate-pulse" />{tx.newOrder}
            </div>
          </div>
          {incoming && (
            <div className="space-y-3 p-5">
              <Row label={tx.order} value={incoming.number} />
              <Row label={tx.restaurant} value={incoming.restaurantName} />
              <Row label={tx.restaurantAddr} value={incoming.restaurantAddr} />
              <Row label={tx.customerAddr} value={incoming.customerAddr} />
              <div className="flex items-center justify-between border-t pt-3">
                <span className="text-sm text-muted-foreground">{tx.total}</span>
                <span className="text-xl font-black text-primary">${incoming.total.toFixed(2)}</span>
              </div>
              <div className="flex gap-2 pt-2">
                <Button variant="outline" className="flex-1" onClick={rejectIncoming}><X className="h-4 w-4 me-1" />{tx.cantCollect}</Button>
                <Button className="flex-1 gradient-energy text-white" onClick={acceptIncoming}><CheckCircle2 className="h-4 w-4 me-1" />{tx.readyToCollect}</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="text-xs uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="text-end text-sm font-semibold">{value}</span>
    </div>
  );
}

function MiniKpi({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <Card className="shadow-[var(--shadow-soft)] border-border/50">
      <CardContent className="p-3 text-center">
        <div className="mx-auto mb-1.5 flex h-8 w-8 items-center justify-center text-primary">{icon}</div>
        <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</div>
        <div className="text-base font-black mt-0.5">{value}</div>
      </CardContent>
    </Card>
  );
}

function DeliveryCard({ order, tx, isAr, onAdvance }: { order: DOrder; tx: typeof t.en; isAr: boolean; onAdvance: () => void }) {
  const statusLabel: Record<DStatus, string> = {
    incoming: "—", collected: tx.collected, onway: tx.onway, arrived: tx.arrived, delivered: tx.delivered, cancelled: "—",
  };
  const nextLabel: Record<DStatus, string> = {
    incoming: "", collected: tx.onway, onway: tx.arrived, arrived: tx.delivered, delivered: "", cancelled: "",
  };
  const tone: Record<DStatus, string> = {
    incoming: "", collected: "bg-warning text-warning-foreground", onway: "bg-chart-5 text-white",
    arrived: "bg-accent text-accent-foreground", delivered: "bg-success text-success-foreground", cancelled: "",
  };
  const mapUrl = (addr: string) => `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(addr)}`;

  return (
    <Card className="animate-slide-up overflow-hidden shadow-[var(--shadow-soft)]">
      <div className={`flex items-center justify-between px-4 py-2 text-sm font-semibold ${tone[order.status]}`}>
        <span>{tx.order} {order.number}</span>
        <Badge variant="secondary" className="bg-white/20 text-white">{statusLabel[order.status]}</Badge>
      </div>
      <CardContent className="space-y-3 p-4">
        <div>
          <div className="text-[10px] uppercase text-muted-foreground">{tx.restaurant}</div>
          <div className="font-semibold">{order.restaurantName}</div>
          <a href={mapUrl(order.restaurantAddr)} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-sm text-primary hover:underline">
            <MapPin className="h-4 w-4" />{order.restaurantAddr}
          </a>
        </div>
        <div>
          <div className="text-[10px] uppercase text-muted-foreground">{tx.customer}</div>
          <div className="font-semibold">{order.customerName}</div>
          <a href={mapUrl(order.customerAddr)} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-sm text-primary hover:underline">
            <MapPin className="h-4 w-4" />{order.customerAddr}
          </a>
        </div>
        <div className="flex items-center justify-between border-t pt-2">
          <span className="text-sm text-muted-foreground">{tx.total}</span>
          <span className="text-lg font-black">${order.total.toFixed(2)}</span>
        </div>
        {order.status === "arrived" && (
          <Button variant="outline" className="w-full border-accent text-accent" onClick={() => toast.success(tx.notified)}>
            <BellRing className="h-4 w-4 me-2" />{tx.notify}
          </Button>
        )}
        {order.status !== "delivered" && (
          <Button className="w-full gradient-energy text-white" onClick={onAdvance}>
            {order.status === "collected" && <Truck className="h-4 w-4 me-2" />}
            {order.status === "onway" && <MapPin className="h-4 w-4 me-2" />}
            {order.status === "arrived" && <Package className="h-4 w-4 me-2" />}
            {nextLabel[order.status]}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function HistoryView({ orders, tx, isAr }: { orders: DOrder[]; tx: typeof t.en; isAr: boolean }) {
  const [date, setDate] = useState("");
  const filtered = orders.filter(o => !date || new Date(o.deliveredAt ?? o.createdAt).toISOString().slice(0, 10) === date)
    .sort((a, b) => (b.deliveredAt ?? 0) - (a.deliveredAt ?? 0));
  return (
    <div className="space-y-3">
      <Input type="date" value={date} onChange={e => setDate(e.target.value)} />
      {filtered.length === 0 ? (
        <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">{tx.noHistory}</CardContent></Card>
      ) : filtered.map(o => (
        <Card key={o.id}>
          <CardContent className="flex items-center justify-between gap-3 p-3">
            <div className="min-w-0">
              <div className="text-sm font-semibold">{tx.order} {o.number}</div>
              <div className="truncate text-xs text-muted-foreground">{o.restaurantName} → {o.customerName}</div>
              <div className="text-[10px] text-muted-foreground">{new Date(o.deliveredAt ?? o.createdAt).toLocaleString(isAr ? "ar" : "en")}</div>
            </div>
            <div className="text-end">
              <Badge className="bg-success text-success-foreground">{tx.delivered}</Badge>
              <div className="mt-1 text-sm font-bold">${o.total.toFixed(2)}</div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function SettingsView({ settings, setSettings, tx, lang, setLang }: { settings: DriverSettings; setSettings: (f: (s: DriverSettings) => DriverSettings) => void; tx: typeof t.en; lang: "en" | "ar"; setLang: (l: "en" | "ar") => void }) {
  const [local, setLocal] = useState(settings);
  return (
    <Card className="border-border/50">
      <CardHeader><CardTitle>{tx.settings}</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        {/* Language Selection */}
        <div className="space-y-2">
          <Label className="text-sm font-semibold">{tx.language}</Label>
          <div className="grid grid-cols-2 gap-2">
            <Button
              type="button"
              variant={lang === "en" ? "default" : "outline"}
              className={lang === "en" ? "gradient-energy text-white font-bold" : "border-border"}
              onClick={() => setLang("en")}
            >
              English
            </Button>
            <Button
              type="button"
              variant={lang === "ar" ? "default" : "outline"}
              className={lang === "ar" ? "gradient-energy text-white font-bold" : "border-border"}
              onClick={() => setLang("ar")}
            >
              العربية
            </Button>
          </div>
        </div>

        <div className="h-px bg-border my-4" />

        <div><Label>{tx.name}</Label><Input value={local.name} onChange={e => setLocal({ ...local, name: e.target.value })} /></div>
        <div><Label>{tx.mobile}</Label><Input value={local.mobile} onChange={e => setLocal({ ...local, mobile: e.target.value })} /></div>
        <div>
          <Label>{tx.vehicle}</Label>
          <div className="mt-2 grid grid-cols-2 gap-2">
            {VEHICLES.map(({ v, icon }) => (
              <button key={v} onClick={() => setLocal({ ...local, vehicle: v })}
                className={`rounded-xl border-2 p-3 text-center transition ${local.vehicle === v ? "border-primary bg-primary/10" : "border-border"}`}>
                <div className="text-3xl">{icon}</div>
                <div className="mt-1 text-xs font-medium">{tx[v]}</div>
              </button>
            ))}
          </div>
        </div>
        <Button className="w-full gradient-energy text-white" onClick={() => { setSettings(() => local); toast.success(tx.saved); }}>{tx.save}</Button>
      </CardContent>
    </Card>
  );
}

export default DriverPage;
