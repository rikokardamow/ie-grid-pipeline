// Wide tables scroll inside this box on small screens. It takes focus so
// keyboard users can scroll it too. (Copied from the record's site.)
export function TableScroll({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="table-scroll" role="region" aria-label={label} tabIndex={0}>
      {children}
    </div>
  );
}
