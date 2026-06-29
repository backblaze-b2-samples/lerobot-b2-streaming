import Link from "next/link";
import { Film, Radio } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DatasetStatsCards } from "@/components/dashboard/dataset-stats-cards";
import { RecentEpisodesTable } from "@/components/dashboard/recent-episodes-table";
import { IngestChart } from "@/components/dashboard/ingest-chart";

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-1.5">
            Your LeRobot v3 teleoperation dataset on Backblaze B2.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild size="sm" variant="outline" className="h-8">
            <Link href="/stream">
              <Radio className="h-3.5 w-3.5" />
              Stream from B2
            </Link>
          </Button>
          <Button asChild size="sm" className="h-8">
            <Link href="/episodes/new">
              <Film className="h-3.5 w-3.5" />
              Record episode
            </Link>
          </Button>
        </div>
      </div>
      <DatasetStatsCards />
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="animate-fade-in-up stagger-3">
          <IngestChart />
        </div>
        <div className="animate-fade-in-up stagger-4">
          <RecentEpisodesTable />
        </div>
      </div>
    </div>
  );
}
