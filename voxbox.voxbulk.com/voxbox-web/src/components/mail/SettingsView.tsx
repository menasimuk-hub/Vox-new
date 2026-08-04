import { useState } from "react";
import {
  Plug,
  Trash2,
  Plus,
  CheckCircle2,
  XCircle,
  User,
  Save,
  Pencil,
  Snowflake,
  Play,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import type { AppUser, MailAccount } from "@/lib/mail-store";

interface Props {
  accounts: MailAccount[];
  user: AppUser;
  onSaveAccount: (a: MailAccount) => void | Promise<MailAccount | void>;
  onDeleteAccount: (id: string) => void;
  onSaveUser: (u: AppUser) => void;
  onTestAccount: (a: MailAccount) => Promise<{ ok: boolean; message: string; status?: string }>;
}

const PALETTE = ["var(--accent-1)", "var(--accent-2)", "var(--accent-3)"];

function blankAccount(index: number): MailAccount {
  return {
    id: `a${Date.now()}`,
    name: "New account",
    email: "",
    color: PALETTE[index % PALETTE.length] as string,
    imapHost: "",
    imapPort: 993,
    smtpHost: "",
    smtpPort: 465,
    username: "",
    password: "",
    ssl: true,
    status: "untested",
    signature: "",
    frozen: false,
  };
}

function StatusPill({ account }: { account: MailAccount }) {
  if (account.frozen)
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[11px] font-semibold text-muted-foreground">
        <Snowflake className="size-3" /> Frozen
      </span>
    );
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
        account.status === "ok"
          ? "bg-success/15 text-success"
          : account.status === "failed"
            ? "bg-destructive/15 text-destructive"
            : "bg-muted text-muted-foreground"
      }`}
    >
      {account.status === "ok" ? (
        <CheckCircle2 className="size-3" />
      ) : account.status === "failed" ? (
        <XCircle className="size-3" />
      ) : null}
      {account.status === "ok" ? "Connected" : account.status === "failed" ? "Failed" : "Not tested"}
    </span>
  );
}

function AccountForm({
  account,
  onSave,
  onClose,
  onTestAccount,
}: {
  account: MailAccount;
  onSave: (a: MailAccount) => void | Promise<MailAccount | void>;
  onClose: () => void;
  onTestAccount: (a: MailAccount) => Promise<{ ok: boolean; message: string; status?: string }>;
}) {
  const [draft, setDraft] = useState<MailAccount>(account);
  const [testing, setTesting] = useState(false);
  const set = (patch: Partial<MailAccount>) => setDraft((d) => ({ ...d, ...patch }));

  async function test(connect: boolean) {
    if (!draft.imapHost || !draft.smtpHost || !draft.email) {
      toast.error("Fill in email, IMAP host and SMTP host first.");
      return;
    }
    setTesting(true);
    try {
      const saved = (await onSave(draft)) ?? draft;
      const res = await onTestAccount(saved);
      const status = (res.status ?? (res.ok ? "ok" : "failed")) as MailAccount["status"];
      const next = { ...saved, status };
      setDraft(next);
      toast[res.ok ? "success" : "error"](
        res.ok
          ? connect
            ? res.message || `${draft.name} connected — syncing mail.`
            : res.message || "IMAP and SMTP settings look valid."
          : res.message || "Connection failed — check host names.",
      );
    } catch {
      toast.error("Connection test failed.");
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="space-y-4 rounded-xl border bg-card p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="size-3 rounded-full" style={{ backgroundColor: draft.color }} />
        <p className="font-display font-semibold">{draft.name || "Untitled"}</p>
        <StatusPill account={draft} />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label>Display name</Label>
          <Input value={draft.name} onChange={(e) => set({ name: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label>Email address</Label>
          <Input
            type="email"
            value={draft.email}
            onChange={(e) => set({ email: e.target.value })}
            placeholder="you@domain.com"
          />
        </div>
        <div className="space-y-1.5">
          <Label>IMAP host</Label>
          <Input
            value={draft.imapHost}
            onChange={(e) => set({ imapHost: e.target.value })}
            placeholder="imap.domain.com"
          />
        </div>
        <div className="space-y-1.5">
          <Label>IMAP port</Label>
          <Input
            type="number"
            value={draft.imapPort}
            onChange={(e) => set({ imapPort: Number(e.target.value) })}
          />
        </div>
        <div className="space-y-1.5">
          <Label>SMTP host</Label>
          <Input
            value={draft.smtpHost}
            onChange={(e) => set({ smtpHost: e.target.value })}
            placeholder="smtp.domain.com"
          />
        </div>
        <div className="space-y-1.5">
          <Label>SMTP port</Label>
          <Input
            type="number"
            value={draft.smtpPort}
            onChange={(e) => set({ smtpPort: Number(e.target.value) })}
          />
        </div>
        <div className="space-y-1.5">
          <Label>Username</Label>
          <Input value={draft.username} onChange={(e) => set({ username: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label>Password</Label>
          <Input
            type="password"
            value={draft.password ?? ""}
            onChange={(e) => set({ password: e.target.value })}
            placeholder={draft.passwordConfigured ? "Leave blank to keep current" : "Mailbox password"}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label>Email signature</Label>
          <Textarea
            rows={3}
            value={draft.signature}
            onChange={(e) => set({ signature: e.target.value })}
            placeholder={"—\nAlex Morgan\nyou@domain.com"}
          />
          <p className="text-xs text-muted-foreground">
            Added automatically to every reply and forward sent from this mailbox.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Switch
            checked={draft.ssl}
            onCheckedChange={(v) => set({ ssl: v })}
            id={`ssl-${draft.id}`}
          />
          <Label htmlFor={`ssl-${draft.id}`}>SSL / TLS</Label>
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          <Button variant="secondary" disabled={testing} onClick={() => test(false)}>
            {testing ? "Testing…" : "Test"}
          </Button>
          <Button disabled={testing} onClick={() => test(true)}>
            <Plug className="size-4" /> Connect
          </Button>
          <Button
            variant="outline"
            onClick={async () => {
              await onSave(draft);
              toast.success("Saved.");
              onClose();
            }}
          >
            <Save className="size-4" /> Save
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}

export function SettingsView({
  accounts,
  user,
  onSaveAccount,
  onDeleteAccount,
  onSaveUser,
  onTestAccount,
}: Props) {
  const [profile, setProfile] = useState(user);
  const [editing, setEditing] = useState<MailAccount | null>(null);
  const [pendingDelete, setPendingDelete] = useState<MailAccount | null>(null);

  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-xl border bg-card p-4 sm:p-5">
        <div className="flex items-center gap-2">
          <User className="size-4 text-primary" />
          <h2 className="font-display font-semibold">User account</h2>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label>Display name</Label>
            <Input
              value={profile.displayName}
              onChange={(e) => setProfile({ ...profile, displayName: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Login username</Label>
            <Input
              value={profile.username}
              onChange={(e) => setProfile({ ...profile, username: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label>New login password</Label>
            <Input
              type="password"
              value={profile.password ?? ""}
              onChange={(e) => setProfile({ ...profile, password: e.target.value })}
              placeholder="Leave blank to keep current"
            />
          </div>
          <div className="space-y-1.5 sm:col-span-3">
            <Label>Current password</Label>
            <Input
              type="password"
              value={profile.currentPassword ?? ""}
              onChange={(e) => setProfile({ ...profile, currentPassword: e.target.value })}
              placeholder="Required to save profile changes"
            />
          </div>
        </div>
        <Button
          onClick={() => {
            onSaveUser(profile);
          }}
        >
          <Save className="size-4" /> Save profile
        </Button>
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-display font-semibold">Mailboxes (IMAP / SMTP)</h2>
          <Button
            onClick={() => {
              setEditing(blankAccount(accounts.length));
            }}
          >
            <Plus className="size-4" /> Add mailbox
          </Button>
        </div>

        <div className="overflow-x-auto rounded-xl border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Mailbox</TableHead>
                <TableHead className="hidden sm:table-cell">Email</TableHead>
                <TableHead className="hidden md:table-cell">IMAP / SMTP</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {accounts.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                    No mailboxes yet — add your first IMAP/SMTP account.
                  </TableCell>
                </TableRow>
              )}
              {accounts.map((a) => (
                <TableRow key={a.id} className={a.frozen ? "opacity-60" : undefined}>
                  <TableCell className="font-medium">
                    <span className="flex items-center gap-2">
                      <span
                        className="size-2.5 rounded-full"
                        style={{ backgroundColor: a.color }}
                      />
                      {a.name || "Untitled"}
                    </span>
                  </TableCell>
                  <TableCell className="hidden sm:table-cell text-muted-foreground">
                    {a.email || "—"}
                  </TableCell>
                  <TableCell className="hidden md:table-cell text-xs text-muted-foreground">
                    {a.imapHost || "—"}:{a.imapPort} · {a.smtpHost || "—"}:{a.smtpPort}
                  </TableCell>
                  <TableCell>
                    <StatusPill account={a} />
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setEditing(a)}>
                        <Pencil className="size-3.5" />
                        <span className="hidden sm:inline">Edit</span>
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          void onSaveAccount({ ...a, frozen: !a.frozen });
                          toast.success(a.frozen ? "Mailbox resumed." : "Mailbox frozen.");
                        }}
                      >
                        {a.frozen ? (
                          <Play className="size-3.5" />
                        ) : (
                          <Snowflake className="size-3.5" />
                        )}
                        <span className="hidden sm:inline">{a.frozen ? "Resume" : "Freeze"}</span>
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-destructive hover:text-destructive"
                        onClick={() => setPendingDelete(a)}
                      >
                        <Trash2 className="size-3.5" />
                        <span className="hidden sm:inline">Delete</span>
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        {editing && (
          <AccountForm
            key={editing.id}
            account={accounts.find((a) => a.id === editing.id) ?? editing}
            onSave={onSaveAccount}
            onTestAccount={onTestAccount}
            onClose={() => setEditing(null)}
          />
        )}
      </section>

      <AlertDialog open={!!pendingDelete} onOpenChange={(o) => !o && setPendingDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this mailbox?</AlertDialogTitle>
            <AlertDialogDescription>
              {pendingDelete?.name} ({pendingDelete?.email || "no address"}) and all of its messages
              will be removed from Voxbox. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (pendingDelete) {
                  onDeleteAccount(pendingDelete.id);
                  if (editing?.id === pendingDelete.id) setEditing(null);
                  toast.success("Mailbox deleted.");
                }
                setPendingDelete(null);
              }}
            >
              Delete mailbox
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
