'use client';

import { createContext, useContext, useState, useCallback } from 'react';

export interface SelectedItem {
  id: string;
  charStart?: number;
  charEnd?: number;
  tabHint?: 'overview' | 'analysis' | 'redlines' | 'intelligence' | 'obligations' | 'versions';
}

interface HoveredSpan {
  charStart: number;
  charEnd: number;
}

export interface CompareMode {
  vA: string;
  vB: string;
}

interface WorkspaceContextValue {
  selected: SelectedItem | null;
  setSelected: (item: SelectedItem | null) => void;
  hovered: HoveredSpan | null;
  setHovered: (span: HoveredSpan | null) => void;
  activeTab: string;
  setActiveTab: (tab: string) => void;
  compareMode: CompareMode | null;
  setCompareMode: (mode: CompareMode | null) => void;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [selected, setSelectedRaw] = useState<SelectedItem | null>(null);
  const [hovered, setHovered] = useState<HoveredSpan | null>(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [compareMode, setCompareMode] = useState<CompareMode | null>(null);

  const setSelected = useCallback((item: SelectedItem | null) => {
    setSelectedRaw(item);
    if (item?.tabHint) {
      setActiveTab(item.tabHint);
    }
  }, []);

  return (
    <WorkspaceContext.Provider
      value={{ selected, setSelected, hovered, setHovered, activeTab, setActiveTab, compareMode, setCompareMode }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error('useWorkspace must be used within WorkspaceProvider');
  return ctx;
}
