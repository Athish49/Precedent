'use client';

import type { ReactNode } from 'react';
import { ApiError } from '@/lib/api/client';

interface QueryBoundaryProps {
  isLoading: boolean;
  isEmpty?: boolean;
  error: Error | null;
  /** Skeleton shaped like the content. Defaults to a generic block skeleton. */
  loadingSkeleton?: ReactNode;
  emptyMessage?: string;
  /** Primary action shown in empty state (e.g. a button). */
  emptyAction?: ReactNode;
  /** Retry callback shown in error state. */
  onRetry?: () => void;
  children: ReactNode;
}

export function QueryBoundary({
  isLoading,
  isEmpty,
  error,
  loadingSkeleton,
  emptyMessage = 'No items found.',
  emptyAction,
  onRetry,
  children,
}: QueryBoundaryProps) {
  if (isLoading) {
    return <>{loadingSkeleton ?? <DefaultSkeleton />}</>;
  }

  if (error) {
    const message =
      error instanceof ApiError ? error.message : 'Something went wrong. Please try again.';
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <p className="text-sm text-red-600">{message}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-700"
          >
            Retry
          </button>
        )}
      </div>
    );
  }

  if (isEmpty) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <p className="text-sm text-neutral-500">{emptyMessage}</p>
        {emptyAction}
      </div>
    );
  }

  return <>{children}</>;
}

function DefaultSkeleton() {
  return (
    <div className="space-y-3 p-4" aria-busy="true" aria-label="Loading">
      {[80, 60, 90, 50].map((w) => (
        <div
          key={w}
          className="h-4 animate-pulse rounded bg-neutral-200"
          style={{ width: `${w}%` }}
        />
      ))}
    </div>
  );
}
