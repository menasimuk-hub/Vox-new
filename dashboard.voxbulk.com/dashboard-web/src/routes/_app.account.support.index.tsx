import { createFileRoute, Link } from "@tanstack/react-router";
import { BookOpen, MessageCircle, Mail, FileText } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { useConnections } from "@/lib/connections";

export const Route = createFileRoute("/_app/account/support/")({
  head: () => ({ meta: [{ title: "Support — VoxBulk" }] }),
  component: SupportIndex,
});

function SupportIndex() {
  const { openChat } = useConnections();
  const cards = [
    { title: "Documentation", desc: "FAQ, categories and step-by-step guides.", Icon: BookOpen, to: "/account/support/faq" as const },
    { title: "Live chat", desc: "Chat with VoxBulk AI · instant answers.", Icon: MessageCircle, onClick: openChat },
    { title: "Email support", desc: "Open a ticket — reply, close, track status.", Icon: Mail, to: "/account/support/tickets" as const },
    { title: "Legal & DPA", desc: "Data processing agreement, terms.", Icon: FileText },
  ];

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader eyebrow="Account" title="Support" description="We're here to help." />
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {cards.map((c) => {
          const inner = (
            <Card className="h-full transition-colors hover:border-primary hover:bg-accent/40">
              <CardContent className="flex items-start gap-3 p-5">
                <div className="grid size-10 place-items-center rounded-lg bg-primary/10 text-primary"><c.Icon className="size-5" /></div>
                <div>
                  <p className="text-sm font-semibold">{c.title}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{c.desc}</p>
                </div>
              </CardContent>
            </Card>
          );
          if (c.to) return <Link key={c.title} to={c.to} className="text-left">{inner}</Link>;
          return <button key={c.title} onClick={c.onClick} className="text-left">{inner}</button>;
        })}
      </div>
    </div>
  );
}
