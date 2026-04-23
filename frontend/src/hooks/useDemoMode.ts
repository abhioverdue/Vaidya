/**
 * Vaidya — useDemoMode hook
 * Returns true when at least one API call has fallen back to demo data.
 * Subscribes to the module-level flag in demoData.ts.
 */

import { useState, useEffect } from 'react';
import { isDemoMode, subscribeDemoMode } from '@/services/demoData';

export function useDemoMode(): boolean {
  const [demo, setDemo] = useState(isDemoMode());

  useEffect(() => {
    // Already true before mount?
    setDemo(isDemoMode());
    const unsub = subscribeDemoMode(() => setDemo(true));
    return unsub;
  }, []);

  return demo;
}
