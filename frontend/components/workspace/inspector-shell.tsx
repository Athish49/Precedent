'use client';

import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { useWorkspace } from './workspace-context';
import { OverviewTab } from './tabs/overview-tab';
import { AnalysisTab } from './tabs/analysis-tab';
import { RedlinesTab } from './tabs/redlines-tab';
import { IntelligenceTab } from './tabs/intelligence-tab';
import { ObligationsTab } from './tabs/obligations-tab';
import { VersionsTab } from './tabs/versions-tab';

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'analysis', label: 'Analysis' },
  { id: 'redlines', label: 'Redlines' },
  { id: 'intelligence', label: 'Intelligence' },
  { id: 'obligations', label: 'Obligations' },
  { id: 'versions', label: 'Versions' },
] as const;

interface InspectorShellProps {
  contractId: string;
}

export function InspectorShell({ contractId }: InspectorShellProps) {
  const { activeTab, setActiveTab } = useWorkspace();

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background">
      <Tabs
        value={activeTab}
        onValueChange={setActiveTab}
        className="flex h-full flex-col gap-0"
      >
        <TabsList
          variant="line"
          className="h-auto w-full shrink-0 justify-start overflow-x-auto rounded-none border-b border-border px-2 py-0"
        >
          {TABS.map((tab) => (
            <TabsTrigger key={tab.id} value={tab.id} className="shrink-0 py-2 text-xs">
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <div className="min-h-0 flex-1 overflow-hidden">
          <TabsContent value="overview" className="h-full overflow-y-auto p-3">
            <OverviewTab contractId={contractId} />
          </TabsContent>
          <TabsContent value="analysis" className="h-full overflow-y-auto p-3">
            <AnalysisTab contractId={contractId} />
          </TabsContent>
          <TabsContent value="redlines" className="h-full overflow-y-auto p-3">
            <RedlinesTab contractId={contractId} />
          </TabsContent>
          <TabsContent value="intelligence" className="h-full overflow-y-auto">
            <IntelligenceTab contractId={contractId} />
          </TabsContent>
          <TabsContent value="obligations" className="h-full overflow-y-auto p-3">
            <ObligationsTab contractId={contractId} />
          </TabsContent>
          <TabsContent value="versions" className="h-full overflow-y-auto p-3">
            <VersionsTab contractId={contractId} />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
