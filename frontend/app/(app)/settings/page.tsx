'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useHealth, useConfigureWebhook } from '@/lib/api/hooks';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const HEALTH_LABELS: Record<string, string> = {
  db: 'Database',
  embedding_model: 'Embedding Model',
  object_storage: 'Object Storage',
};

const ENV_CONFIG = [
  { label: 'Model tier (primary)', value: 'claude-opus-4-8' },
  { label: 'Model tier (fast)', value: 'claude-haiku-4-5' },
  { label: 'Embedding model', value: 'text-embedding-3-large' },
  { label: 'Storage backend', value: 'S3-compatible' },
];

export default function SettingsPage() {
  const router = useRouter();
  const healthQuery = useHealth();
  const configureWebhook = useConfigureWebhook();

  const [webhookUrl, setWebhookUrl] = useState('');
  const [webhookSecret, setWebhookSecret] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (configureWebhook.isSuccess) {
      setSaved(true);
      const t = setTimeout(() => setSaved(false), 3000);
      return () => clearTimeout(t);
    }
  }, [configureWebhook.isSuccess]);

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-8">
      <h1 className="text-lg font-semibold">Settings</h1>

      {/* Section 1: System Health */}
      <section className="space-y-4">
        <div className="flex items-center justify-between border-b border-border pb-2">
          <h2 className="text-base font-semibold">System Health</h2>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => healthQuery.refetch()}
            disabled={healthQuery.isFetching}
          >
            {healthQuery.isFetching ? 'Refreshing…' : 'Refresh'}
          </Button>
        </div>

        {healthQuery.isLoading ? (
          <div className="grid grid-cols-3 gap-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-20 animate-pulse rounded-lg bg-muted" />
            ))}
          </div>
        ) : healthQuery.error ? (
          <div className="flex items-center gap-3 rounded-lg border border-destructive/40 bg-destructive/5 p-4">
            <p className="text-sm text-destructive">Unable to reach health endpoint.</p>
            <Button variant="outline" size="sm" onClick={() => healthQuery.refetch()}>
              Retry
            </Button>
          </div>
        ) : healthQuery.data ? (
          <div className="grid grid-cols-3 gap-3">
            {(Object.entries(healthQuery.data) as [string, boolean][]).map(([key, isUp]) => (
              <div key={key} className="rounded-lg border border-border p-3 text-center">
                <div
                  className={cn(
                    'mx-auto mb-2 size-3 rounded-full',
                    isUp ? 'bg-green-500' : 'bg-destructive'
                  )}
                />
                <p className="text-xs font-medium">{HEALTH_LABELS[key] ?? key}</p>
                <Badge variant={isUp ? 'default' : 'destructive'} className="mt-1 text-xs">
                  {isUp ? 'Up' : 'Down'}
                </Badge>
              </div>
            ))}
          </div>
        ) : null}
      </section>

      {/* Section 2: Environment Configuration */}
      <section className="space-y-4">
        <h2 className="text-base font-semibold border-b border-border pb-2">
          Environment Configuration
        </h2>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          {ENV_CONFIG.map(({ label, value }) => (
            <>
              <dt key={`dt-${label}`} className="text-muted-foreground">
                {label}
              </dt>
              <dd key={`dd-${label}`} className="font-mono text-xs">
                {value}
              </dd>
            </>
          ))}
        </dl>
      </section>

      {/* Section 3: Webhook Configuration */}
      <section className="space-y-4">
        <h2 className="text-base font-semibold border-b border-border pb-2">
          Webhook Configuration
        </h2>
        <div className="space-y-3">
          <input
            type="url"
            placeholder="https://your-endpoint.com/webhook"
            value={webhookUrl}
            onChange={(e) => setWebhookUrl(e.target.value)}
            className="w-full rounded border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary/50"
          />
          <input
            type="password"
            placeholder="Webhook signing secret (optional)"
            value={webhookSecret}
            onChange={(e) => setWebhookSecret(e.target.value)}
            className="w-full rounded border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary/50"
          />
          <div className="flex items-center gap-3">
            <Button
              onClick={() =>
                configureWebhook.mutate({
                  url: webhookUrl,
                  secret: webhookSecret || undefined,
                })
              }
              disabled={!webhookUrl || configureWebhook.isPending}
            >
              {configureWebhook.isPending ? 'Saving…' : 'Save Webhook'}
            </Button>
            {saved && <span className="text-sm text-green-600">Webhook configured.</span>}
          </div>
        </div>
      </section>

      {/* Section 4: Seed Status */}
      <section className="space-y-4">
        <h2 className="text-base font-semibold border-b border-border pb-2">Seed Status</h2>
        <div className="flex items-center justify-between rounded-lg border border-border p-4">
          <div>
            <p className="text-sm font-medium">Playbook Templates</p>
            <p className="text-xs text-muted-foreground">
              Bootstrap standard playbook templates for your practice areas.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => router.push('/playbooks')}>
            Go to Playbooks →
          </Button>
        </div>
      </section>
    </div>
  );
}
