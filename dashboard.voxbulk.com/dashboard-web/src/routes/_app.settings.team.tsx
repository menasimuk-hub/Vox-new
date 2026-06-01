import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import { Check, Copy, Mail, Trash2, UserPlus } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  useCreateTeamInvite,
  useRemoveTeamMember,
  useRevokeTeamInvite,
  useTeamInvites,
  useTeamMembers,
} from "@/lib/queries";
import { useSession } from "@/lib/session";

const ROLES = [
  { value: "accountant", label: "Accountant — billing & invoices" },
  { value: "manager", label: "Manager — full dashboard access" },
  { value: "member", label: "Member — standard access" },
  { value: "receptionist", label: "Receptionist — calls & recovery" },
];

export const Route = createFileRoute("/_app/settings/team")({
  head: () => ({ meta: [{ title: "Team — VoxBulk" }] }),
  component: TeamSettings,
});

function TeamSettings() {
  const { session } = useSession();
  const membersQ = useTeamMembers();
  const invitesQ = useTeamInvites();
  const inviteM = useCreateTeamInvite();
  const revokeM = useRevokeTeamInvite();
  const removeM = useRemoveTeamMember();

  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState("accountant");
  const [copiedLinkId, setCopiedLinkId] = React.useState<string | null>(null);

  const myRole = String(session?.profile?.role || "owner").toLowerCase();
  const canManage = !myRole || myRole === "owner" || myRole === "manager";

  const onInvite = async () => {
    const em = email.trim().toLowerCase();
    if (!em) {
      toast.error("Enter an email address");
      return;
    }
    try {
      const res = await inviteM.mutateAsync({ email: em, role, send_email: true });
      toast.success(res.email_sent ? `Invite emailed to ${em}` : `Invite created for ${em} — copy the link below`);
      setEmail("");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not send invite");
    }
  };

  const copyLink = async (url: string, inviteId: string) => {
    try {
      await navigator.clipboard.writeText(url);
      setCopiedLinkId(inviteId);
      window.setTimeout(() => setCopiedLinkId((current) => (current === inviteId ? null : current)), 2000);
      toast.success("Invite link copied");
    } catch {
      toast.error("Could not copy link");
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Settings"
        title="Team members"
        description="Invite colleagues — e.g. an accountant to manage billing and pay invoices."
      />

      <Card>
        <CardHeader>
          <CardTitle>Invite teammate</CardTitle>
          <CardDescription>
            They receive an email with a sign-up link. Accountants can use{" "}
            <Link to="/account/billing" className="text-primary underline-offset-2 hover:underline">Billing</Link>{" "}
            to view invoices and set up GoCardless payment.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 md:flex-row md:items-end">
          <div className="flex-1 space-y-1.5">
            <Label className="text-xs">Email</Label>
            <Input type="email" placeholder="finance@clinic.com" value={email} onChange={(e) => setEmail(e.target.value)} disabled={!canManage} />
          </div>
          <div className="w-full space-y-1.5 md:w-56">
            <Label className="text-xs">Role</Label>
            <Select value={role} onValueChange={setRole} disabled={!canManage}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {ROLES.map((r) => (
                  <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button className="gap-1.5" onClick={() => void onInvite()} disabled={!canManage || inviteM.isPending}>
            <UserPlus className="size-4" /> {inviteM.isPending ? "Sending…" : "Send invite"}
          </Button>
        </CardContent>
        {!canManage && (
          <CardContent className="pt-0 text-xs text-muted-foreground">Only owners and managers can invite or remove team members.</CardContent>
        )}
      </Card>

      <Card>
        <CardHeader><CardTitle>Pending invites</CardTitle></CardHeader>
        <CardContent className="px-0">
          {invitesQ.isLoading ? (
            <div className="p-6"><Skeleton className="h-10 w-full" /></div>
          ) : (invitesQ.data || []).length === 0 ? (
            <p className="px-6 pb-6 text-sm text-muted-foreground">No pending invites.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Expires</TableHead>
                  <TableHead className="pr-6 text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(invitesQ.data || []).map((inv) => (
                  <TableRow key={inv.id}>
                    <TableCell className="pl-6">{inv.email}</TableCell>
                    <TableCell className="capitalize">{inv.role}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {inv.expires_at ? new Date(inv.expires_at).toLocaleDateString() : "—"}
                      {inv.is_expired ? " (expired)" : ""}
                    </TableCell>
                    <TableCell className="pr-6 text-right">
                      <Button size="sm" variant="ghost" className="gap-1" onClick={() => void copyLink(inv.signup_url, inv.id)}>
                        {copiedLinkId === inv.id ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
                        {copiedLinkId === inv.id ? "Copied" : "Link"}
                      </Button>
                      {canManage && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="gap-1 text-destructive"
                          onClick={() => void revokeM.mutateAsync(inv.id).then(() => toast.success("Invite revoked")).catch((e) => toast.error(e instanceof Error ? e.message : "Failed"))}
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Active members</CardTitle></CardHeader>
        <CardContent className="px-0">
          {membersQ.isLoading ? (
            <div className="p-6"><Skeleton className="h-10 w-full" /></div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="pr-6 text-right"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(membersQ.data || []).map((m) => (
                  <TableRow key={m.user_id}>
                    <TableCell className="pl-6">{m.email}</TableCell>
                    <TableCell className="capitalize">{m.role || "owner"}</TableCell>
                    <TableCell>{m.is_active ? "Active" : "Blocked"}</TableCell>
                    <TableCell className="pr-6 text-right">
                      {canManage && m.user_id !== session?.profile?.user_id && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="gap-1 text-destructive"
                          onClick={() => void removeM.mutateAsync(m.user_id).then(() => toast.success("Member removed")).catch((e) => toast.error(e instanceof Error ? e.message : "Failed"))}
                        >
                          <Trash2 className="size-3.5" /> Remove
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <p className="flex items-center gap-1 text-xs text-muted-foreground">
        <Mail className="size-3.5" /> Invites use your organisation sign-in page. The invitee creates a password and joins this clinic automatically.
      </p>
    </div>
  );
}
