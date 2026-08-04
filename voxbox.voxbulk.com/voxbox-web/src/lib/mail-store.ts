export type MailFolder = "inbox" | "sent" | "archive" | "trash";

export interface MailAttachment {
  id: string;
  kind: "image" | "link";
  name: string;
  url: string;
}

export interface MailAccount {
  id: string;
  name: string;
  email: string;
  color: string;
  imapHost: string;
  imapPort: number;
  smtpHost: string;
  smtpPort: number;
  username: string;
  /** Form-only; never returned by API */
  password?: string;
  ssl: boolean;
  status: "untested" | "ok" | "failed";
  signature: string;
  frozen: boolean;
  sortOrder?: number;
  passwordConfigured?: boolean;
}

export interface MailMessage {
  id: string;
  accountId: string;
  from: string;
  fromEmail: string;
  to: string;
  subject: string;
  preview: string;
  html: string;
  text: string;
  date: string;
  unread: boolean;
  important: boolean;
  starred: boolean;
  hasAttachment: boolean;
  folder: MailFolder;
  attachments?: MailAttachment[];
}

export interface AppUser {
  username: string;
  displayName: string;
  /** Form-only when changing login password */
  password?: string;
  currentPassword?: string;
}

export const SESSION_KEY = "voxbox.session";
