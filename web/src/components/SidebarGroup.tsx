import { useState, useId, type ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';

interface SidebarGroupProps {
  label: string;
  storageKey: string;
  defaultExpanded?: boolean;
  children: ReactNode;
}

export default function SidebarGroup({
  label,
  storageKey,
  defaultExpanded = true,
  children,
}: SidebarGroupProps) {
  const [expanded, setExpanded] = useState(() => {
    const stored = localStorage.getItem(`sidebar-${storageKey}`);
    if (stored !== null) return stored === 'true';
    return defaultExpanded;
  });

  const itemsId = useId();

  const toggle = () => {
    setExpanded((prev) => {
      const next = !prev;
      localStorage.setItem(`sidebar-${storageKey}`, String(next));
      return next;
    });
  };

  return (
    <div className="sidebar-group">
      <button
        className="sidebar-group-header"
        onClick={toggle}
        aria-expanded={expanded}
        aria-controls={itemsId}
      >
        <ChevronRight
          size={12}
          className={`sidebar-chevron${expanded ? ' sidebar-chevron-expanded' : ''}`}
        />
        {label}
      </button>
      {expanded && (
        <div id={itemsId} className="sidebar-group-items" role="group" aria-label={label}>
          {children}
        </div>
      )}
    </div>
  );
}
