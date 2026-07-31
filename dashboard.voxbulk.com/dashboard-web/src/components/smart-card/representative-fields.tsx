import { Globe, Hash, Mail, Phone, PhoneCall, User } from "lucide-react";
import * as React from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export type SocialLinks = {
  x?: string;
  instagram?: string;
  facebook?: string;
  tiktok?: string;
  linkedin?: string;
};

export type RepresentativeFormValue = {
  name: string;
  email: string;
  mobile: string;
  landline: string;
  extension: string;
  website: string;
  social_links: SocialLinks;
};

export function emptyRepresentativeForm(): RepresentativeFormValue {
  return {
    name: "",
    email: "",
    mobile: "",
    landline: "",
    extension: "",
    website: "",
    social_links: { x: "", instagram: "", facebook: "", tiktok: "", linkedin: "" },
  };
}

export function socialLinksPayload(links: SocialLinks): SocialLinks {
  const clean = (v?: string) => (v || "").trim() || undefined;
  return {
    x: clean(links.x),
    instagram: clean(links.instagram),
    facebook: clean(links.facebook),
    tiktok: clean(links.tiktok),
    linkedin: clean(links.linkedin),
  };
}

type IconProps = { className?: string };

function FieldIcon({
  icon: Icon,
  children,
  className,
}: {
  icon: React.ComponentType<IconProps>;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("relative", className)}>
      <Icon className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
      {children}
    </div>
  );
}

function XIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden fill="currentColor">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.727-8.835L1.254 2.25H8.08l4.253 5.622zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
    </svg>
  );
}

function InstagramIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="2" y="2" width="20" height="20" rx="5" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

function FacebookIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden fill="currentColor">
      <path d="M14 13.5h2.5l1-4H14v-2c0-1.03 0-2 2-2h1.5V2.14C17.174 2.097 15.943 2 14.643 2 11.928 2 10 3.657 10 6.7v2.8H7v4h3V22h4z" />
    </svg>
  );
}

function TikTokIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden fill="currentColor">
      <path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-2.88 2.5 2.89 2.89 0 0 1-2.89-2.89 2.89 2.89 0 0 1 2.89-2.89c.28 0 .54.04.79.1v-3.5a6.37 6.37 0 0 0-.79-.05A6.34 6.34 0 0 0 3.15 15.3a6.34 6.34 0 0 0 6.34 6.34 6.34 6.34 0 0 0 6.34-6.34V8.75a8.2 8.2 0 0 0 4.76 1.52V6.84a4.85 4.85 0 0 1-1-.15z" />
    </svg>
  );
}

function LinkedInIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden fill="currentColor">
      <path d="M6.94 6.5a1.94 1.94 0 1 1 0-3.88 1.94 1.94 0 0 1 0 3.88zM4.5 21.5h4.88V8.75H4.5V21.5zM13.07 8.75c-1.8 0-2.95 1-3.47 1.7V8.75H5.75c.06 1.4 0 12.75 0 12.75h3.85v-7.12c0-.38.03-.76.14-1.03.3-.76.99-1.55 2.15-1.55 1.52 0 2.13 1.16 2.13 2.86v6.84h3.85v-7.34c0-3.93-2.1-5.76-4.9-5.76z" />
    </svg>
  );
}

export function RepresentativeFields({
  value,
  onChange,
  disabled,
  nameRequired = true,
  mobileHint,
}: {
  value: RepresentativeFormValue;
  onChange: (next: RepresentativeFormValue) => void;
  disabled?: boolean;
  nameRequired?: boolean;
  mobileHint?: string;
}) {
  const patch = (partial: Partial<RepresentativeFormValue>) => onChange({ ...value, ...partial });
  const patchSocial = (key: keyof SocialLinks, v: string) =>
    onChange({ ...value, social_links: { ...value.social_links, [key]: v } });

  return (
    <div className="grid gap-3">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label className="text-xs">
            Name {nameRequired ? <span className="text-destructive">*</span> : null}
          </Label>
          <FieldIcon icon={User}>
            <Input
              className="pl-8"
              value={value.name}
              disabled={disabled}
              onChange={(e) => patch({ name: e.target.value })}
              placeholder="Alex Representative"
            />
          </FieldIcon>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Email</Label>
          <FieldIcon icon={Mail}>
            <Input
              className="pl-8"
              type="email"
              value={value.email}
              disabled={disabled}
              onChange={(e) => patch({ email: e.target.value })}
              placeholder="alex@company.com"
            />
          </FieldIcon>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">{mobileHint || "Mobile"}</Label>
          <FieldIcon icon={Phone}>
            <Input
              className="pl-8"
              value={value.mobile}
              disabled={disabled}
              onChange={(e) => patch({ mobile: e.target.value })}
              placeholder="+447…"
            />
          </FieldIcon>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="grid grid-cols-[1fr_5.5rem] gap-2">
          <div className="space-y-1.5">
            <Label className="text-xs">Landline</Label>
            <FieldIcon icon={PhoneCall}>
              <Input
                className="pl-8"
                value={value.landline}
                disabled={disabled}
                onChange={(e) => patch({ landline: e.target.value })}
                placeholder="+44 20…"
              />
            </FieldIcon>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Ext</Label>
            <FieldIcon icon={Hash}>
              <Input
                className="pl-8"
                value={value.extension}
                disabled={disabled}
                onChange={(e) => patch({ extension: e.target.value })}
                placeholder="101"
              />
            </FieldIcon>
          </div>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Website</Label>
          <FieldIcon icon={Globe}>
            <Input
              className="pl-8"
              value={value.website}
              disabled={disabled}
              onChange={(e) => patch({ website: e.target.value })}
              placeholder="https://"
            />
          </FieldIcon>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">X (Twitter)</Label>
          <FieldIcon icon={XIcon}>
            <Input
              className="pl-8"
              value={value.social_links.x || ""}
              disabled={disabled}
              onChange={(e) => patchSocial("x", e.target.value)}
              placeholder="@handle or URL"
            />
          </FieldIcon>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-1.5">
          <Label className="text-xs">Instagram</Label>
          <FieldIcon icon={InstagramIcon}>
            <Input
              className="pl-8"
              value={value.social_links.instagram || ""}
              disabled={disabled}
              onChange={(e) => patchSocial("instagram", e.target.value)}
              placeholder="@handle or URL"
            />
          </FieldIcon>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Facebook</Label>
          <FieldIcon icon={FacebookIcon}>
            <Input
              className="pl-8"
              value={value.social_links.facebook || ""}
              disabled={disabled}
              onChange={(e) => patchSocial("facebook", e.target.value)}
              placeholder="URL"
            />
          </FieldIcon>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">TikTok</Label>
          <FieldIcon icon={TikTokIcon}>
            <Input
              className="pl-8"
              value={value.social_links.tiktok || ""}
              disabled={disabled}
              onChange={(e) => patchSocial("tiktok", e.target.value)}
              placeholder="@handle or URL"
            />
          </FieldIcon>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">LinkedIn</Label>
          <FieldIcon icon={LinkedInIcon}>
            <Input
              className="pl-8"
              value={value.social_links.linkedin || ""}
              disabled={disabled}
              onChange={(e) => patchSocial("linkedin", e.target.value)}
              placeholder="URL"
            />
          </FieldIcon>
        </div>
      </div>
    </div>
  );
}
