import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown } from 'lucide-react';

export interface SelectItemData {
  label: string;
  value: string | null;
  disabled?: boolean;
}

interface SelectContextValue {
  items: SelectItemData[];
  value: string | null;
  open: boolean;
  setOpen: (open: boolean) => void;
  selectValue: (value: string | null) => void;
}

const SelectContext = createContext<SelectContextValue | null>(null);

function useSelectContext() {
  const ctx = useContext(SelectContext);
  if (!ctx) throw new Error('Select components must be used inside <Select>');
  return ctx;
}

interface SelectProps {
  items?: SelectItemData[];
  value?: string | null;
  defaultValue?: string | null;
  onValueChange?: (value: string | null) => void;
  disabled?: boolean;
  className?: string;
  children?: React.ReactNode;
}

export function Select({
  items = [],
  value,
  defaultValue = null,
  onValueChange,
  disabled = false,
  className = '',
  children,
}: SelectProps) {
  const [internalValue, setInternalValue] = useState<string | null>(defaultValue);
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const currentValue = value !== undefined ? value : internalValue;

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const ctx = useMemo<SelectContextValue>(
    () => ({
      items,
      value: currentValue,
      open,
      setOpen: (o) => {
        if (!disabled) setOpen(o);
      },
      selectValue: (v) => {
        setInternalValue(v);
        onValueChange?.(v);
        setOpen(false);
      },
    }),
    [items, currentValue, open, disabled, onValueChange]
  );

  return (
    <SelectContext.Provider value={ctx}>
      <div 
        ref={rootRef} 
        className={`relative ${className}`}
        onMouseEnter={() => { if (!disabled) setOpen(true); }}
        onMouseLeave={() => setOpen(false)}
      >
        {children}
      </div>
    </SelectContext.Provider>
  );
}

interface SelectTriggerProps {
  className?: string;
  children?: React.ReactNode;
}

export function SelectTrigger({ className = '', children }: SelectTriggerProps) {
  const { open, setOpen } = useSelectContext();
  return (
    <button
      type="button"
      onClick={() => setOpen(!open)}
      className={`flex w-full items-center justify-between gap-2 rounded-xl bg-[#09090b] border border-white/[0.08] px-3 py-2 text-xs text-white transition-colors focus:outline-none focus:ring-2 focus:ring-primary/40 ${
        open ? 'border-primary/40 bg-[#121216]' : 'hover:bg-[#121216] hover:border-white/[0.14]'
      } ${className}`}
    >
      <span className="truncate text-left">{children}</span>
      <ChevronDown className={`w-3.5 h-3.5 text-muted flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
    </button>
  );
}

interface SelectValueProps {
  placeholder?: string;
  children?: React.ReactNode;
}

export function SelectValue({ placeholder = 'Select…', children }: SelectValueProps) {
  const { items, value } = useSelectContext();
  if (children !== undefined) return <>{children}</>;
  const item = items.find((i) => i.value === value);
  return <>{item ? item.label : placeholder}</>;
}

interface SelectContentProps {
  className?: string;
  children?: React.ReactNode;
}

export function SelectContent({ className = '', children }: SelectContentProps) {
  const { open, items } = useSelectContext();
  if (!open) return null;
  return (
    <div
      className={`absolute z-50 mt-1.5 w-full min-w-[180px] rounded-xl bg-[#09090b] border border-white/[0.08] shadow-[0_8px_32px_rgba(0,0,0,0.5)] py-1.5 ${className}`}
    >
      {children !== undefined ? (
        children
      ) : (
        items.map((item) => (
          <SelectItem key={item.value ?? '__none'} value={item.value} disabled={item.disabled}>
            {item.label}
          </SelectItem>
        ))
      )}
    </div>
  );
}

export function SelectGroup({ children, className = '' }: { children?: React.ReactNode; className?: string }) {
  return <div className={`px-1.5 ${className}`}>{children}</div>;
}

export function SelectLabel({ children, className = '' }: { children?: React.ReactNode; className?: string }) {
  return <p className={`px-2.5 py-1 text-[9px] uppercase tracking-wider text-muted font-semibold ${className}`}>{children}</p>;
}

interface SelectItemProps {
  value: string | null;
  disabled?: boolean;
  className?: string;
  children?: React.ReactNode;
}

export function SelectItem({ value, disabled = false, className = '', children }: SelectItemProps) {
  const { selectValue, value: current } = useSelectContext();
  const selected = current === value;
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => selectValue(value)}
      className={`flex w-full items-center justify-between gap-2 px-2.5 py-1.5 text-left text-xs rounded-lg transition-colors ${
        selected ? 'text-white bg-primary/15' : 'text-zinc-300 hover:text-white hover:bg-[#1a1a20]/80'
      } ${disabled ? 'opacity-40 cursor-not-allowed' : ''} ${className}`}
    >
      <span className="truncate">{children}</span>
      {selected && <Check className="w-3.5 h-3.5 text-primary flex-shrink-0" />}
    </button>
  );
}