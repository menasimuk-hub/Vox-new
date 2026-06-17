import { useMemo, useState } from "react";
import { apiFetch, logoutRestaurant } from "@/lib/api";
import { useRestaurantPortal } from "@/hooks/useRestaurantPortal";
import {
  Sun, Moon, ClipboardList, BookOpen, History as HistoryIcon, Settings as SettingsIcon,
  Play, CheckCircle2, PackageCheck, RotateCcw, AlertOctagon, Plus, Trash2, Pencil, X,
  DollarSign, ShoppingBag, Activity, Search, Sparkles, Tag, Check, Minus, LogOut,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useLang, useTheme, useLocalState, uid } from "@/lib/app-prefs";
import { OnlineSlider } from "@/components/OnlineSlider";
import { toast, Toaster } from "sonner";

type Status = "new" | "preparing" | "ready" | "collected" | "with_driver";
type OrderItem = { id: string; nameEn: string; nameAr: string; qty: number; price: number; outOfStock?: boolean; substitutionStatus?: string | null };
type Order = {
  id: string;
  number: string;
  status: Status;
  items: OrderItem[];
  createdAt: number;
  collectedAt?: number;
  outOfStockCount: number;
  substitutionPending?: boolean;
  customerPhone?: string;
  customerName?: string;
  deliveryAddress?: string;
  notes?: string;
  allergyNote?: string;
};
type MenuItem = {
  id: string;
  nameEn: string; nameAr: string;
  price: number; icon: string;
  descEn: string; descAr: string;
  recipeEn: string; recipeAr: string;
  allergy: string; diet: string;
  itemType: string;
  hidden: boolean;
};
type Category = { id: string; nameEn: string; nameAr: string; items: MenuItem[] };
type DayHours = { open: boolean; from: string; to: string };
type WeekHours = Record<string, DayHours>;
type RestaurantSettings = { name: string; mobile: string; address: string; hours: WeekHours };

type OfferItem = {
  itemId: string;
  qty: number;
};

type Offer = {
  id: string;
  titleEn: string;
  titleAr: string;
  items: OfferItem[];
  originalPrice: number;
  offerPrice: number;
  discountPercentage: number;
  createdAt: number;
};

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

const DEFAULT_HOURS: WeekHours = Object.fromEntries(
  DAYS.map(d => [d, { open: true, from: "10:00", to: "23:00" }])
) as WeekHours;

const t = {
  en: {
    title: "Yallasay Restaurant", orders: "Orders", menu: "Menu", history: "History", settings: "Settings",
    todayOrders: "Today's Orders", active: "Active", sales: "Sales",
    activeOrders: "Active Orders", noActive: "No active orders right now",
    order: "Order", items: "Items", start: "Start", ready: "Ready", collected: "Collected", back: "Back",
    outOfStock: "Out of stock", removed: "Removed", customerNotified: "Customer will be notified",
    historyDesc: "All past orders", filter: "Filter", search: "Search…", date: "Date",
    editMenu: "Edit Menu", addCategory: "Add Category", addItem: "Add Item",
    name: "Name", nameEn: "Name (English)", nameAr: "Name (Arabic)", price: "Price",
    icon: "Icon (emoji)", description: "Description", recipe: "Recipe / ingredients", allergy: "Allergens", diet: "Dietary tags",
    hide: "Hide from menu", save: "Save", cancel: "Cancel", edit: "Edit", delete: "Delete",
    restaurantName: "Restaurant Name", mobile: "Mobile Number", address: "Address", hours: "Working Time",
    saved: "Saved", open: "Open", closed: "Closed", from: "From", to: "To",
    days: { mon: "Monday", tue: "Tuesday", wed: "Wednesday", thu: "Thursday", fri: "Friday", sat: "Saturday", sun: "Sunday" },
    new: "New", preparing: "Preparing", readyS: "Ready", collectedS: "Collected",
    total: "Total",
    offers: "Offers",
    addOffer: "Add Offer",
    activeOffers: "Active Offers",
    offerTitleEn: "Offer Title (English)",
    offerTitleAr: "Offer Title (Arabic)",
    selectItems: "Select Menu Items",
    originalPrice: "Original Price",
    offerPrice: "Offer Price",
    discountPercent: "Discount Percentage",
    createOffer: "Create Offer",
    noOffers: "No active offers yet",
    offerCreated: "Offer created successfully!",
    offerDeleted: "Offer deleted successfully!",
    language: "Language",
    logout: "Logout",
    allergyNote: "Customer allergy note",
  },
  ar: {
    title: "يلا ساي — المطعم", orders: "الطلبات", menu: "القائمة", history: "السجل", settings: "الإعدادات",
    todayOrders: "طلبات اليوم", active: "نشطة", sales: "المبيعات",
    activeOrders: "الطلبات النشطة", noActive: "لا توجد طلبات نشطة الآن",
    order: "طلب", items: "العناصر", start: "ابدأ", ready: "جاهز", collected: "تم الاستلام", back: "رجوع",
    outOfStock: "غير متوفر", removed: "تمت إزالته", customerNotified: "سيتم إعلام العميل",
    historyDesc: "جميع الطلبات السابقة", filter: "تصفية", search: "بحث…", date: "التاريخ",
    editMenu: "تعديل القائمة", addCategory: "إضافة قسم", addItem: "إضافة صنف",
    name: "الاسم", nameEn: "الاسم (إنجليزي)", nameAr: "الاسم (عربي)", price: "السعر",
    icon: "أيقونة", description: "الوصف", recipe: "الوصفة / المكونات", allergy: "مسببات الحساسية", diet: "النظام الغذائي",
    hide: "إخفاء من القائمة", save: "حفظ", cancel: "إلغاء", edit: "تعديل", delete: "حذف",
    restaurantName: "اسم المطعم", mobile: "رقم الجوال", address: "العنوان", hours: "ساعات العمل",
    saved: "تم الحفظ", open: "مفتوح", closed: "مغلق", from: "من", to: "إلى",
    days: { mon: "الإثنين", tue: "الثلاثاء", wed: "الأربعاء", thu: "الخميس", fri: "الجمعة", sat: "السبت", sun: "الأحد" },
    new: "جديد", preparing: "قيد التحضير", readyS: "جاهز", collectedS: "تم الاستلام",
    total: "الإجمالي",
    offers: "العروض",
    addOffer: "إضافة عرض",
    activeOffers: "العروض النشطة",
    offerTitleEn: "عنوان العرض (إنجليزي)",
    offerTitleAr: "عنوان العرض (عربي)",
    selectItems: "اختر الأصناف من القائمة",
    originalPrice: "السعر الأصلي",
    offerPrice: "سعر العرض",
    discountPercent: "نسبة الخصم",
    createOffer: "إنشاء العرض",
    noOffers: "لا توجد عروض نشطة بعد",
    offerCreated: "تم إنشاء العرض بنجاح!",
    offerDeleted: "تم حذف العرض بنجاح!",
    language: "اللغة",
    logout: "تسجيل الخروج",
    allergyNote: "ملاحظة حساسية العميل",
  },
};

