import { useEffect, useState } from "react";
import { frontpageApiFetch } from "@/lib/api";

const STORAGE_KEY = "vox_cookie_consent";

type PublicSeoSettings = {
  google_analytics_id?: string | null;
  meta_pixel_id?: string | null;
  linkedin_partner_id?: string | null;
  google_ads_id?: string | null;
  x_pixel_id?: string | null;
  tiktok_pixel_id?: string | null;
  pinterest_tag_id?: string | null;
};

function readConsent(): "all" | "essential" | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "all" || v === "essential" ? v : null;
  } catch {
    return null;
  }
}

function injectScript(id: string, src: string, async = true) {
  if (typeof document === "undefined") return;
  if (document.getElementById(id)) return;
  const s = document.createElement("script");
  s.id = id;
  s.src = src;
  s.async = async;
  s.defer = true;
  document.head.appendChild(s);
}

function injectInline(id: string, code: string) {
  if (typeof document === "undefined") return;
  if (document.getElementById(id)) return;
  const s = document.createElement("script");
  s.id = id;
  s.text = code;
  document.head.appendChild(s);
}

/** Loads analytics / ad pixels only after "Accept all" cookie consent. */
export function ConsentTrackingScripts() {
  const [settings, setSettings] = useState<PublicSeoSettings | null>(null);
  const [consent, setConsent] = useState<"all" | "essential" | null>(null);

  useEffect(() => {
    setConsent(readConsent());
    const onStorage = () => setConsent(readConsent());
    const onConsent = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail === "all" || detail === "essential") setConsent(detail);
      else setConsent(readConsent());
    };
    window.addEventListener("storage", onStorage);
    window.addEventListener("vox:cookie-consent", onConsent);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("vox:cookie-consent", onConsent);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    frontpageApiFetch<PublicSeoSettings>("/frontpage/seo/settings")
      .then((data) => {
        if (!cancelled) setSettings(data || {});
      })
      .catch(() => {
        if (!cancelled) setSettings({});
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (consent !== "all" || !settings) return;

    const ga = (settings.google_analytics_id || "").trim();
    if (ga) {
      injectScript("vox-gtag-src", `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(ga)}`);
      injectInline(
        "vox-gtag-inline",
        `window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config',${JSON.stringify(ga)});`,
      );
    }

    const meta = (settings.meta_pixel_id || "").trim();
    if (meta) {
      injectInline(
        "vox-meta-pixel",
        `!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');fbq('init',${JSON.stringify(meta)});fbq('track','PageView');`,
      );
    }

    const li = (settings.linkedin_partner_id || "").trim();
    if (li) {
      injectInline(
        "vox-linkedin",
        `_linkedin_partner_id=${JSON.stringify(li)};window._linkedin_data_partner_ids=window._linkedin_data_partner_ids||[];window._linkedin_data_partner_ids.push(_linkedin_partner_id);`,
      );
      injectScript("vox-linkedin-src", "https://snap.licdn.com/li.lms-analytics/insight.min.js");
    }

    const ads = (settings.google_ads_id || "").trim();
    if (ads) {
      injectScript("vox-ads-src", `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(ads)}`);
      injectInline(
        "vox-ads-inline",
        `window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config',${JSON.stringify(ads)});`,
      );
    }

    const x = (settings.x_pixel_id || "").trim();
    if (x) {
      injectInline(
        "vox-x-pixel",
        `!function(e,t,n,s,u,a){e.twq||(s=e.twq=function(){s.exe?s.exe.apply(s,arguments):s.queue.push(arguments)},s.version='1.1',s.queue=[],u=t.createElement(n),u.async=!0,u.src='https://static.ads-twitter.com/uwt.js',a=t.getElementsByTagName(n)[0],a.parentNode.insertBefore(u,a))}(window,document,'script');twq('config',${JSON.stringify(x)});`,
      );
    }

    const tt = (settings.tiktok_pixel_id || "").trim();
    if (tt) {
      injectInline(
        "vox-tiktok",
        `!function(w,d,t){w.TiktokAnalyticsObject=t;var ttq=w[t]=w[t]||[];ttq.methods=["page","track","identify","instances","debug","on","off","once","ready","alias","group","enableCookie","disableCookie"],ttq.setAndDefer=function(t,e){t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}};for(var i=0;i<ttq.methods.length;i++)ttq.setAndDefer(ttq,ttq.methods[i]);ttq.instance=function(t){for(var e=ttq._i[t]||[],n=0;n<ttq.methods.length;n++)ttq.setAndDefer(e,ttq.methods[n]);return e},ttq.load=function(e,n){var i="https://analytics.tiktok.com/i18n/pixel/events.js";ttq._i=ttq._i||{},ttq._i[e]=[],ttq._i[e]._u=i,ttq._t=ttq._t||{},ttq._t[e]=+new Date,ttq._o=ttq._o||{},ttq._o[e]=n||{};var o=document.createElement("script");o.type="text/javascript",o.async=!0,o.src=i+"?sdkid="+e+"&lib="+t;var a=document.getElementsByTagName("script")[0];a.parentNode.insertBefore(o,a)};ttq.load(${JSON.stringify(tt)});ttq.page()}(window,document,'ttq');`,
      );
    }

    const pin = (settings.pinterest_tag_id || "").trim();
    if (pin) {
      injectInline(
        "vox-pinterest",
        `!function(e){if(!window.pintrk){window.pintrk=function(){window.pintrk.queue.push(Array.prototype.slice.call(arguments))};var n=window.pintrk;n.queue=[],n.version="3.0";var t=document.createElement("script");t.async=!0,t.src=e;var r=document.getElementsByTagName("script")[0];r.parentNode.insertBefore(t,r)}}("https://s.pinimg.com/ct/core.js");pintrk('load',${JSON.stringify(pin)});pintrk('page');`,
      );
    }
  }, [consent, settings]);

  return null;
}
