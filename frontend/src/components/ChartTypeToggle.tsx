interface Props {
  options: { type: string; label: string }[];
  value: string;
  onChange: (type: string) => void;
}

export function ChartTypeToggle({ options, value, onChange }: Props) {
  return (
    <div className="chart-type-toggle">
      {options.map((opt) => (
        <button
          key={opt.type}
          className={opt.type === value ? 'active' : ''}
          onClick={() => onChange(opt.type)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