const STATUS_FLOW: Status[] = ["new", "preparing", "ready", "collected"];
const STATUS_COLORS: Record<Status, string> = {
  new: "bg-chart-5 text-white",
  preparing: "bg-warning text-warning-foreground",
  ready: "bg-success text-success-foreground",
  collected: "bg-muted text-muted-foreground",
  with_driver: "bg-accent text-accent-foreground",
};

function RestaurantPage() {
  const { lang, setLang } = useLang("restaurant");
  const { theme, toggle: toggleTheme } = useTheme("restaurant");
  const [online, setOnline] = useLocalState<boolean>("restaurant:online", true);
  const tx = t[lang];
  const isAr = lang === "ar";

  const { orders, cats, setCats, offers, setOffers, settings, setSettings, loading, refresh, changeStatus, markOOS, formatMoney } =
    useRestaurantPortal(lang);

  const active = orders.filter(o => o.status !== "collected" && o.status !== "with_driver");
  const todaysOrders = orders.filter(o => Date.now() - o.createdAt < 86400000);
  const sales = todaysOrders.reduce((s, o) => s + o.items.filter(i => !i.outOfStock).reduce((a, i) => a + i.price * i.qty, 0), 0);

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center bg-background text-muted-foreground">
        {lang === "ar" ? "جاري التحميل…" : "Loading…"}
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Toaster richColors position={isAr ? "top-left" : "top-right"} />
      <header className="sticky top-0 z-30 border-b bg-background/85 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl gradient-energy text-white shadow-[var(--shadow-glow)]">
              <ShoppingBag className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-base font-bold sm:text-lg">{tx.title}</h1>
              <p className="truncate text-xs text-muted-foreground">{settings.name}</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <OnlineSlider online={online} setOnline={setOnline} lang={lang} />
            <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="theme">
              {theme === "light" ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
            </Button>
            <Button variant="ghost" size="icon" onClick={() => logoutRestaurant()} aria-label={tx.logout} title={tx.logout}>
              <LogOut className="h-5 w-5" />
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        <Tabs defaultValue="orders" className="w-full">
          <TabsList className="grid w-full grid-cols-5 gap-1">
            <TabsTrigger value="orders" className="gap-2"><ClipboardList className="h-4 w-4" />{tx.orders}</TabsTrigger>
            <TabsTrigger value="menu" className="gap-2"><BookOpen className="h-4 w-4" />{tx.menu}</TabsTrigger>
            <TabsTrigger value="offers" className="gap-2"><Tag className="h-4 w-4" />{tx.offers}</TabsTrigger>
            <TabsTrigger value="history" className="gap-2"><HistoryIcon className="h-4 w-4" />{tx.history}</TabsTrigger>
            <TabsTrigger value="settings" className="gap-2"><SettingsIcon className="h-4 w-4" />{tx.settings}</TabsTrigger>
          </TabsList>

          <TabsContent value="orders" className="mt-6 space-y-6">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <KpiCard icon={<ShoppingBag />} label={tx.todayOrders} value={todaysOrders.length.toString()} tone="primary" />
              <KpiCard icon={<Activity />} label={tx.active} value={active.length.toString()} tone="accent" />
              <KpiCard icon={<DollarSign />} label={tx.sales} value={formatMoney(sales)} tone="success" />
            </div>

            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold">{tx.activeOrders}</h2>
            </div>

            {active.length === 0 ? (
              <Card><CardContent className="py-12 text-center text-muted-foreground">{tx.noActive}</CardContent></Card>
            ) : (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                {active.map(o => (
                  <OrderCard key={o.id} order={o} tx={tx} isAr={isAr} formatMoney={formatMoney}
                    onForward={() => changeStatus(o.id, 1)}
                    onBack={() => changeStatus(o.id, -1)}
                    onOOS={(iid) => markOOS(o.id, iid)} />
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value="menu" className="mt-6">
            <MenuPanel cats={cats} setCats={setCats} tx={tx} isAr={isAr} onRefresh={refresh} />
          </TabsContent>

          <TabsContent value="offers" className="mt-6">
            <OffersPanel cats={cats} offers={offers} setOffers={setOffers} tx={tx} isAr={isAr} onRefresh={refresh} />
          </TabsContent>

          <TabsContent value="history" className="mt-6">
            <HistoryPanel orders={orders.filter(o => o.status === "collected")} tx={tx} isAr={isAr} />
          </TabsContent>

          <TabsContent value="settings" className="mt-6">
            <SettingsPanel settings={settings} setSettings={setSettings} tx={tx} lang={lang} setLang={setLang} />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}

function KpiCard({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: string; tone: "primary" | "accent" | "success" }) {
  const grad = tone === "primary" ? "gradient-energy" : tone === "accent" ? "bg-accent" : "bg-success";
  return (
    <Card className="overflow-hidden shadow-[var(--shadow-soft)] border-border/50">
      <CardContent className="flex items-center gap-4 p-5">
        <div className={`grid h-12 w-12 shrink-0 place-items-center rounded-xl text-white ${grad}`}>{icon}</div>
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
          <div className="truncate text-2xl font-black">{value}</div>
        </div>
      </CardContent>
    </Card>
  );
}

function OrderCard({ order, tx, isAr, onForward, onBack, onOOS, formatMoney }: {
  order: Order; tx: typeof t.en; isAr: boolean;
  onForward: () => void; onBack: () => void; onOOS: (id: string) => void;
  formatMoney: (n: number) => string;
}) {
  const label: Record<Status, string> = { new: tx.new, preparing: tx.preparing, ready: tx.readyS, collected: tx.collectedS, with_driver: tx.collectedS };
  const total = order.items.filter(i => !i.outOfStock).reduce((s, i) => s + i.price * i.qty, 0);
  const idx = STATUS_FLOW.indexOf(order.status === "with_driver" ? "ready" : order.status);
  const nextLabel = idx === 0 ? tx.start : idx === 1 ? tx.ready : tx.collected;
  const canForward = !order.substitutionPending && order.status !== "with_driver";
  return (
    <Card className="animate-slide-up overflow-hidden shadow-[var(--shadow-soft)]">
      <div className={`px-4 py-2 text-sm font-semibold ${STATUS_COLORS[order.status] || STATUS_COLORS.new}`}>
        {tx.order} {order.number} · {label[order.status] || order.status}
        {order.substitutionPending && (
          <span className="ms-2 rounded-full bg-black/20 px-2 py-0.5 text-xs">{isAr ? "بانتظار العميل" : "Awaiting customer"}</span>
        )}
        {order.outOfStockCount > 0 && (
          <span className="ms-2 rounded-full bg-black/20 px-2 py-0.5 text-xs">⚠ {order.outOfStockCount}</span>
        )}
      </div>
      <CardContent className="space-y-3 p-4">
        {(order.customerName || order.deliveryAddress) && (
          <div className="rounded-lg border bg-muted/30 p-2 text-xs">
            {order.customerName ? <div className="font-semibold">{order.customerName} {order.customerPhone ? `· ${order.customerPhone}` : ""}</div> : null}
            {order.deliveryAddress ? <div className="text-muted-foreground">{order.deliveryAddress}</div> : null}
          </div>
        )}
        {order.allergyNote ? (
          <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-2 text-xs font-medium text-destructive">
            ⚠ {order.allergyNote}
          </div>
        ) : null}
        <ul className="space-y-2">
          {order.items.map(it => (
            <li key={it.id} className={`flex items-center justify-between gap-2 rounded-lg border p-2 ${it.outOfStock ? "opacity-40 line-through" : ""}`}>
              <div className="min-w-0">
                <div className="truncate font-medium">{it.qty}× {isAr ? it.nameAr : it.nameEn}</div>
                <div className="text-xs text-muted-foreground">{formatMoney(it.price * it.qty)}</div>
                {it.outOfStock && it.substitutionStatus === "pending_customer" && (
                  <div className="text-xs text-destructive">{isAr ? "بانتظار بديل" : "Awaiting replacement"}</div>
                )}
              </div>
              {!it.outOfStock && order.status !== "with_driver" && (
                <Button size="sm" variant="ghost" className="shrink-0 text-destructive hover:bg-destructive/10" onClick={() => onOOS(it.id)} title={tx.outOfStock}>
                  <AlertOctagon className="h-4 w-4" />
                </Button>
              )}
            </li>
          ))}
        </ul>
        <div className="flex items-center justify-between border-t pt-3">
          <span className="text-sm text-muted-foreground">{tx.total}</span>
          <span className="text-lg font-black">{formatMoney(total)}</span>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="icon" onClick={onBack} disabled={idx === 0} title={tx.back}>
            <RotateCcw className="h-4 w-4" />
          </Button>
          <Button className="flex-1 gradient-energy text-white hover:opacity-90" onClick={onForward} disabled={!canForward}>
            {idx === 0 ? <Play className="h-4 w-4 me-2" /> : idx === 1 ? <CheckCircle2 className="h-4 w-4 me-2" /> : <PackageCheck className="h-4 w-4 me-2" />}
            {nextLabel}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function HistoryPanel({ orders, tx, isAr }: { orders: Order[]; tx: typeof t.en; isAr: boolean }) {
  const [q, setQ] = useState("");
  const [date, setDate] = useState("");
  const filtered = useMemo(() => {
    return orders
      .filter(o => !q || o.number.includes(q))
      .filter(o => !date || new Date(o.collectedAt ?? o.createdAt).toISOString().slice(0, 10) === date)
      .sort((a, b) => (b.collectedAt ?? 0) - (a.collectedAt ?? 0));
  }, [orders, q, date]);
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <Search className="absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input className="ps-9" placeholder={tx.search} value={q} onChange={e => setQ(e.target.value)} />
        </div>
        <Input type="date" value={date} onChange={e => setDate(e.target.value)} className="sm:w-48" />
      </div>
      {filtered.length === 0 ? (
        <Card><CardContent className="py-12 text-center text-muted-foreground">{tx.historyDesc}</CardContent></Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {filtered.map(o => {
            const total = o.items.filter(i => !i.outOfStock).reduce((s, i) => s + i.price * i.qty, 0);
            return (
              <Card key={o.id}>
                <CardContent className="flex items-center justify-between gap-3 p-4">
                  <div className="min-w-0">
                    <div className="font-semibold">{tx.order} {o.number}</div>
                    <div className="text-xs text-muted-foreground">
                      {new Date(o.collectedAt ?? o.createdAt).toLocaleString(isAr ? "ar" : "en")}
                    </div>
                    <div className="mt-1 truncate text-xs text-muted-foreground">
                      {o.items.map(i => (isAr ? i.nameAr : i.nameEn)).join(" · ")}
                    </div>
                  </div>
                  <div className="text-end">
                    <Badge variant="secondary">{tx.collectedS}</Badge>
                    <div className="mt-1 font-bold">${total.toFixed(2)}</div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

function MenuPanel({ cats, setCats, tx, isAr, onRefresh }: { cats: Category[]; setCats: (f: (c: Category[]) => Category[]) => void; tx: typeof t.en; isAr: boolean; onRefresh: () => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [newCat, setNewCat] = useState({ en: "", ar: "" });
  const [itemDialog, setItemDialog] = useState<{ catId: string; item?: MenuItem } | null>(null);

  async function addCategory() {
    if (!newCat.en) return;
    try {
      await apiFetch("/abuu/restaurant/menu/categories", {
        method: "POST",
        body: JSON.stringify({ name_en: newCat.en, name_ar: newCat.ar || newCat.en }),
      });
      setNewCat({ en: "", ar: "" });
      await onRefresh();
    } catch (e: any) {
      toast.error(e?.message || "Save failed");
    }
  }
  async function delCat(id: string) {
    try {
      await apiFetch(`/abuu/restaurant/menu/categories/${id}`, { method: "DELETE" });
      await onRefresh();
    } catch (e: any) {
      toast.error(e?.message || "Delete failed");
    }
  }
  async function saveItem(catId: string, item: MenuItem) {
    try {
      const tagsFromCsv = (s: string) => {
        if (!s || s === "—") return null;
        const tags = s.split(",").map(t => t.trim()).filter(Boolean);
        return tags.length ? tags : null;
      };
      const payload: Record<string, unknown> = {
        name_en: item.nameEn,
        name_ar: item.nameAr,
        item_type: item.itemType || "meal",
        price_agorot: Math.round(item.price * 100),
        description_en: item.descEn,
        description_ar: item.descAr,
        is_available: !item.hidden,
      };
      const allergens = tagsFromCsv(item.allergy);
      const dietary = tagsFromCsv(item.diet);
      if (allergens) payload.allergen_tags_json = allergens;
      if (dietary) payload.dietary_tags_json = dietary;
      if (item.recipeEn || item.recipeAr) {
        payload.ingredients_json = {
          ingredients_en: item.recipeEn || item.recipeAr,
          ingredients_ar: item.recipeAr || item.recipeEn,
        };
      }
      const exists = cats.some(c => c.items.some(i => i.id === item.id));
      if (exists) {
        await apiFetch(`/abuu/restaurant/menu/items/${item.id}`, { method: "PATCH", body: JSON.stringify(payload) });
      } else {
        await apiFetch(`/abuu/restaurant/menu/categories/${catId}/items`, { method: "POST", body: JSON.stringify(payload) });
      }
      setItemDialog(null);
      await onRefresh();
    } catch (e: any) {
      toast.error(e?.message || "Save failed");
    }
  }
  async function delItem(_catId: string, id: string) {
    try {
      await apiFetch(`/abuu/restaurant/menu/items/${id}`, { method: "DELETE" });
      await onRefresh();
    } catch (e: any) {
      toast.error(e?.message || "Delete failed");
    }
  }
  async function toggleHide(_catId: string, id: string, hidden: boolean) {
    try {
      await apiFetch(`/abuu/restaurant/menu/items/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_available: !hidden }),
      });
      await onRefresh();
    } catch (e: any) {
      toast.error(e?.message || "Update failed");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-bold">{tx.menu}</h2>
        <Button onClick={() => setEditing(e => !e)} variant={editing ? "secondary" : "default"} className={editing ? "" : "gradient-energy text-white"}>
          <Pencil className="h-4 w-4 me-2" />{tx.editMenu}
        </Button>
      </div>

      {editing && (
        <Card>
          <CardContent className="flex flex-col gap-2 p-4 sm:flex-row">
            <Input placeholder={tx.nameEn} value={newCat.en} onChange={e => setNewCat(s => ({ ...s, en: e.target.value }))} />
            <Input placeholder={tx.nameAr} value={newCat.ar} onChange={e => setNewCat(s => ({ ...s, ar: e.target.value }))} dir="rtl" />
            <Button onClick={addCategory}><Plus className="h-4 w-4 me-1" />{tx.addCategory}</Button>
          </CardContent>
        </Card>
      )}

      <div className="space-y-6">
        {cats.map(cat => (
          <div key={cat.id}>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-xl font-bold text-gradient-sunset">{isAr ? cat.nameAr : cat.nameEn}</h3>
              {editing && (
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => setItemDialog({ catId: cat.id })}>
                    <Plus className="h-4 w-4 me-1" />{tx.addItem}
                  </Button>
                  <Button size="sm" variant="ghost" className="text-destructive" onClick={() => delCat(cat.id)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {cat.items.map(it => (
                <Card key={it.id} className={`shadow-[var(--shadow-soft)] ${it.hidden ? "opacity-50" : ""}`}>
                  <CardContent className="p-4">
                    <div className="flex items-start gap-3">
                      <div className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-muted text-2xl">{it.icon}</div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <h4 className="truncate font-bold">{isAr ? it.nameAr : it.nameEn}</h4>
                          <span className="shrink-0 font-bold text-primary">${it.price.toFixed(2)}</span>
                        </div>
                        <p className="line-clamp-2 text-sm text-muted-foreground">{isAr ? it.descAr : it.descEn}</p>
                        {(isAr ? it.recipeAr : it.recipeEn) ? (
                          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                            <span className="font-medium">{tx.recipe}: </span>
                            {isAr ? it.recipeAr : it.recipeEn}
                          </p>
                        ) : null}
                        <div className="mt-2 flex flex-wrap gap-1">
                          {it.allergy && it.allergy !== "—" && <Badge variant="destructive" className="text-xs">⚠ {it.allergy}</Badge>}
                          {it.diet && it.diet !== "—" && <Badge variant="secondary" className="text-xs">🥗 {it.diet}</Badge>}
                          {it.hidden && <Badge className="text-xs">Hidden</Badge>}
                        </div>
                      </div>
                    </div>
                    <div className="mt-3 flex items-center justify-between gap-2 border-t pt-3">
                      <label className="flex items-center gap-2 text-xs">
                        <Switch checked={it.hidden} onCheckedChange={() => toggleHide(cat.id, it.id, !it.hidden)} />
                        {tx.outOfStock}
                      </label>
                      {editing && (
                        <div className="flex gap-1">
                          <Button size="icon" variant="ghost" onClick={() => setItemDialog({ catId: cat.id, item: it })}><Pencil className="h-4 w-4" /></Button>
                          <Button size="icon" variant="ghost" className="text-destructive" onClick={() => delItem(cat.id, it.id)}><Trash2 className="h-4 w-4" /></Button>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        ))}
      </div>

      {itemDialog && (
        <ItemDialog
          tx={tx}
          catId={itemDialog.catId}
          initial={itemDialog.item}
          onClose={() => setItemDialog(null)}
          onSave={(it) => saveItem(itemDialog.catId, it)}
        />
      )}
    </div>
  );
}

function ItemDialog({ tx, initial, onClose, onSave }: { tx: typeof t.en; catId: string; initial?: MenuItem; onClose: () => void; onSave: (i: MenuItem) => void }) {
  const [it, setIt] = useState<MenuItem>(initial ?? {
    id: uid(), nameEn: "", nameAr: "", price: 0, icon: "🍽️",
    descEn: "", descAr: "", recipeEn: "", recipeAr: "", allergy: "", diet: "", itemType: "meal", hidden: false,
  });
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>{initial ? tx.edit : tx.addItem}</DialogTitle></DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2 sm:col-span-1"><Label>{tx.nameEn}</Label><Input value={it.nameEn} onChange={e => setIt({ ...it, nameEn: e.target.value })} /></div>
          <div className="col-span-2 sm:col-span-1"><Label>{tx.nameAr}</Label><Input dir="rtl" value={it.nameAr} onChange={e => setIt({ ...it, nameAr: e.target.value })} /></div>
          <div><Label>{tx.price}</Label><Input type="number" step="0.01" value={it.price} onChange={e => setIt({ ...it, price: parseFloat(e.target.value) || 0 })} /></div>
          <div><Label>{tx.icon}</Label><Input value={it.icon} onChange={e => setIt({ ...it, icon: e.target.value })} /></div>
          <div className="col-span-2"><Label>{tx.description} (EN)</Label><Textarea rows={2} value={it.descEn} onChange={e => setIt({ ...it, descEn: e.target.value })} /></div>
          <div className="col-span-2"><Label>{tx.description} (AR)</Label><Textarea rows={2} dir="rtl" value={it.descAr} onChange={e => setIt({ ...it, descAr: e.target.value })} /></div>
          <div className="col-span-2"><Label>{tx.recipe} (EN)</Label><Textarea rows={2} value={it.recipeEn} onChange={e => setIt({ ...it, recipeEn: e.target.value })} placeholder="Chicken, garlic, lemon, spices…" /></div>
          <div className="col-span-2"><Label>{tx.recipe} (AR)</Label><Textarea rows={2} dir="rtl" value={it.recipeAr} onChange={e => setIt({ ...it, recipeAr: e.target.value })} /></div>
          <div><Label>{tx.allergy}</Label><Input placeholder="dairy, nuts, gluten" value={it.allergy} onChange={e => setIt({ ...it, allergy: e.target.value })} /></div>
          <div><Label>{tx.diet}</Label><Input placeholder="vegetarian, vegan, spicy" value={it.diet} onChange={e => setIt({ ...it, diet: e.target.value })} /></div>
          <div className="col-span-2"><Label>Item type</Label><Input placeholder="meal, drink, dessert" value={it.itemType} onChange={e => setIt({ ...it, itemType: e.target.value })} /></div>
          <label className="col-span-2 flex items-center gap-2"><Switch checked={it.hidden} onCheckedChange={v => setIt({ ...it, hidden: v })} />{tx.hide}</label>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>{tx.cancel}</Button>
          <Button className="gradient-energy text-white" onClick={() => onSave(it)}>{tx.save}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function OffersPanel({ cats, offers, setOffers, tx, isAr, onRefresh }: { cats: Category[]; offers: Offer[]; setOffers: (f: (o: Offer[]) => Offer[]) => void; tx: typeof t.en; isAr: boolean; onRefresh: () => Promise<void> }) {
  const [titleEn, setTitleEn] = useState("");
  const [titleAr, setTitleAr] = useState("");
  const [selectedItems, setSelectedItems] = useState<Record<string, number>>({});
  const [customOriginalPrice, setCustomOriginalPrice] = useState("");
  const [offerPriceInput, setOfferPriceInput] = useState("");

  const allMenuItems = useMemo(() => {
    return cats.flatMap(c => c.items);
  }, [cats]);

  const originalTotal = useMemo(() => {
    return Object.entries(selectedItems).reduce((sum, [id, qty]) => {
      if (qty <= 0) return sum;
      const item = allMenuItems.find(it => it.id === id);
      return sum + (item ? item.price * qty : 0);
    }, 0);
  }, [selectedItems, allMenuItems]);

  const displayOriginalPrice = customOriginalPrice !== "" ? parseFloat(customOriginalPrice) || 0 : originalTotal;
  const displayOfferPrice = parseFloat(offerPriceInput) || 0;

  const discountPercentage = useMemo(() => {
    if (displayOriginalPrice <= 0 || displayOfferPrice >= displayOriginalPrice) return 0;
    return Math.round(((displayOriginalPrice - displayOfferPrice) / displayOriginalPrice) * 100);
  }, [displayOriginalPrice, displayOfferPrice]);

  const selectedCount = useMemo(() => {
    return Object.values(selectedItems).filter(qty => qty > 0).length;
  }, [selectedItems]);

  async function handleCreateOffer(e: React.FormEvent) {
    e.preventDefault();
    if (!titleEn.trim() || selectedCount === 0 || displayOfferPrice <= 0) return;

    const offerItems: OfferItem[] = Object.entries(selectedItems)
      .filter(([_, qty]) => qty > 0)
      .map(([id, qty]) => ({ itemId: id, qty }));

    try {
      await apiFetch("/abuu/restaurant/offers", {
        method: "POST",
        body: JSON.stringify({
          title_en: titleEn,
          title_ar: titleAr.trim() || titleEn,
          original_price_agorot: Math.round(displayOriginalPrice * 100),
          offer_price_agorot: Math.round(displayOfferPrice * 100),
          items: offerItems.map((oi) => ({ menu_item_id: oi.itemId, quantity: oi.qty })),
        }),
      });
      toast.success(tx.offerCreated);
      setTitleEn("");
      setTitleAr("");
      setSelectedItems({});
      setCustomOriginalPrice("");
      setOfferPriceInput("");
      await onRefresh();
    } catch (err: any) {
      toast.error(err?.message || "Create failed");
    }
  }

  async function handleDeleteOffer(id: string) {
    try {
      await apiFetch(`/abuu/restaurant/offers/${id}`, { method: "DELETE" });
      toast.success(tx.offerDeleted);
      await onRefresh();
    } catch (err: any) {
      toast.error(err?.message || "Delete failed");
    }
  }

  const getItemNames = (offerItems?: OfferItem[], legacyItemIds?: string[]) => {
    if (offerItems && Array.isArray(offerItems) && offerItems.length > 0) {
      return offerItems
        .map(oi => {
          const item = allMenuItems.find(it => it.id === oi.itemId);
          return item ? `${oi.qty}x ${isAr ? item.nameAr : item.nameEn}` : null;
        })
        .filter(Boolean)
        .join(" + ");
    }
    if (legacyItemIds && Array.isArray(legacyItemIds) && legacyItemIds.length > 0) {
      return legacyItemIds
        .map(id => {
          const item = allMenuItems.find(it => it.id === id);
          return item ? `1x ${isAr ? item.nameAr : item.nameEn}` : null;
        })
        .filter(Boolean)
        .join(" + ");
    }
    return "";
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
      {/* Add Offer Form */}
      <div className="lg:col-span-5">
        <Card className="shadow-[var(--shadow-soft)] border-border/50">
          <CardHeader>
            <CardTitle className="text-lg font-bold flex items-center gap-2">
              <Plus className="h-5 w-5 text-primary" />
              {tx.addOffer}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleCreateOffer} className="space-y-4">
              <div>
                <Label>{tx.offerTitleEn}</Label>
                <Input required value={titleEn} onChange={e => setTitleEn(e.target.value)} placeholder="e.g., Summer Pizza Combo" className="mt-1" />
              </div>
              <div>
                <Label>{tx.offerTitleAr}</Label>
                <Input value={titleAr} onChange={e => setTitleAr(e.target.value)} placeholder="مثال: كومبو البيتزا الصيفي" dir="rtl" className="mt-1" />
              </div>

              <div>
                <Label className="block mb-2">{tx.selectItems}</Label>
                <div className="max-h-60 overflow-y-auto border rounded-lg p-2 space-y-2 bg-muted/20">
                  {allMenuItems.length === 0 ? (
                    <p className="text-xs text-muted-foreground p-2 text-center">No menu items found</p>
                  ) : (
                    allMenuItems.map(item => {
                      const qty = selectedItems[item.id] || 0;
                      const isSelected = qty > 0;
                      return (
                        <div
                          key={item.id}
                          onClick={() => {
                            setSelectedItems(prev => {
                              const next = { ...prev };
                              if (next[item.id]) {
                                delete next[item.id];
                              } else {
                                next[item.id] = 1;
                              }
                              return next;
                            });
                          }}
                          className={`flex items-center justify-between p-2 hover:bg-muted/50 rounded-lg border transition-colors cursor-pointer select-none ${
                            isSelected ? "border-primary bg-primary/5" : "border-border/40 bg-card"
                          }`}
                        >
                          <div className="flex items-center gap-3">
                            {/* Checkbox Indicator */}
                            <div
                              className={`h-5 w-5 rounded border flex items-center justify-center transition-colors ${
                                isSelected ? "bg-primary border-primary text-white" : "border-border bg-background"
                              }`}
                            >
                              {isSelected && <Check className="h-3.5 w-3.5" />}
                            </div>

                            {/* QTY selector in front of item */}
                            {isSelected && (
                              <div
                                onClick={(e) => e.stopPropagation()}
                                className="flex items-center gap-1 bg-muted rounded-full p-0.5 border border-border/50 shrink-0"
                              >
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedItems(prev => {
                                      const next = { ...prev };
                                      if (next[item.id] > 1) {
                                        next[item.id] -= 1;
                                      } else {
                                        delete next[item.id];
                                      }
                                      return next;
                                    });
                                  }}
                                  className="h-5 w-5 rounded-full flex items-center justify-center hover:bg-background text-muted-foreground hover:text-foreground transition-colors"
                                >
                                  <Minus className="h-2.5 w-2.5" />
                                </button>
                                <span className="text-xs font-bold w-4 text-center select-none">{qty}</span>
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedItems(prev => ({
                                      ...prev,
                                      [item.id]: (prev[item.id] || 0) + 1
                                    }));
                                  }}
                                  className="h-5 w-5 rounded-full flex items-center justify-center hover:bg-background text-muted-foreground hover:text-foreground transition-colors"
                                >
                                  <Plus className="h-2.5 w-2.5" />
                                </button>
                              </div>
                            )}

                            <span className="text-sm font-medium">
                              {item.icon} {isAr ? item.nameAr : item.nameEn}
                            </span>
                          </div>
                          <span className="text-xs font-bold text-muted-foreground">${item.price.toFixed(2)}</span>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>{tx.originalPrice}</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={customOriginalPrice !== "" ? customOriginalPrice : originalTotal > 0 ? originalTotal.toFixed(2) : ""}
                    onChange={e => setCustomOriginalPrice(e.target.value)}
                    placeholder={originalTotal > 0 ? originalTotal.toFixed(2) : "0.00"}
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label>{tx.offerPrice}</Label>
                  <Input
                    required
                    type="number"
                    step="0.01"
                    value={offerPriceInput}
                    onChange={e => setOfferPriceInput(e.target.value)}
                    placeholder="0.00"
                    className="mt-1"
                  />
                </div>
              </div>

              {/* Live Calculations Display */}
              <div className="rounded-xl bg-primary/5 border border-primary/10 p-4 space-y-2 mt-2">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">{tx.originalPrice}:</span>
                  <span className="font-semibold line-through text-muted-foreground">${displayOriginalPrice.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">{tx.offerPrice}:</span>
                  <span className="font-bold text-primary">${displayOfferPrice.toFixed(2)}</span>
                </div>
                {discountPercentage > 0 && (
                  <div className="flex justify-between items-center text-sm border-t border-primary/10 pt-2">
                    <span className="font-semibold text-emerald-600 dark:text-emerald-400">{tx.discountPercent}:</span>
                    <Badge className="bg-emerald-500 hover:bg-emerald-600 text-white font-bold animate-pulse-glow">
                      {discountPercentage}% OFF
                    </Badge>
                  </div>
                )}
              </div>

              <Button
                type="submit"
                disabled={!titleEn.trim() || selectedCount === 0 || displayOfferPrice <= 0}
                className="w-full gradient-energy text-white font-bold h-11"
              >
                <Sparkles className="h-4 w-4 me-2" />
                {tx.createOffer}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>

      {/* Active Offers List */}
      <div className="lg:col-span-7 space-y-4">
        <h3 className="text-lg font-bold flex items-center gap-2">
          <Tag className="h-5 w-5 text-primary" />
          {tx.activeOffers}
        </h3>

        {offers.length === 0 ? (
          <Card className="border-dashed border-2 border-border/50">
            <CardContent className="py-12 text-center text-muted-foreground">
              {tx.noOffers}
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {offers.map(offer => (
              <Card key={offer.id} className="overflow-hidden shadow-[var(--shadow-soft)] border-border/50 flex flex-col justify-between">
                <div>
                  <div className="px-4 py-2.5 bg-muted/40 border-b flex items-center justify-between">
                    <h4 className="font-bold text-sm truncate max-w-[150px]">
                      {isAr ? offer.titleAr : offer.titleEn}
                    </h4>
                    <Badge className="bg-emerald-500 text-white font-bold text-xs">
                      {offer.discountPercentage}% OFF
                    </Badge>
                  </div>
                  <CardContent className="p-4 space-y-3">
                    <div className="text-xs text-muted-foreground">
                      <span className="font-semibold block mb-1">{tx.items}:</span>
                      <p className="line-clamp-2 bg-muted/20 p-2 rounded border border-border/30">
                        {getItemNames(offer.items, (offer as any).itemIds)}
                      </p>
                    </div>
                  </CardContent>
                </div>
                <div className="px-4 py-3 bg-muted/10 border-t flex items-center justify-between">
                  <div className="flex items-baseline gap-2">
                    <span className="text-xs line-through text-muted-foreground">${offer.originalPrice.toFixed(2)}</span>
                    <span className="text-base font-black text-primary">${offer.offerPrice.toFixed(2)}</span>
                  </div>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="text-destructive hover:bg-destructive/10 h-8 w-8 rounded-full"
                    onClick={() => handleDeleteOffer(offer.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SettingsPanel({ settings, setSettings, tx, lang, setLang }: { settings: RestaurantSettings; setSettings: (f: (s: RestaurantSettings) => RestaurantSettings) => void; tx: typeof t.en; lang: "en" | "ar"; setLang: (l: "en" | "ar") => void }) {
  const [local, setLocal] = useState<RestaurantSettings>({
    ...settings,
    hours: { ...DEFAULT_HOURS, ...(settings.hours ?? {}) },
  });
  function updateDay(day: string, patch: Partial<DayHours>) {
    setLocal(s => ({ ...s, hours: { ...s.hours, [day]: { ...s.hours[day], ...patch } } }));
  }
  return (
    <Card className="max-w-3xl border-border/50">
      <CardHeader><CardTitle>{tx.settings}</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        {/* Language Selection */}
        <div className="space-y-2">
          <Label className="text-sm font-semibold">{tx.language}</Label>
          <div className="grid grid-cols-2 gap-2 max-w-md">
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

        <div className="h-px bg-border my-4 max-w-md" />

        <div><Label>{tx.restaurantName}</Label><Input value={local.name} onChange={e => setLocal({ ...local, name: e.target.value })} /></div>
        <div><Label>{tx.mobile}</Label><Input value={local.mobile} onChange={e => setLocal({ ...local, mobile: e.target.value })} /></div>
        <div><Label>{tx.address}</Label><Input value={local.address} onChange={e => setLocal({ ...local, address: e.target.value })} /></div>
        <div>
          <Label className="mb-2 block">{tx.hours}</Label>
          <div className="space-y-2 rounded-xl border p-3">
            {DAYS.map(day => {
              const d = local.hours[day];
              return (
                <div key={day} className="grid grid-cols-12 items-center gap-2">
                  <div className="col-span-4 sm:col-span-3 text-sm font-medium">{tx.days[day]}</div>
                  <label className="col-span-3 sm:col-span-2 flex items-center gap-2 text-xs">
                    <Switch checked={d.open} onCheckedChange={v => updateDay(day, { open: v })} />
                    <span className="text-muted-foreground">{d.open ? tx.open : tx.closed}</span>
                  </label>
                  <div className="col-span-5 sm:col-span-7 grid grid-cols-2 gap-2">
                    <Input type="time" value={d.from} disabled={!d.open} onChange={e => updateDay(day, { from: e.target.value })} />
                    <Input type="time" value={d.to} disabled={!d.open} onChange={e => updateDay(day, { to: e.target.value })} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <Button className="gradient-energy text-white" onClick={() => { setSettings(() => local); toast.success(tx.saved); }}>{tx.save}</Button>
      </CardContent>
    </Card>
  );
}

export default RestaurantPage;
